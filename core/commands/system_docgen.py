"""core/commands/system_docgen.py
Команда автогенерации SKILL.md на основе зарегистрированных команд CLI.
Извлекает флаги, типы и справку из ArgumentParser и компилирует чистые таблицы.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from core.commands.base import BaseCommand
from core.commands import load_commands

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SystemDocgenCommand(BaseCommand):
    name: str = "system-docgen"
    description: str = "Автогенерация SKILL.md на основе зарегистрированных команд CLI"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--output",
            type=str,
            default=str(BASE_DIR / ".agents" / "skills" / "agent-cli" / "SKILL.md"),
            help="Целевой путь для записи файла SKILL.md",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Вывести сгенерированный Markdown в stdout без перезаписи файла",
        )

    def _extract_actions(self, subparser: argparse.ArgumentParser) -> List[Dict[str, Any]]:
        """Извлекает флаги, типы и справку из ArgumentParser команды."""
        flags = []
        for action in subparser._actions:
            if action.dest == "help":
                continue

            flags.append({
                "options": ", ".join(action.option_strings) if action.option_strings else action.dest,
                "required": getattr(action, "required", False),
                "help": action.help or "Без описания",
                "default": action.default if action.default != argparse.SUPPRESS else None,
            })
        return flags

    def run(self, args: argparse.Namespace) -> int:
        commands_map = load_commands()
        as_json = getattr(args, "json", False)

        md_lines = [
            "---",
            "name: agent-cli",
            'description: "Автоматически сгенерированный справочник интерфейса CLI. Используй эти команды вместо одноразовых ad-hoc скриптов."',
            "---",
            "",
            "# Справочник команд Command Layer Engine (CLE)",
            "",
            "> Данный файл сгенерирован автоматически через `cle system-docgen`. Не редактируйте вручную.",
            "",
            "## Доступные команды",
            "",
        ]

        # Сортировка по имени модульных команд для детерминированного вывода
        for cmd_name in sorted(commands_map.keys()):
            cmd = commands_map[cmd_name]
            md_lines.append(f"### `cle {cmd_name}`")
            md_lines.append(f"**Назначение:** {cmd.description or getattr(cmd, 'help', None) or 'Описание отсутствует'}\n")

            temp_parser = argparse.ArgumentParser(prog=f"cle {cmd_name}", add_help=False)
            if hasattr(cmd, "configure_parser"):
                cmd.configure_parser(temp_parser)
            else:
                cmd.add_arguments(temp_parser)
            actions = self._extract_actions(temp_parser)

            if actions:
                md_lines.append("| Аргумент | Обязательный | Описание | По умолчанию |")
                md_lines.append("| :--- | :---: | :--- | :--- |")
                for act in actions:
                    req_str = "Да" if act["required"] else "Нет"
                    default_str = f"`{act['default']}`" if act["default"] is not None else "-"
                    md_lines.append(f"| `{act['options']}` | {req_str} | {act['help']} | {default_str} |")
                md_lines.append("")
            else:
                md_lines.append("*Команда не принимает дополнительных аргументов.*\n")

        md_lines.extend([
            "## Общие системные флаги",
            "- `--json`: Обязательный флаг при вызове агентом для получения структурированного JSON ответа.",
            "- `--dry-run`: Симуляция выполнения для команд с деструктивными операциями.",
            "",
            "## Рецепты вызовов",
            "1. **Создание новой команды (Dev Scaffold):**",
            "   ```bash",
            "   cle dev-scaffold --command cache-cleaner",
            "   ```",
            "2. **Проверка качества и AST валидация:**",
            "   ```bash",
            "   cle dev-validate --file core/commands/cache_cleaner.py --json",
            "   ```",
            "3. **Актуализация документации скила на лету:**",
            "   ```bash",
            "   cle system-docgen",
            "   ```",
            "4. **Безопасные ad-hoc вычисления без создания файлов (Zero-Context Interpreter):**",
            "   ```bash",
            '   cle exec --code "2 + 2" --json',
            '   cle exec --code "import os; result = os.listdir(\'.\')" --json',
            "   ```",
            "5. **Управление снимками конфигураций и откат:**",
            "   ```bash",
            '   cle rollback create --reason "before_update" --json',
            "   cle rollback list --json",
            "   cle rollback restore --last --dry-run --json",
            "   cle rollback restore --last --json",
            "   ```",
            "6. **Диагностика системы и процессов:**",
            "   ```bash",
            "   cle sys-info --json",
            "   cle service-health --json",
            "   ```",
        ])

        rendered_markdown = "\n".join(md_lines) + "\n"

        if getattr(args, "dry_run", False):
            self.output(
                {
                    "status": "ok",
                    "mode": "dry-run",
                    "commands_count": len(commands_map),
                    "markdown_preview": rendered_markdown,
                },
                as_json=as_json,
            )
            return 0

        target_path = Path(args.output)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(rendered_markdown, encoding="utf-8")
        except OSError as exc:
            self.output(
                {"status": "error", "message": f"Не удалось записать файл: {exc}"},
                as_json=as_json,
            )
            return 1

        self.output(
            {
                "status": "ok",
                "saved_to": str(target_path),
                "commands_documented": len(commands_map),
            },
            as_json=as_json,
        )
        return 0
