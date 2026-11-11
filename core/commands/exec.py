"""core/commands/exec.py
Zero-Context Code Interpreter для Metric QA Lab CLI.
Позволяет агенту выполнять Python-выражения и расчеты на лету внутри
контекста проекта без создания временных файлов.
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from core.commands.base import BaseCommand, CommandError

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
    """Выполнение Python-выражения или скрипта в контексте проекта без временных файлов."""

    name = "exec"
    description = "Выполнение Python-выражения или скрипта в контексте проекта без создания временных файлов"

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

        if not code_str:
            self.output(
                {"status": "error", "message": "Параметр --code не может быть пустым"},
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

        # 2. Подготовка изолированного скоупа окружения проекта
        config_obj = ProjectConfig(BASE_DIR)

        scope: Dict[str, Any] = {
            "__builtins__": __builtins__,
            "Path": Path,
            "json": json,
            "os": os,
            "sys": sys,
            "time": time,
            "datetime": datetime,
            "timezone": timezone,
            "config": config_obj,
            "BASE_DIR": BASE_DIR,
            "result": None,
        }

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                # Сначала пробуем как eval-выражение (для однострочников, возвращающих значение)
                try:
                    compiled = compile(code_str, "<cle-exec>", "eval")
                    scope["result"] = eval(compiled, scope)
                except SyntaxError:
                    # Если многострочный блок или инструкция с присваиванием — выполняем через exec
                    compiled = compile(code_str, "<cle-exec>", "exec")
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
