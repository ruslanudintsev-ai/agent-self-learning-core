"""core/commands/sys_info.py
Пример встроенной модульной команды: вывод системных метрик и загрузки ресурсов.
"""

from __future__ import annotations

import argparse
import platform
import psutil

from core.commands.base import BaseCommand


class SysInfoCommand(BaseCommand):
    name = "sys-info"
    description = "Вывод метрик сервера и загрузки ресурсов"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--disk", action="store_true", help="Включить данные по диску")

    def run(self, args: argparse.Namespace) -> int:
        payload = {
            "status": "ok",
            "os": platform.platform(),
            "cpu_usage_pct": psutil.cpu_percent(interval=0.2),
            "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 2),
        }

        if getattr(args, "disk", False):
            payload["disk_free_gb"] = round(psutil.disk_usage("/").free / (1024 ** 3), 2)

        as_json = getattr(args, "json", False)
        self.output(payload, as_json=as_json)
        return 0
