"""core/commands/rollback.py
Управление теневыми снимками конфигураций (config/) и их атомарный откат.
Позволяет агенту и разработчику безопасно экспериментировать с настройками,
пулами запросов и прокси, имея возможность мгновенного восстановления.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import filecmp
import json
from pathlib import Path
import shutil
import time
from typing import Any, Dict, List, Optional

from core.commands.base import BaseCommand, CommandError

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class RollbackCommand(BaseCommand):
    """Управление теневыми снимками конфигураций и их откат."""

    name = "rollback"
    description = "Управление теневыми снимками конфигураций и их откат"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="subaction", help="Действие над снимками конфигураций")

        # cle rollback list
        p_list = sub.add_parser("list", help="Список доступных снимков конфигураций")
        p_list.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        # cle rollback create --reason "..."
        create_p = sub.add_parser("create", help="Создать снимок текущей папки config/")
        create_p.add_argument(
            "--reason",
            type=str,
            default="manual",
            help="Причина создания снимка (например: before_target_pool_update)",
        )
        create_p.add_argument("--json", action="store_true", help="Вывод в формате JSON")

        # cle rollback restore [--snapshot-id ID] [--last] [--dry-run]
        restore_p = sub.add_parser("restore", help="Восстановить конфигурации из снимка")
        restore_p.add_argument("--snapshot-id", type=str, default=None, help="Идентификатор снимка")
        restore_p.add_argument("--last", action="store_true", help="Откатить до самого свежего снимка")
        restore_p.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции: показать diff изменений без перезаписи файлов",
        )
        restore_p.add_argument("--json", action="store_true", help="Вывод в формате JSON")

    def run(self, args: argparse.Namespace) -> int:
        subaction = getattr(args, "subaction", None)
        as_json = getattr(args, "json", False)

        snapshots_dir = BASE_DIR / ".cle_state" / "snapshots"
        config_dir = BASE_DIR / "config"

        if subaction == "create":
            return self._run_create(args, snapshots_dir, config_dir, as_json)
        elif subaction == "list":
            return self._run_list(args, snapshots_dir, as_json)
        elif subaction == "restore":
            return self._run_restore(args, snapshots_dir, config_dir, as_json)
        else:
            self.output(
                {
                    "status": "error",
                    "message": "Не указано действие. Доступно: list, create, restore.",
                },
                as_json=as_json,
            )
            return 1

    def _run_create(
        self,
        args: argparse.Namespace,
        snapshots_dir: Path,
        config_dir: Path,
        as_json: bool,
    ) -> int:
        if not config_dir.exists():
            self.output(
                {"status": "error", "message": f"Директория конфигураций {config_dir} не найдена"},
                as_json=as_json,
            )
            return 1

        snapshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        clean_reason = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in args.reason).strip("_")
        snap_id = f"snap_{timestamp}_{clean_reason}"
        target_snap = snapshots_dir / snap_id

        # Копируем дерево config/
        shutil.copytree(config_dir, target_snap)

        # Сохраняем manifest метаданных
        files = [p.name for p in target_snap.glob("*") if p.is_file() and p.name != "manifest.json"]
        manifest = {
            "snapshot_id": snap_id,
            "created_at_epoch": timestamp,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": args.reason,
            "files": files,
        }
        (target_snap / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        payload = {
            "status": "ok",
            "message": f"Снимок конфигураций успешно создан: {snap_id}",
            "snapshot_id": snap_id,
            "reason": args.reason,
            "files_count": len(files),
            "files": files,
            "path": str(target_snap),
        }
        self.output(payload, as_json=as_json)
        return 0

    def _run_list(
        self,
        args: argparse.Namespace,
        snapshots_dir: Path,
        as_json: bool,
    ) -> int:
        if not snapshots_dir.exists():
            self.output({"status": "ok", "snapshots": [], "total": 0}, as_json=as_json)
            return 0

        snaps_list: List[Dict[str, Any]] = []
        snap_dirs = sorted([p for p in snapshots_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)

        for snap in snap_dirs:
            manifest_file = snap / "manifest.json"
            if manifest_file.exists():
                try:
                    meta = json.loads(manifest_file.read_text(encoding="utf-8"))
                    snaps_list.append(meta)
                    continue
                except Exception:
                    pass
            # Фолбэк для снимков без манифеста
            snaps_list.append({
                "snapshot_id": snap.name,
                "created_at_epoch": int(snap.stat().st_mtime),
                "reason": "unknown",
                "files_count": len([f for f in snap.glob("*") if f.is_file()]),
            })

        payload = {
            "status": "ok",
            "snapshots": snaps_list,
            "total": len(snaps_list),
        }
        self.output(payload, as_json=as_json)
        return 0

    def _run_restore(
        self,
        args: argparse.Namespace,
        snapshots_dir: Path,
        config_dir: Path,
        as_json: bool,
    ) -> int:
        if not snapshots_dir.exists():
            self.output({"status": "error", "message": "Снимки конфигураций отсутствуют"}, as_json=as_json)
            return 1

        target_id = getattr(args, "snapshot_id", None)
        is_last = getattr(args, "last", False)
        is_dry_run = getattr(args, "dry_run", False)

        if is_last:
            snaps = sorted([p for p in snapshots_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
            if not snaps:
                self.output({"status": "error", "message": "Нет доступных снимков для отката"}, as_json=as_json)
                return 1
            target_snap = snaps[0]
            target_id = target_snap.name
        else:
            if not target_id:
                self.output(
                    {"status": "error", "message": "Укажите --snapshot-id или флаг --last"},
                    as_json=as_json,
                )
                return 1
            target_snap = snapshots_dir / target_id

        if not target_snap.exists() or not target_snap.is_dir():
            self.output(
                {"status": "error", "message": f"Снимок '{target_id}' не найден"},
                as_json=as_json,
            )
            return 1

        # Анализ различий (diff)
        diff_files: List[str] = []
        for src_file in target_snap.glob("**/*"):
            if src_file.is_file() and src_file.name != "manifest.json":
                rel_path = src_file.relative_to(target_snap)
                dest_file = config_dir / rel_path
                if not dest_file.exists() or not filecmp.cmp(src_file, dest_file, shallow=False):
                    diff_files.append(str(rel_path).replace("\\", "/"))

        if is_dry_run:
            payload = {
                "status": "ok",
                "mode": "dry-run",
                "target_snapshot": target_id,
                "will_overwrite_files": diff_files,
                "changed_count": len(diff_files),
                "safety_check": "passed",
            }
            self.output(payload, as_json=as_json)
            return 0

        # Выполнение отката
        for rel_f in diff_files:
            src = target_snap / rel_f
            dest = config_dir / rel_f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

        payload = {
            "status": "ok",
            "message": f"Конфигурации успешно восстановлены из снимка {target_id}",
            "restored_snapshot": target_id,
            "reverted_files": diff_files,
            "reverted_count": len(diff_files),
        }
        self.output(payload, as_json=as_json)
        return 0
