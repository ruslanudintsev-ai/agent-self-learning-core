---
trigger: model_decision
description: "Стандарты разработки, структуры и валидации новых команд-плагинов в core/commands/"
---

# Регламент создания модулей CLE (`core/commands/`)

При необходимости автоматизировать операцию или создать новую функцию, создание временных скриптов в корне или во временных папках СТРОГО ЗАПРЕЩЕНО. Любой новый функционал оформляется как постоянный плагин в директории `core/commands/`.

---

## 1. Конвенции именования и размещения

- **Путь:** только `core/commands/<command_name>.py`. Поддиректории не создавать.
- **Имя файла:** `snake_case` (например, `db_vacuum.py`, `service_health.py`).
- **Имя класса:** `PascalCase` с суффиксом `Command` (например, `DbVacuumCommand`, `ServiceHealthCommand`).
- **Свойство `name`:** `kebab-case` (например, `db-vacuum`, `service-health`), совпадает с вызовом из CLI: `cle service-health` или `python manage.py service-health`.

---

## 2. Обязательный канонический шаблон

Каждый файл в `core/commands/` обязан строго воспроизводить следующую структуру без отклонений от интерфейса `BaseCommand`:

```python
import argparse
from typing import Any, Dict
from core.commands.base import BaseCommand


class ExampleActionCommand(BaseCommand):
    name: str = "example-action"
    description: str = "Краткое и точное описание действия команды"

    def configure_parser(self, parser: argparse.ArgumentParser) -> None:
        """Регистрация аргументов.

        Обязательно указывать help для каждого аргумента.
        """
        parser.add_argument(
            "--target",
            type=str,
            required=True,
            help="Целевой идентификатор или путь",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Режим симуляции без внесения изменений",
        )

    def run(self, args: argparse.Namespace) -> int:
        """Точка входа команды.

        Возвращает 0 при успехе, ненулевой код при ошибке.
        """
        # 1. Защитная валидация входных данных
        if not args.target.strip():
            self.output(
                {"status": "error", "message": "Параметр --target не может быть пустым"},
                as_json=getattr(args, "json", False),
            )
            return 1

        # 2. Логика выполнения
        result_payload: Dict[str, Any] = {
            "status": "ok",
            "target": args.target,
            "dry_run": args.dry_run,
            "affected_items": 0,
        }

        # 3. Унифицированный вывод через self.output
        self.output(result_payload, as_json=getattr(args, "json", False))
        return 0
```

---

## 3. Критические требования к коду

1. **Запрет прямого `print()`:**
   - Весь вывод данных обязан производиться ИСКЛЮЧИТЕЛЬНО через `self.output(data_dict, as_json=getattr(args, "json", False))`.
   - Запрещено использовать `print()` или логгеры, ломающие JSON-вывод в `stdout`.

2. **Защита контекста (Output Budgets):**
   - Не возвращать гигантские нефильтрованные списки. Базовый метод `self.output()` автоматически усекает массивы длиннее 50 элементов, добавляя `_budget_notice` с общим количеством и подсказкой сузить фильтр.

3. **Формат полезной нагрузки (`payload`):**
   - Словарь для `self.output` всегда должен содержать ключ `"status"` со значением `"ok"` или `"error"`.

4. **Безопасные режимы (Safety First & Smart Dry-Run):**
   - Любая деструктивная операция (удаление файлов, очистка таблиц, останов процессов) ОБЯЗАНА поддерживать флаг `--dry-run` (или `--plan`), возвращая точный манифест предстоящих изменений:
     `{"status": "ok", "mode": "plan", "targets": [...], "safety_check": "passed"}`.

5. **Обработка исключений и Self-Healing:**
   - Не глушить ошибки через `except: pass`. Выбрасывать `CommandError(message, error_code, suggested_fix)` с понятной подсказкой, как устранить ошибку.

---

## 4. Обязательный цикл валидации перед сдачей

После написания или модификации файла в `core/commands/` агент ОБЯЗАН выполнить три шага верификации в терминале:

1. **Автоматический аудит и pre-commit валидация:**
   ```bash
   cle dev-validate --file core/commands/<имя_файла>.py
   ```

2. **Тестовый прогон в JSON-режиме:**
   ```bash
   cle <command-name> --help
   cle <command-name> [тестовые_аргументы] --json
   ```

3. **Синхронизация документации (Doc-Sync):**
   ```bash
   cle docgen
   ```

Только после успешного завершения всех 3 шагов задача считается решенной, а новая команда — принятой в эксплуатацию.
