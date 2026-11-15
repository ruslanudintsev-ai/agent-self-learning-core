"""core/commands/system_docgen.py
Команда автогенерации документации CLI на основе зарегистрированных команд.

Генерирует два файла:
  SKILL.md      — короткий индекс: команда + назначение одной строкой + частые рецепты;
  reference.md  — полные таблицы флагов, значения по умолчанию и все рецепты.

Причина разделения: SKILL.md попадает в контекст агента целиком, поэтому он
должен оставаться коротким. Полные флаги нужны редко и загружаются по ссылке.

Абсолютные пути в значениях по умолчанию не попадают в документацию: внутри
проекта они заменяются на `<project>/...`, вне проекта — на `<absolute path>`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from core.commands.base import BaseCommand
from core.commands import load_commands

BASE_DIR = Path(__file__).resolve().parent.parent.parent

RECIPES = [
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
    "   cle exec --code \"import os; result = os.listdir('.')\" --json",
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
]

QUICK_RECIPES = [
    "1. **Многошаговая задача за один вызов (HTTP + SSL + GSC + SSH):**",
    "   ```bash",
    '   cle batch-exec --script "res = [ctx.http_get(s) for s in sites]; result = res" --json',
    "   ```",
    "2. **Разовая проверка без файлов:**",
    "   ```bash",
    '   cle exec --code "2 + 2" --json',
    "   ```",
    "3. **Снять снимок конфигов перед правкой:**",
    "   ```bash",
    '   cle rollback create --reason "before_update" --json',
    "   ```",
]


class SystemDocgenCommand(BaseCommand):
    name: str = "system-docgen"
    description: str = "Автогенерация SKILL.md (индекс) и reference.md (полные флаги) на основе команд CLI"

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

            default = action.default if action.default != argparse.SUPPRESS else None
            if isinstance(default, (str, Path)):
                default_path = Path(default)
                if default_path.is_absolute():
                    try:
                        relative = default_path.resolve().relative_to(BASE_DIR.resolve())
                        default = f"<project>/{relative.as_posix()}"
                    except (OSError, ValueError):
                        default = "<absolute path>"

            flags.append({
                "options": ", ".join(action.option_strings) if action.option_strings else action.dest,
                "required": getattr(action, "required", False),
                "help": action.help or "Без описания",
                "default": default,
            })
        return flags

    def _command_parser(self, cmd_name: str, cmd: Any) -> argparse.ArgumentParser:
        temp_parser = argparse.ArgumentParser(prog=f"cle {cmd_name}", add_help=False)
        if hasattr(cmd, "configure_parser"):
            cmd.configure_parser(temp_parser)
        else:
            cmd.add_arguments(temp_parser)
        return temp_parser

    def _render_index(self, commands_map: Dict[str, Any]) -> str:
        """Короткий индекс: каждая команда — заголовок и одна строка назначения."""
        lines = [
            "---",
            "name: agent-cli",
            'description: "Автоматически сгенерированный справочник интерфейса CLI. Используй эти команды вместо одноразовых ad-hoc скриптов."',
            "---",
            "",
            "# CLE — индекс команд",
            "",
            "> Сгенерировано `cle system-docgen`. Полные флаги, значения по умолчанию и все",
            "> рецепты — в `reference.md` в этой же папке. Читай его только когда нужен",
            "> конкретный флаг: держать таблицы в контексте незачем.",
            "",
            "## Команды",
            "",
        ]
        for cmd_name in sorted(commands_map.keys()):
            cmd = commands_map[cmd_name]
            purpose = cmd.description or getattr(cmd, "help", None) or "Описание отсутствует"
            lines.append(f"### `cle {cmd_name}`")
            lines.append(f"{purpose}")
            lines.append("")

        lines.extend([
            "## Системные флаги",
            "- `--json` — обязателен при вызове агентом: структурированный ответ вместо текста.",
            "- `--dry-run` — проверка без выполнения; обязательна для деструктивных команд.",
            "",
            "## Рецепты (частое)",
            *QUICK_RECIPES,
            "",
            "Полный список рецептов — `reference.md`.",
        ])
        return "\n".join(lines) + "\n"

    def _render_reference(self, commands_map: Dict[str, Any]) -> str:
        """Полный справочник: таблицы флагов по каждой команде и все рецепты."""
        lines = [
            "# CLE — полный справочник",
            "",
            "> Сгенерировано `cle system-docgen`. Таблицы флагов и значения по умолчанию.",
            "> Индекс команд и частые рецепты — в `SKILL.md`.",
            "",
            "## Команды и флаги",
            "",
        ]
        for cmd_name in sorted(commands_map.keys()):
            cmd = commands_map[cmd_name]
            lines.append(f"### `cle {cmd_name}`")
            lines.append(f"**Назначение:** {cmd.description or getattr(cmd, 'help', None) or 'Описание отсутствует'}\n")

            actions = self._extract_actions(self._command_parser(cmd_name, cmd))
            if actions:
                lines.append("| Аргумент | Обязательный | Описание | По умолчанию |")
                lines.append("| :--- | :---: | :--- | :--- |")
                for act in actions:
                    req_str = "Да" if act["required"] else "Нет"
                    default_str = f"`{act['default']}`" if act["default"] is not None else "-"
                    lines.append(f"| `{act['options']}` | {req_str} | {act['help']} | {default_str} |")
                lines.append("")
            else:
                lines.append("*Команда не принимает дополнительных аргументов.*\n")

        lines.extend([
            "## Системные флаги",
            "- `--json`: Обязательный флаг при вызове агентом для получения структурированного JSON ответа.",
            "- `--dry-run`: Симуляция выполнения для команд с деструктивными операциями.",
            "",
            "## Рецепты вызовов",
            *RECIPES,
        ])
        return "\n".join(lines) + "\n"

    def run(self, args: argparse.Namespace) -> int:
        commands_map = load_commands()
        as_json = getattr(args, "json", False)

        index_md = self._render_index(commands_map)
        reference_md = self._render_reference(commands_map)

        if getattr(args, "dry_run", False):
            self.output(
                {
                    "status": "ok",
                    "mode": "dry-run",
                    "commands_count": len(commands_map),
                    "markdown_preview": index_md,
                    "reference_preview": reference_md,
                },
                as_json=as_json,
            )
            return 0

        target_path = Path(args.output)
        reference_path = target_path.parent / "reference.md"
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(index_md, encoding="utf-8")
            reference_path.write_text(reference_md, encoding="utf-8")
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
                "reference_saved_to": str(reference_path),
                "commands_documented": len(commands_map),
            },
            as_json=as_json,
        )
        return 0
