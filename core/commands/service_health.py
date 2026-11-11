"""core/commands/service_health.py
Модуль комплексной диагностики здоровья сервисов и компонентов системы.
Написан строго по регламенту .agents/rules/cle-command-authoring.md.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict

from core.commands.base import BaseCommand

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ServiceHealthCommand(BaseCommand):
    name: str = "service-health"
    description: str = "Комплексная диагностика здоровья компонентов системы"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        """Регистрация аргументов команды."""
        parser.add_argument(
            "--component",
            type=str,
            choices=["all", "disk", "python", "workspace", "commands"],
            default="all",
            help="Целевой компонент для проверки (по умолчанию 'all')",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции проверки без сетевых запросов или записи",
        )

    def run(self, args: argparse.Namespace) -> int:
        """Точка входа команды service-health."""
        as_json = getattr(args, "json", False)
        component = getattr(args, "component", "all").lower()
        is_dry_run = getattr(args, "dry_run", False)

        checks: Dict[str, Any] = {}
        all_ok = True

        # 1. Проверка дискового пространства
        if component in ("all", "disk"):
            try:
                target_disk = "C:\\" if os.name == "nt" else "/"
                total, used, free = shutil.disk_usage(target_disk)
                free_gb = round(free / (1024 ** 3), 2)
                disk_ok = free_gb >= 1.0
                checks["disk"] = {
                    "free_gb": free_gb,
                    "threshold_gb": 1.0,
                    "status": "ok" if disk_ok else "warning_low_disk",
                }
                if not disk_ok:
                    all_ok = False
            except Exception as e:
                checks["disk"] = {"status": "error", "message": str(e)}
                all_ok = False

        # 2. Проверка версии Python
        if component in ("all", "python"):
            py_ver = sys.version_info
            py_ok = (py_ver.major == 3 and py_ver.minor >= 10)
            checks["python"] = {
                "version": f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}",
                "status": "ok" if py_ok else "warning_old_version",
            }
            if not py_ok:
                all_ok = False

        # 3. Проверка доступности записи в рабочей директории
        if component in ("all", "workspace"):
            is_writable = os.access(BASE_DIR, os.W_OK)
            checks["workspace"] = {
                "path": str(BASE_DIR),
                "writable": is_writable,
                "status": "ok" if is_writable else "error_readonly",
            }
            if not is_writable:
                all_ok = False

        # 4. Проверка реестра модульных команд
        if component in ("all", "commands"):
            try:
                from core.commands import load_commands
                cmds = load_commands()
                cmds_ok = len(cmds) > 0
                checks["commands"] = {
                    "loaded_count": len(cmds),
                    "status": "ok" if cmds_ok else "warning_no_commands",
                }
                if not cmds_ok:
                    all_ok = False
            except Exception as e:
                checks["commands"] = {"status": "error", "message": str(e)}
                all_ok = False

        payload = {
            "status": "ok" if all_ok else "error",
            "component": component,
            "dry_run": is_dry_run,
            "checks": checks,
        }

        self.output(payload, as_json=as_json)
        return 0 if all_ok else 1
