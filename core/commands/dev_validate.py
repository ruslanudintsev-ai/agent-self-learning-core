"""core/commands/dev_validate.py
Команда валидации и пре-коммит аудита новых модулей commands/.
Проверяет синтаксис, AST-контракт, запрет print() и регистрацию в ядре.
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
from typing import Any, Dict, List

from core.commands.base import BaseCommand, CommandError

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class DevValidateCommand(BaseCommand):
    name = "dev-validate"
    description = "Pre-commit валидация модулей core/commands/ на соответствие регламенту"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Путь к валидируемому файлу команды (например core/commands/my_cmd.py)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции проверки без тестового запуска подпроцесса",
        )

    def run(self, args: argparse.Namespace) -> int:
        as_json = getattr(args, "json", False)
        is_dry_run = getattr(args, "dry_run", False)
        target_path = Path(args.file)

        if not target_path.is_absolute():
            target_path = BASE_DIR / target_path

        if not target_path.exists():
            raise CommandError(
                message=f"Файл {target_path} не существует",
                error_code="FILE_NOT_FOUND",
                suggested_fix="Укажите корректный путь к файлу команды в core/commands/<имя>.py",
            )

        checks: Dict[str, Any] = {}
        failed_checks: List[str] = []

        # 1. Проверка имени файла (snake_case)
        stem = target_path.stem
        is_snake = bool(re.match(r"^[a-z0-9]+(_[a-z0-9]+)*$", stem))
        checks["file_naming_snake_case"] = {
            "status": "ok" if is_snake else "failed",
            "file_stem": stem,
        }
        if not is_snake:
            failed_checks.append("Имя файла должно быть в snake_case (например: db_cleanup.py)")

        # 2. Компиляция синтаксиса
        try:
            py_compile.compile(str(target_path), doraise=True)
            checks["syntax_py_compile"] = {"status": "ok"}
        except py_compile.PyCompileError as e:
            checks["syntax_py_compile"] = {"status": "failed", "error": str(e)}
            failed_checks.append(f"Синтаксическая ошибка: {e}")

        # 3. AST анализ (BaseCommand, *Command, kebab-case name, запрет print)
        ast_errors = []
        cmd_name = ""
        try:
            source = target_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(target_path))
            found_class = False

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if node.name.endswith("Command"):
                        found_class = True
                        for item in node.body:
                            # Проверяем свойство name
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name) and target.id == "name":
                                        if isinstance(item.value, ast.Constant):
                                            cmd_name = str(item.value.value)
                            elif isinstance(item, ast.AnnAssign):
                                if isinstance(item.target, ast.Name) and item.target.id == "name":
                                    if isinstance(item.value, ast.Constant):
                                        cmd_name = str(item.value.value)

                            # Проверяем отсутствие print() в run()
                            if isinstance(item, ast.FunctionDef) and item.name == "run":
                                for sub in ast.walk(item):
                                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                                        if sub.func.id == "print":
                                            ast_errors.append(
                                                f"Строка {sub.lineno}: прямой вызов print(). Замените на self.output()."
                                            )

            if not found_class:
                ast_errors.append("Класс команды обязан иметь суффикс 'Command' (например: MyActionCommand)")

            if cmd_name:
                if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", cmd_name):
                    ast_errors.append(f"Свойство name='{cmd_name}' должно быть в kebab-case")
            else:
                cmd_name = stem.replace("_", "-")

            checks["ast_compliance"] = {
                "status": "ok" if not ast_errors else "failed",
                "detected_name": cmd_name,
                "errors": ast_errors,
            }
            if ast_errors:
                failed_checks.extend(ast_errors)

        except Exception as e:
            checks["ast_compliance"] = {"status": "failed", "error": str(e)}
            failed_checks.append(f"Ошибка парсинга AST: {e}")

        # 4. Проверка запуска в подпроцессе (если не dry-run и нет ошибок)
        if not failed_checks and not is_dry_run and cmd_name:
            try:
                proc = subprocess.run(
                    [sys.executable, "manage.py", cmd_name, "--help"],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if proc.returncode == 0:
                    checks["subcommand_registration"] = {"status": "ok"}
                else:
                    checks["subcommand_registration"] = {
                        "status": "failed",
                        "error": proc.stderr or proc.stdout,
                    }
                    failed_checks.append(f"Команда '{cmd_name}' не регистрируется в ядре: {proc.stderr[:200]}")
            except Exception as e:
                checks["subcommand_registration"] = {"status": "failed", "error": str(e)}
                failed_checks.append(f"Сбой выполнения подпроцесса manage.py: {e}")

        is_passed = len(failed_checks) == 0
        payload = {
            "status": "ok" if is_passed else "error",
            "verdict": "PASSED_COMPLIANCE" if is_passed else "FAILED_COMPLIANCE",
            "target_file": str(target_path.relative_to(BASE_DIR)),
            "checks": checks,
        }

        if not is_passed:
            payload["failed_checks"] = failed_checks
            payload["suggested_fix"] = "Исправьте замечания AST-анализатора и проверьте регистрацию BaseCommand."

        self.output(payload, as_json=as_json)
        return 0 if is_passed else 1
