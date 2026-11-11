# Agent Self-Learning Core (CLE)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Ad-Hoc Scripts](https://img.shields.io/badge/Policy-Zero--Ad--Hoc-success)](.agents/rules/agent-core.md)
[![Tests Passing](https://img.shields.io/badge/Tests-25%2F25%20Passing-brightgreen)](tests/)

**Промышленная самообучающаяся архитектура для автономных AI-агентов** (Google Antigravity, OpenCode, Claude Code, Cursor, Codex).

Вместо засорения проекта одноразовыми скриптами (`temp.py`, `test1.py`) и раздувания контекста LLM бесконечными логами, агент работает через строго типизированный слой команд **Command Layer Engine (CLE)**, непрерывно накапливает процедурную память и расширяет собственный арсенал CLI в процессе выполнения задач.

---

## 🧬 Архитектура: 4 фундаментальных закона агента

1. **Единая точка входа (Zero Ad-Hoc Scripts):**  
   Любые вычисления, тесты и системные действия выполняются **ТОЛЬКО** через `cle` (`python manage.py <command>`). Одноразовые скрипты в корне запрещены. Для расчетов на лету используется `cle exec --code "..."`.
2. **Экономия контекста (Доверяй CLI):**  
   Если штатная команда вернула структурированный вывод (`--json`), агенту **запрещено** перечитывать `.py` исходники реализации. *Один вопрос = один вызов CLI*.
3. **Точечная память граблей (Gotchas on Demand):**  
   Ошибки окружения, блокировки SQLite, таймауты и специфика ОС фиксируются по канонической схеме (*Симптом $\to$ Первопричина $\to$ Решение*) в `.agents/skills/agent-cli/gotchas.md`.
4. **Изоляция сред (Environment Boundary):**  
   Локальная машина разработчика — Dev/Dry-run среда. Боевые деструктивные запуски на Dev блокируются встроенным **Target Host Guard** (`assert_production_host()`).

---

## 🔄 Цикл самообучения (Self-Refining Loop)

```
[Поступила задача пользователя]
             │
             ▼
      [Выполнение через CLE]
             │
      ┌──────┴─────────────────────────────────┐
      │ Успех                                  │ Ошибка / нехватка функции
      ▼                                        ▼
[Post-Run Reflection]              1. cle dev-scaffold --command <name>
- Фиксация удачного паттерна       2. Реализация логики в core/commands/
- Запись рецепта в SKILL.md        3. cle dev-validate --file core/commands/<name>.py
                                   4. cle system-docgen --json
                                   5. Запись граблей в gotchas.md
```

---

## 🚀 Инструкция по установке в существующий проект

Подключить самообучающееся ядро к любому вашему проекту можно за 1 минуту:

### 1. Клонируйте репозиторий
```bash
git clone https://github.com/ruslanudintsev-ai/agent-self-learning-core.git
```

### 2. Скопируйте ядро в корень вашего проекта
Перенесите в корень вашего целевого репозитория следующие компоненты:
```text
Ваш-Проект/
├── .agents/          # Правила и процедурная память агента
├── core/             # Диспетчер CLE и базовые команды
├── manage.py         # Главная точка входа CLI
├── cle, cle.cmd      # Быстрые консольные вызовы
└── tests/            # Набор compliance-тестов
```

*(Команда для терминала Linux / macOS)*:
```bash
cp -r agent-self-learning-core/.agents /путь/к/вашему/проекту/
cp -r agent-self-learning-core/core /путь/к/вашему/проекту/
cp agent-self-learning-core/manage.py /путь/к/вашему/проекту/
cp agent-self-learning-core/cle* /путь/к/вашему/проекту/
```

*(Команда для Windows PowerShell)*:
```powershell
Copy-Item -Recurse agent-self-learning-core\.agents \путь\к\проекту\
Copy-Item -Recurse agent-self-learning-core\core \путь\к\проекту\
Copy-Item agent-self-learning-core\manage.py \путь\к\проекту\
Copy-Item agent-self-learning-core\cle.* \путь\к\проекту\
```

### 3. Проверьте запуск
```bash
# Диагностика
python manage.py sys-info --json

# Автогенерация справочника команд
python manage.py system-docgen --json

# Запуск тестов соответствия
pytest tests/ -v
```

---

## 🛠️ Базовый арсенал команд (CLE)

| Команда | Назначение |
| :--- | :--- |
| **`cle dev-scaffold`** | Автоматическая генерация канонического шаблона новой команды и pytest-тестов. |
| **`cle dev-validate`** | Pre-commit AST-валидатор модулей на соответствие PEP8, контракту `BaseCommand` и запрет прямых `print()`. |
| **`cle system-docgen`** | Интроспекция реестра CLI и автогенерация Markdown-справочника в `.agents/skills/agent-cli/SKILL.md`. |
| **`cle exec`** | Безопасный Python-интерпретатор выражений на лету без создания мусорных ad-hoc скриптов. |
| **`cle rollback`** | Транзакционные снимки конфигураций и мгновенный откат изменений с поддержкой `--dry-run`. |
| **`cle sys-info`** | Диагностика хоста (CPU, RAM, диск, ОС, версия Python). |
| **`cle service-health`** | Проверка здоровья компонентов системы и готовности к работе. |

Все команды поддерживают глобальный флаг **`--json`** для интеграции с агентами и защищены механизмом **Output Budgeting** (аппаратное ограничение до 12 КБ для защиты контекстного окна LLM).

---

## 🚀 Быстрый старт

### Запуск CLI
```bash
# Windows (через wrapper или python)
cle sys-info --json
python manage.py service-health --dry-run --json

# Linux / macOS
./cle sys-info --json
```

### Запуск тестов
```bash
pytest tests/ -v
# 25 passed in <1s
```

---

## 📁 Структура репозитория

```text
agent-self-learning-core/
├── .agents/
│   ├── rules/
│   │   ├── agent-core.md              # Фундаментальные законы взаимодействия и Zero Ad-Hoc
│   │   ├── cle-command-authoring.md   # Канонический стандарт создания команд-плагинов
│   │   └── self-learning.md           # Протокол рефлексии (Post-Task Reflection)
│   └── skills/
│       ├── agent-cli/
│       │   ├── SKILL.md               # Автосгенерированный справочник интерфейса
│       │   ├── changelog.md           # Журнал эволюции CLI
│       │   └── gotchas.md             # Процедурная память граблей и решений
│       └── self-improvement/
│           └── SKILL.md               # Мета-скилл самосовершенствования
├── core/
│   ├── cli.py                         # Динамический маршрутизатор команд
│   └── commands/
│       ├── base.py                    # BaseCommand, OutputBudget, Target Host Guard
│       ├── dev_scaffold.py            # Генератор команд и тестов
│       ├── dev_validate.py            # Pre-commit валидатор
│       ├── system_docgen.py           # Документатор SKILL.md
│       ├── exec.py                    # Zero-Context интерпретатор
│       ├── rollback.py                # Снимки и откат конфигураций
│       ├── sys_info.py                # Системные метрики
│       └── service_health.py          # Диагностика здоровья
├── tests/                             # Полный набор unit-тестов и compliance проверок
├── cle, cle.cmd, cle.ps1              # Кроссплатформенные CLI-врапперы
├── manage.py                          # Главная точка входа
└── README.md
```
