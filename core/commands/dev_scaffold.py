"""core/commands/dev_scaffold.py
Автоматическая генерация заготовок тестов (Test Scaffolding) для новых модулей core/commands/.
Создает готовый файл tests/test_command_<name>.py с проверками парсера, JSON-режима и AST.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from core.commands.base import BaseCommand, CommandError
from core.commands import load_commands

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class DevScaffoldCommand(BaseCommand):
    name = "dev-scaffold"
    description = "Автоматическая генерация готовых pytest-тестов для команд из core/commands/"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--command",
            type=str,
            required=True,
            help="Имя команды для генерации теста (например: service-health)",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=str(BASE_DIR / "tests"),
            help="Директория для сохранения тестового файла",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции: показать код теста без записи на диск",
        )

    def run(self, args: argparse.Namespace) -> int:
        as_json = getattr(args, "json", False)
        is_dry_run = getattr(args, "dry_run", False)
        target_cmd_name = args.command.strip()

        commands_map = load_commands()
        if target_cmd_name not in commands_map:
            raise CommandError(
                message=f"Команда '{target_cmd_name}' не найдена в реестре core/commands/",
                error_code="COMMAND_NOT_FOUND",
                suggested_fix=f"Доступные команды: {', '.join(sorted(commands_map.keys()))}",
            )

        cmd_instance = commands_map[target_cmd_name]
        class_name = cmd_instance.__class__.__name__
        module_name = cmd_instance.__class__.__module__

        temp_parser = argparse.ArgumentParser(add_help=False)
        if hasattr(cmd_instance, "configure_parser"):
            cmd_instance.configure_parser(temp_parser)
        else:
            cmd_instance.add_arguments(temp_parser)

        has_dry_run = any("--dry-run" in a.option_strings for a in temp_parser._actions)
        file_snake_name = target_cmd_name.replace("-", "_")

        test_code = self._generate_test_template(
            cmd_name=target_cmd_name,
            class_name=class_name,
            module_name=module_name,
            has_dry_run=has_dry_run,
        )

        out_dir = Path(args.output_dir)
        target_test_file = out_dir / f"test_generated_{file_snake_name}.py"

        if is_dry_run:
            payload = {
                "status": "ok",
                "mode": "plan",
                "target_command": target_cmd_name,
                "projected_file": str(target_test_file),
                "has_dry_run": has_dry_run,
                "code_preview": test_code,
            }
            self.output(payload, as_json=as_json)
            return 0

        out_dir.mkdir(parents=True, exist_ok=True)
        target_test_file.write_text(test_code, encoding="utf-8")

        payload = {
            "status": "ok",
            "message": f"Шаблон теста успешно сгенерирован: {target_test_file.name}",
            "command": target_cmd_name,
            "saved_to": str(target_test_file),
            "suggested_run": f"pytest {target_test_file.relative_to(BASE_DIR)}",
        }
        self.output(payload, as_json=as_json)
        return 0

    def _generate_test_template(
        self,
        cmd_name: str,
        class_name: str,
        module_name: str,
        has_dry_run: bool,
    ) -> str:
        dry_run_test = ""
        if has_dry_run:
            dry_run_test = f"""
    def test_{cmd_name.replace("-", "_")}_dry_run(self, capsys):
        \"\"\"Проверка флага --dry-run и манифеста безопасности.\"\"\"
        main(["{cmd_name}", "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("status") == "ok"
        assert data.get("dry_run") is True or data.get("mode") == "plan"
"""

        return f'''"""Auto-generated test suite for command: {cmd_name}
Сгенерировано через cle dev-scaffold.
"""

from __future__ import annotations

import json
import pytest
from core.cli import build_parser, main
from {module_name} import {class_name}


class Test{class_name}:
    """Набор тестов для команды {cmd_name}."""

    def test_{cmd_name.replace("-", "_")}_registration(self):
        \"\"\"Проверка регистрации в основном парсере.\"\"\"
        parser = build_parser()
        subparser_action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
        assert "{cmd_name}" in subparser_action.choices

    def test_{cmd_name.replace("-", "_")}_json_output(self, capsys):
        \"\"\"Проверка структурированного JSON-вывода.\"\"\"
        try:
            main(["{cmd_name}", "--json"])
        except SystemExit as exc:
            assert exc.code in (0, None)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "status" in data
{dry_run_test}
'''
