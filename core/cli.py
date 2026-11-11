"""core/cli.py
Единый командный интерфейс управления проектом (Command Layer Engine / CLE).
Динамически обнаруживает и загружает модульные команды из core/commands/.
Поддерживает флаг --json, телеметрию, бюджетирование вывода и самоисцеление при ошибках.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent

# Настройка системного логгера CLE
logger = logging.getLogger("cle")
if not logger.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)
logger.setLevel(logging.INFO)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Command Layer Engine (CLE) — Единый интерфейс управления проектом для автономных агентов",
    )
    parser.add_argument("--json", action="store_true", help="Вывод результатов в формате JSON (для агентов)")
    subparsers = parser.add_subparsers(dest="command", help="Команда для выполнения")

    # Динамическая загрузка плагинов из core.commands
    try:
        from core.commands import load_commands
        commands_map = load_commands()
        for cmd_name, cmd_instance in commands_map.items():
            if cmd_name in subparsers.choices:
                continue
            desc = cmd_instance.description or getattr(cmd_instance, "help", "") or ""
            sub_p = subparsers.add_parser(cmd_name, help=desc, description=desc)
            if hasattr(cmd_instance, "configure_parser"):
                cmd_instance.configure_parser(sub_p)
            else:
                cmd_instance.add_arguments(sub_p)
            # Гарантируем флаг --json на уровне подкоманды
            if not any("--json" in a.option_strings for a in sub_p._actions):
                sub_p.add_argument("--json", action="store_true", help="Вывод результатов в формате JSON (для агентов)")
            sub_p.set_defaults(_handler_command=cmd_instance)
    except Exception as e:
        logger.warning(f"Не удалось загрузить динамические команды: {e}")

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    raw_args = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if "--json" in raw_args:
        setattr(args, "json", True)

    try:
        from core.commands.base import CommandError
        if hasattr(args, "_handler_command") and args._handler_command:
            cmd = args._handler_command
            res = cmd.execute(args) if hasattr(cmd, "execute") else cmd.run(args)
            if isinstance(res, int) and res != 0:
                sys.exit(res)
        else:
            parser.print_help()
    except CommandError as ce:
        if getattr(args, "json", False):
            print(json.dumps(ce.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"[CLE Error {ce.error_code}]: {ce.message}", file=sys.stderr)
            if ce.suggested_fix:
                print(f"💡 [Suggested Fix]: {ce.suggested_fix}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        suggested_fix = ""
        error_code = type(exc).__name__
        if isinstance(exc, FileNotFoundError):
            suggested_fix = "Убедитесь, что указанный файл или путь существует."
        elif isinstance(exc, PermissionError):
            suggested_fix = "Файл или ресурс заблокирован. Завершите конкурирующие процессы."
        elif isinstance(exc, TimeoutError):
            suggested_fix = "Истек таймаут ожидания операции."

        if getattr(args, "json", False):
            payload = {
                "status": "error",
                "error_code": error_code,
                "error": str(exc),
            }
            if suggested_fix:
                payload["suggested_fix"] = suggested_fix
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"[CLE Error {error_code}]: {exc}", file=sys.stderr)
            if suggested_fix:
                print(f"💡 [Suggested Fix]: {suggested_fix}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
