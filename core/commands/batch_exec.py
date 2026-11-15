"""core/commands/batch_exec.py
Code Mode Batch Orchestrator для Command Layer Engine (CLE).
Позволяет агенту выполнять многошаговые оркестрационные цепочки (GSC, SSH, HTTP, Git)
за один вызов без раздувания контекста и без создания временных файлов.
Вдохновлено паттерном Cloudflare Code Mode & Habr 1107276.
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import ssl
import sys
import time
import traceback
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from core.commands.base import BaseCommand, CommandError

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ToolContext:
    """Встроенный контекст утилит для безопасной и компактной оркестрации."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def http_get(self, url: str, timeout: int = 10, user_agent: Optional[str] = None) -> Dict[str, Any]:
        """Быстрый HTTP GET запрос с возвратом компактного ответа."""
        ua = user_agent or "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return {
                    "url": url,
                    "status": resp.status,
                    "length": len(body),
                    "body_snippet": body[:300],
                }
        except urllib.error.HTTPError as e:
            return {"url": url, "status": e.code, "error": str(e)}
        except Exception as e:
            return {"url": url, "status": 0, "error": str(e)}

    def check_ssl(self, domain: str, timeout: int = 5) -> Dict[str, Any]:
        """Проверка срока действия SSL сертификата."""
        import socket
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(timeout)
                s.connect((domain, 443))
                cert = s.getpeercert()
                not_after = cert["notAfter"]
                expire_date = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days_left = (expire_date - datetime.now(timezone.utc)).days
                return {"domain": domain, "status": "ok", "days_left": days_left}
        except Exception as e:
            return {"domain": domain, "status": "error", "error": str(e)}

    def gsc_query(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 10,
        credentials_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Запрос аналитики GSC с компактным форматированием строк."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            key_file = credentials_path or os.environ.get(
                "GSC_SERVICE_ACCOUNT_FILE",
                os.path.join(os.path.expanduser("~"), ".secrets", "google", "service-account.json"),
            )
            creds = service_account.Credentials.from_service_account_file(
                key_file, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )
            service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
            body = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": dimensions or ["query"],
                "rowLimit": row_limit,
            }
            res = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
            rows = res.get("rows", [])
            return {
                "site_url": site_url,
                "rows_count": len(rows),
                "rows": [
                    {
                        "keys": r.get("keys", []),
                        "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0),
                        "position": round(r.get("position", 0.0), 1),
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            return {"site_url": site_url, "error": str(e)}

    def ssh_cmd(
        self,
        host: str,
        cmd: str,
        user: str = "root",
        key_path: Optional[str] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """Безопасное выполнение команды на удаленном сервере по SSH."""
        try:
            import paramiko

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kp = key_path or os.path.expanduser("~/.ssh/id_rsa")
            ssh.connect(host, username=user, key_filename=kp, timeout=timeout)
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode("utf-8", errors="ignore").strip()
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            ssh.close()
            return {"status": "ok", "stdout": out, "stderr": err if err else None}
        except Exception as e:
            return {"status": "error", "error": str(e)}


def _sanitize_for_json(val: Any) -> Any:
    """Рекурсивно приводит объекты к сериализуемым примитивам."""
    if val is None or isinstance(val, (int, float, bool, str)):
        return val
    if isinstance(val, Path):
        return str(val)
    if isinstance(val, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in val]
    if isinstance(val, dict):
        return {str(k): _sanitize_for_json(v) for k, v in val.items()}
    if hasattr(val, "to_dict") and callable(val.to_dict):
        try:
            return _sanitize_for_json(val.to_dict())
        except Exception:
            pass
    return str(val)


class BatchExecCommand(BaseCommand):
    """Многошаговая оркестрация инструментов за один вызов (Code Mode Orchestrator)."""

    name = "batch-exec"
    description = "Выполнение оркестрационного сценария за один вызов с доступом к GSC, SSH, HTTP и SSL без создания временных файлов"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--script",
            type=str,
            required=True,
            help="Python-сценарий или выражение для оркестрации",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Проверка синтаксиса и сигнатур без выполнения",
        )

    def run(self, args: argparse.Namespace) -> int:
        script_str = (args.script or "").strip()
        as_json = getattr(args, "json", False)
        is_dry_run = getattr(args, "dry_run", False)

        if not script_str:
            self.output(
                {"status": "error", "message": "Параметр --script не может быть пустым"},
                as_json=as_json,
            )
            return 1

        if is_dry_run:
            try:
                compile(script_str, "<cle-batch-exec>", "exec")
                self.output(
                    {
                        "status": "ok",
                        "mode": "dry-run",
                        "syntax_check": "passed",
                        "script_len": len(script_str),
                    },
                    as_json=as_json,
                )
                return 0
            except SyntaxError as syn_err:
                self.output(
                    {
                        "status": "error",
                        "mode": "dry-run",
                        "syntax_check": "failed",
                        "error": str(syn_err),
                        "lineno": syn_err.lineno,
                    },
                    as_json=as_json,
                )
                return 1

        ctx_obj = ToolContext(BASE_DIR)

        scope: Dict[str, Any] = {
            "__builtins__": __builtins__,
            "ctx": ctx_obj,
            "Path": Path,
            "json": json,
            "time": time,
            "datetime": datetime,
            "timezone": timezone,
            "BASE_DIR": BASE_DIR,
            "result": None,
        }

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                try:
                    compiled = compile(script_str, "<cle-batch-exec>", "eval")
                    scope["result"] = eval(compiled, scope)
                except SyntaxError:
                    compiled = compile(script_str, "<cle-batch-exec>", "exec")
                    exec(compiled, scope)

            raw_stdout = stdout_buf.getvalue().strip()
            raw_stderr = stderr_buf.getvalue().strip()
            raw_result = scope.get("result")

            payload: Dict[str, Any] = {
                "status": "ok",
                "result": _sanitize_for_json(raw_result),
                "stdout": raw_stdout if raw_stdout else None,
                "stderr": raw_stderr if raw_stderr else None,
            }
            self.output(payload, as_json=as_json)
            return 0

        except Exception as exc:
            payload = {
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "stdout": stdout_buf.getvalue().strip() or None,
                "stderr": stderr_buf.getvalue().strip() or None,
            }
            self.output(payload, as_json=as_json)
            return 1
