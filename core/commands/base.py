"""core/commands/base.py
Базовый класс для модульных команд управления Metric QA Lab CLI (manage.py / cle).
Включает промышленные механизмы:
1. Output Budgets (защита контекста LLM от раздувания)
2. CommandError с полями error_code и suggested_fix
3. Локальные контрольные точки (.cle_state/) для длительных пакетных задач
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from typing import Any, Dict, List, Optional


def is_production_host() -> bool:
    """Проверяет, выполняется ли процесс на продакшн-ноде (по флагу окружения или хостнейму)."""
    if os.environ.get("PRODUCTION_ENVIRONMENT", "").lower() in ("1", "true", "yes"):
        return True
    prod_hosts = os.environ.get("PRODUCTION_HOSTS", "").split(",")
    if prod_hosts and any(h.strip() and h.strip().upper() in socket.gethostname().upper() for h in prod_hosts):
        return True
    return False


def assert_production_host(
    action_name: str = "production execution",
    allow_force: bool = False,
    force: bool = False,
) -> None:
    """Target Host Guard: блокирует выполнение боевых сервисов на локальной Dev-машине."""
    if is_production_host():
        return
    if allow_force and force:
        return

    curr_host = socket.gethostname()
    raise CommandError(
        message=(
            f"Execution blocked for '{action_name}': Local host ({curr_host}) is restricted to dev/dry-run. "
            f"Production operations must run on authorized production nodes or with '--dry-run'."
        ),
        error_code="ENVIRONMENT_BOUNDARY_VIOLATION",
        suggested_fix="Run locally with '--dry-run' or set PRODUCTION_ENVIRONMENT=1 on production host.",
    )


# Алиасы совместимости
is_battle_vps = is_production_host
assert_battle_vps = assert_production_host


class CommandError(Exception):
    """Исключение команды с машинно-читаемой подсказкой для самоисцеления LLM."""

    def __init__(
        self,
        message: str,
        error_code: str = "EXECUTION_FAILED",
        suggested_fix: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.suggested_fix = suggested_fix
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "error",
            "error_code": self.error_code,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "details": self.details,
        }


class BaseCommand(ABC):
    """Базовый абстрактный класс для всех команд CLI."""

    name: str = ""
    description: str = ""
    help: str = ""

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        """Настройка аргументов для команды."""
        self.add_arguments(parser)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Алиас/совместимость для configure_parser."""
        pass

    def execute(self, args: argparse.Namespace) -> int:
        """Точка входа с автоматическим замером времени, телеметрией RAM и Shadow Assertions."""
        self._start_perf = time.perf_counter()
        try:
            import psutil
            self._proc = psutil.Process()
            self._start_mem_mb = self._proc.memory_info().rss / (1024 * 1024)
        except Exception:
            self._proc = None
            self._start_mem_mb = 0.0

        try:
            res = self.run(args)
            return res if isinstance(res, int) else 0
        finally:
            self._shadow_warnings = self.check_shadow_assertions()

    def check_shadow_assertions(self) -> List[Dict[str, Any]]:
        """Теневой аудит инвариантов здоровья системы после завершения команды."""
        warnings: List[Dict[str, Any]] = []
        base_dir = Path(__file__).resolve().parent.parent.parent

        # 1. Инвариант: отсутствие заблокированных профилей при отсутствии активной сессии
        flag_file = base_dir / "audit_in_progress.flag"
        profiles_dir = base_dir / "browser_profiles"
        if not flag_file.exists() and profiles_dir.exists():
            locked = []
            lock_names = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", "LOCK")
            for p in profiles_dir.glob("profile_*"):
                if not p.is_dir():
                    continue
                if any((p / l).exists() for l in lock_names):
                    locked.append(p.name)
            if locked:
                warnings.append({
                    "invariant": "no_stale_profile_locks",
                    "severity": "warning",
                    "issue": f"Обнаружены остаточные lock-файлы без активного аудита: {', '.join(locked[:3])}",
                    "auto_remedy": "cle sessions clear",
                })

        # 2. Инвариант: отсутствие оторванных процессов Chrome автоматизации
        if not flag_file.exists():
            try:
                import psutil
                orphan_pids = []
                for p in psutil.process_iter(["name", "cmdline"]):
                    try:
                        p_name = (p.info.get("name") or "").lower()
                        if "chrome" in p_name or "chromium" in p_name:
                            cmdline = " ".join(p.info.get("cmdline") or [])
                            if any(marker in cmdline for marker in ("browser_profiles", "--headless", "--remote-debugging-port", "patchright")):
                                orphan_pids.append(p.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if orphan_pids:
                    warnings.append({
                        "invariant": "no_orphan_browsers",
                        "severity": "warning",
                        "issue": f"Обнаружено {len(orphan_pids)} оторванных процессов автоматизации Chrome",
                        "auto_remedy": "cle sessions clear",
                    })
            except Exception:
                pass

        # 3. Инвариант: дисковое пространство C: >= 2.0 ГБ
        try:
            target_disk = "C:\\" if os.name == "nt" else "/"
            total, used, free = shutil.disk_usage(target_disk)
            free_gb = round(free / (1024 ** 3), 2)
            if free_gb < 2.0:
                warnings.append({
                    "invariant": "disk_space_healthy",
                    "severity": "critical",
                    "issue": f"Критически мало места на диске C:: {free_gb} ГБ (порог 2.0 ГБ)",
                    "auto_remedy": "cle clean-cache",
                })
        except Exception:
            pass

        return warnings

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int:
        """Основная логика выполнения. Возвращает exit code (0 - успех)."""
        pass

    def output(
        self,
        data: Dict[str, Any],
        as_json: bool = False,
        max_items: int = 50,
        max_str_len: int = 5000,
    ) -> None:
        """Унифицированный вывод для человека или агента с защитой контекстного окна (Output Budgeting)."""
        processed_data = self._apply_output_budgets(data, max_items=max_items, max_str_len=max_str_len)

        # Автоматическая инъекция телеметрии при вызове с as_json=True
        if as_json and isinstance(processed_data, dict):
            elapsed = time.perf_counter() - getattr(self, "_start_perf", time.perf_counter())
            cur_mem = 0.0
            if getattr(self, "_proc", None):
                try:
                    cur_mem = round(self._proc.memory_info().rss / (1024 * 1024), 2)
                except Exception:
                    pass
            processed_data["_telemetry"] = {
                "duration_sec": round(elapsed, 3),
                "duration_ms": round(elapsed * 1000, 1),
                "ram_used_mb": cur_mem,
            }

        # Автоматическая инъекция теневых предупреждений
        shadow_warnings = getattr(self, "_shadow_warnings", None)
        if shadow_warnings is None:
            shadow_warnings = self.check_shadow_assertions()

        if shadow_warnings and isinstance(processed_data, dict):
            processed_data["_system_health_warning"] = shadow_warnings

        if as_json:
            print(json.dumps(processed_data, indent=2, ensure_ascii=False))
        else:
            if "message" in processed_data:
                print(processed_data["message"])
            for k, v in processed_data.items():
                if k not in ("message", "_system_health_warning"):
                    if isinstance(v, list):
                        print(f"  {k} ({len(v)} элементов):")
                        for item in v:
                            print(f"    - {item}")
                    elif isinstance(v, dict):
                        print(f"  {k}:")
                        for sub_k, sub_v in v.items():
                            print(f"    {sub_k}: {sub_v}")
                    else:
                        print(f"  {k}: {v}")

            if shadow_warnings:
                print("\n⚠️  [Shadow Assertions Alert]:")
                for w in shadow_warnings:
                    print(f"  - [{w['invariant']}]: {w['issue']}")
                    print(f"    💡 Рекомендация: {w['auto_remedy']}")

    def _apply_output_budgets(
        self,
        data: Any,
        max_items: int = 50,
        max_str_len: int = 5000,
    ) -> Any:
        """Рекурсивно усекает длинные массивы и многокилобайтные строки для защиты контекста LLM."""
        if isinstance(data, list):
            return [
                self._apply_output_budgets(item, max_items=max_items, max_str_len=max_str_len)
                for item in data[:max_items]
            ]

        if isinstance(data, str) and len(data) > max_str_len:
            excess = len(data) - max_str_len
            return data[:max_str_len] + f"\n... [TRUNCATED {excess} chars by Output Budget. Use specific query/slice] ..."

        if isinstance(data, dict):
            out: Dict[str, Any] = {}
            has_truncation = False
            truncation_meta: List[Dict[str, Any]] = []

            for key, val in data.items():
                if isinstance(val, list) and len(val) > max_items:
                    has_truncation = True
                    total_len = len(val)
                    sliced = [
                        self._apply_output_budgets(item, max_items=max_items, max_str_len=max_str_len)
                        for item in val[:max_items]
                    ]
                    out[key] = sliced
                    truncation_meta.append({
                        "field": key,
                        "total_count": total_len,
                        "shown_count": max_items,
                    })
                else:
                    out[key] = self._apply_output_budgets(val, max_items=max_items, max_str_len=max_str_len)

            if has_truncation:
                out["truncated"] = True
                out["_budget_notice"] = {
                    "details": truncation_meta,
                    "hint": "Use --limit, --offset or specific filters to paginate results.",
                }
            return out

        return data

    # =====================================================================
    # ЧЕКПОИНТЫ И СТЕЙТ ДЛЯ ДЛИТЕЛЬНЫХ ЗАДАЧ (.cle_state/)
    # =====================================================================
    def get_state_dir(self) -> Path:
        """Путь к директории сохранения состояния команды."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        state_dir = base_dir / ".cle_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    def save_checkpoint(
        self,
        checkpoint_name: str,
        payload: Dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        """Сохранение контрольной точки с метаданными времени создания и TTL (по умолчанию 24ч)."""
        envelope = {
            "_meta": {
                "command": self.name or self.__class__.__name__,
                "checkpoint_name": checkpoint_name,
                "created_at": time.time(),
                "ttl_seconds": ttl_seconds,
            },
            "data": payload,
        }
        state_file = self.get_state_dir() / f"{self.name or self.__class__.__name__}_{checkpoint_name}.json"
        state_file.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_checkpoint(self, checkpoint_name: str, check_ttl: bool = True) -> Optional[Dict[str, Any]]:
        """Загрузка контрольной точки с проверкой TTL (срок годности по умолчанию 24ч)."""
        state_file = self.get_state_dir() / f"{self.name or self.__class__.__name__}_{checkpoint_name}.json"
        if not state_file.exists():
            return None
        try:
            raw = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "_meta" in raw and "data" in raw:
                meta = raw["_meta"]
                created_at = meta.get("created_at", 0)
                ttl = meta.get("ttl_seconds", 86400)
                if check_ttl and (time.time() - created_at > ttl):
                    # Чекпоинт протух по TTL
                    return None
                return raw["data"]
            return raw
        except Exception:
            return None

    def clear_checkpoint(self, checkpoint_name: str) -> None:
        """Удаление контрольной точки после успешного завершения цепочки."""
        state_file = self.get_state_dir() / f"{self.name or self.__class__.__name__}_{checkpoint_name}.json"
        state_file.unlink(missing_ok=True)

    @classmethod
    def list_all_checkpoints(cls) -> List[Dict[str, Any]]:
        """Возвращает список всех контрольных точек в .cle_state/ с возрастом и статусом TTL."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        state_dir = base_dir / ".cle_state"
        if not state_dir.exists():
            return []
        checkpoints: List[Dict[str, Any]] = []
        now = time.time()
        for f in sorted(state_dir.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                created_at = f.stat().st_mtime
                ttl = 86400
                data_payload = raw
                if isinstance(raw, dict) and "_meta" in raw:
                    created_at = raw["_meta"].get("created_at", created_at)
                    ttl = raw["_meta"].get("ttl_seconds", ttl)
                    data_payload = raw.get("data", {})

                age_sec = max(0.0, now - created_at)
                age_hours = round(age_sec / 3600, 1)
                is_expired = age_sec > ttl

                checkpoints.append({
                    "file": f.name,
                    "task_name": f.stem,
                    "size_bytes": f.stat().st_size,
                    "age_hours": age_hours,
                    "ttl_hours": round(ttl / 3600, 1),
                    "is_expired": is_expired,
                    "data": data_payload,
                })
            except Exception:
                checkpoints.append({
                    "file": f.name,
                    "task_name": f.stem,
                    "corrupted": True,
                })
        return checkpoints

    @classmethod
    def prune_checkpoints(cls, max_age_hours: float = 24.0) -> List[str]:
        """Удаляет протухшие контрольные точки старше указанного возраста."""
        base_dir = Path(__file__).resolve().parent.parent.parent
        state_dir = base_dir / ".cle_state"
        if not state_dir.exists():
            return []
        now = time.time()
        pruned = []
        for f in state_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                created_at = f.stat().st_mtime
                if isinstance(raw, dict) and "_meta" in raw:
                    created_at = raw["_meta"].get("created_at", created_at)
                if (now - created_at) > (max_age_hours * 3600):
                    f.unlink(missing_ok=True)
                    pruned.append(f.name)
            except Exception:
                pass
        return pruned
