"""core/commands
Пакет модульных команд для Metric QA Lab CLI (manage.py / cle).
Включает Auto-Quarantine: изоляцию сломанных плагинов в _quarantine/
для предотвращения сбоев ядра при ошибках агента.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
from pathlib import Path
import pkgutil
import shutil
import sys
import time
import traceback
from typing import Dict, List, Type

from core.commands.base import BaseCommand

logger = logging.getLogger("metricqa_cli")


def _quarantine_module(module_name: str, pkg_path: Path, error_exc: Exception) -> None:
    """Изолирует сломанный модуль в _quarantine/ с записью лога ошибки."""
    try:
        quarantine_dir = pkg_path / "_quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        src_file = pkg_path / f"{module_name}.py"
        if src_file.exists():
            dst_file = quarantine_dir / f"{module_name}.py.disabled"
            shutil.move(str(src_file), str(dst_file))

            log_file = quarantine_dir / "quarantine_log.json"
            log_data: List[dict] = []
            if log_file.exists():
                try:
                    log_data = json.loads(log_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            log_data.append({
                "module": module_name,
                "disabled_at": time.time(),
                "error": str(error_exc),
                "traceback": traceback.format_exc(),
            })
            log_file.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning(
                f"🛡️ [Auto-Quarantine] Модуль {module_name}.py изолирован в _quarantine/ из-за ошибки: {error_exc}"
            )
    except Exception as e:
        logger.warning(f"Не удалось переместить модуль в карантин {module_name}: {e}")


def load_commands(enable_quarantine: bool = False) -> Dict[str, BaseCommand]:
    """Динамически находит и инстанцирует все команды из пакета core.commands.

    По умолчанию ошибки импорта только пропускают проблемную команду: исходники
    остаются на месте. Перемещение модуля в _quarantine/ доступно только при
    явном enable_quarantine=True.
    Возвращает словарь {command_name: cmd_instance}.
    """
    discovered: Dict[str, BaseCommand] = {}
    pkg_path = Path(__file__).resolve().parent

    for _, module_name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if is_pkg or module_name.startswith("_") or module_name == "base":
            continue
        full_module_name = f"core.commands.{module_name}"
        try:
            # Сбрасываем кэш модуля, если уже был импортирован
            if full_module_name in sys.modules:
                module = importlib.reload(sys.modules[full_module_name])
            else:
                module = importlib.import_module(full_module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseCommand) and obj is not BaseCommand:
                    cmd_instance = obj()
                    if not cmd_instance.name:
                        cmd_instance.name = module_name.replace("_", "-")
                    discovered[cmd_instance.name] = cmd_instance
        except Exception as e:
            logger.warning(f"[CLE Warning] Ошибка загрузки команды '{module_name}': {e}")
            if enable_quarantine:
                _quarantine_module(module_name, pkg_path, e)

    return discovered


def discover_commands() -> Dict[str, Type[BaseCommand]]:
    """Алиас обратной совместимости, возвращает {command_name: CommandClass}."""
    instances = load_commands()
    return {name: inst.__class__ for name, inst in instances.items()}


__all__ = ["BaseCommand", "load_commands", "discover_commands"]
