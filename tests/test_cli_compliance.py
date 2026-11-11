"""tests/test_cli_compliance.py
Автоматический тест соответствия модулей commands/ регламенту cle-command-authoring.md:
1. Наследование от BaseCommand.
2. Именование файлов (snake_case), классов (*Command) и свойств name (kebab-case).
3. Запрет прямого print() в методе run() (только self.output).
4. Наличие ключа 'status' в выводе.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import pytest

from core.commands.base import BaseCommand
from core.commands import load_commands

COMMANDS_DIR = Path(__file__).resolve().parent.parent / "core" / "commands"


def get_command_files():
    """Возвращает список файлов команд, исключая служебные."""
    return [
        f for f in COMMANDS_DIR.glob("*.py")
        if f.name not in ("__init__.py", "base.py")
    ]


class TestCommandAuthoringCompliance:
    """Проверка всех плагинов в core/commands/ на соответствие регламенту."""

    @pytest.mark.parametrize("file_path", get_command_files(), ids=lambda p: p.name)
    def test_file_naming_convention(self, file_path: Path):
        """Имя файла должно быть строго в snake_case."""
        name = file_path.stem
        assert re.match(r"^[a-z0-9]+(_[a-z0-9]+)*$", name), (
            f"Имя файла '{file_path.name}' нарушает конвенцию snake_case"
        )

    @pytest.mark.parametrize("file_path", get_command_files(), ids=lambda p: p.name)
    def test_class_naming_and_no_direct_print(self, file_path: Path):
        """Класс должен заканчиваться на Command, а метод run не должен содержать print()."""
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        found_command_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Проверяем имя класса
                if node.name.endswith("Command"):
                    found_command_class = True

                    # Проверяем метод run на отсутствие прямых вызовов print()
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == "run":
                            for subnode in ast.walk(item):
                                if isinstance(subnode, ast.Call):
                                    if isinstance(subnode.func, ast.Name) and subnode.func.id == "print":
                                        pytest.fail(
                                            f"В {file_path.name}:{item.name} на строке {subnode.lineno} "
                                            f"обнаружен прямой вызов print(). Весь вывод обязан идти через self.output()."
                                        )

        assert found_command_class, f"В файле '{file_path.name}' не найден класс команды с суффиксом 'Command'"

    def test_commands_registered_and_kebab_case_names(self):
        """Все команды должны успешно инстанцироваться и иметь kebab-case имя."""
        commands_map = load_commands()
        assert len(commands_map) > 0, "Не загружено ни одной команды из core/commands/"

        for name, cmd in commands_map.items():
            assert isinstance(cmd, BaseCommand), f"Команда {name} не наследуется от BaseCommand"
            assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name), (
                f"Свойство name='{name}' команды {cmd.__class__.__name__} нарушает kebab-case"
            )

    def test_import_error_does_not_quarantine_source_by_default(self, monkeypatch):
        """A transient import error must not move a tracked module by default."""
        import core.commands as command_package

        quarantined = []
        monkeypatch.setattr(
            command_package.pkgutil,
            "iter_modules",
            lambda paths: [(None, "broken_probe", False)],
        )
        monkeypatch.setattr(
            command_package.importlib,
            "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("missing optional dependency")),
        )
        monkeypatch.setattr(
            command_package,
            "_quarantine_module",
            lambda *args, **kwargs: quarantined.append(args[0]),
        )

        command_package.load_commands()

        assert quarantined == []

    def test_service_health_command_execution(self, capsys):
        """Тест выполнения команды service-health в JSON и dry-run режимах."""
        from core.cli import main
        import json

        # Тест dry-run с флагом --json
        main(["service-health", "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "status" in data
        assert data["status"] == "ok"
        assert data["dry_run"] is True
        assert "checks" in data
        assert "disk" in data["checks"]
        assert "python" in data["checks"]
        assert "workspace" in data["checks"]
