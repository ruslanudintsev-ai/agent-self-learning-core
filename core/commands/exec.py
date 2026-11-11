"""core/commands/exec.py
Zero-Context Code Interpreter для Metric QA Lab CLI.
Позволяет агенту выполнять Python-выражения и расчеты на лету внутри
контекста проекта без создания временных файлов.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

from core.commands.base import BaseCommand

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ProjectConfig:
    """Хелпер доступа к путям и файлам конфигураций Metric QA Lab."""

    def __init__(self, base_dir: Path):
        self.BASE_DIR = base_dir
        self.PROFILES_DIR = base_dir / "browser_profiles"
        self.CONFIG_DIR = base_dir / "config"
        self.REPORTS_DIR = base_dir / "reports"
        self.LOGS_DIR = base_dir / "logs"

    def read_json(self, filename: str) -> Any:
        """Считывает и парсит JSON-файл из папки config/."""
        p = self.CONFIG_DIR / filename
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    @property
    def target_pool(self) -> Any:
        return self.read_json("target_pool.json")

    @property
    def target_queries(self) -> Any:
        return self.read_json("target_queries.json")

    @property
    def neutral_queries(self) -> Any:
        return self.read_json("neutral_queries.json")

    @property
    def warmup_queries(self) -> Any:
        return self.read_json("warmup_queries.json")

    @property
    def white_sites(self) -> Any:
        return self.read_json("white_sites.json")


def _sanitize_for_json(val: Any) -> Any:
    """Рекурсивно приводит объекты к JSON-сериализуемым примитивам."""
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


class ExecCommand(BaseCommand):
    """Выполнение Python-кода в отдельном процессе с ограничением времени.

    Команда запускает произвольный код текущего пользователя и не является
    песочницей безопасности.
    """

    name = "exec"
    description = "Выполнение Python-кода в отдельном процессе с ограничением времени (не песочница безопасности)"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--code",
            type=str,
            required=True,
            help="Python-код или выражение для выполнения",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=15,
            help="Таймаут выполнения в секундах (по умолчанию 15)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Проверить синтаксис кода без фактического выполнения",
        )

    def run(self, args: argparse.Namespace) -> int:
        code_str = (args.code or "").strip()
        as_json = getattr(args, "json", False)
        is_dry_run = getattr(args, "dry_run", False)
        timeout = getattr(args, "timeout", 15)

        if not code_str:
            self.output(
                {"status": "error", "message": "Параметр --code не может быть пустым"},
                as_json=as_json,
            )
            return 1

        if timeout <= 0:
            self.output(
                {"status": "error", "message": "Параметр --timeout должен быть больше нуля"},
                as_json=as_json,
            )
            return 1

        # 1. Режим Smart Dry-Run: проверка компиляции кода
        if is_dry_run:
            try:
                try:
                    compile(code_str, "<cle-exec>", "eval")
                    mode = "eval"
                except SyntaxError:
                    compile(code_str, "<cle-exec>", "exec")
                    mode = "exec"

                self.output(
                    {
                        "status": "ok",
                        "mode": "dry-run",
                        "syntax_check": "passed",
                        "execution_type": mode,
                        "code": code_str,
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
                        "offset": syn_err.offset,
                    },
                    as_json=as_json,
                )
                return 1

        try:
            completed = subprocess.run(
                [sys.executable, "-m", "core.exec_worker"],
                input=json.dumps({"code": code_str}),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(BASE_DIR),
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.output(
                {
                    "status": "error",
                    "error_type": "TimeoutExpired",
                    "message": f"Выполнение прервано по таймауту ({timeout} сек.)",
                    "timeout_sec": timeout,
                },
                as_json=as_json,
            )
            return 1
        except OSError as exc:
            self.output(
                {"status": "error", "error_type": type(exc).__name__, "message": str(exc)},
                as_json=as_json,
            )
            return 1

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {
                "status": "error",
                "error_type": "WorkerProtocolError",
                "message": "CLE exec worker returned invalid JSON",
                "return_code": completed.returncode,
                "stdout": completed.stdout.strip() or None,
                "stderr": completed.stderr.strip() or None,
            }

        self.output(payload, as_json=as_json)
        return 0 if completed.returncode == 0 and payload.get("status") == "ok" else 1
