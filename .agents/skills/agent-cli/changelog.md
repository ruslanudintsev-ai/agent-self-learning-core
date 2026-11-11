# Журнал эволюции CLI команд и скилов (Changelog)

Фиксирует добавление новых команд-плагинов, обновление интерфейсов и расширение функционала агента.

---

### [1.0.0] — 2026-11-11
- **Ядро Command Layer Engine (CLE):**
  - Реализован маршрутизатор команд `core/cli.py` и `manage.py` с поддержкой алиасов `cle.cmd`, `cle.ps1`, `cle`.
  - Реализован `BaseCommand` с защитой контекста (Output Budgeting 12 KB), телеметрией (CPU/RAM/время) и Target Host Guard.
- **Инструменты самообучения (Self-Refining Loop):**
  - `cle dev-scaffold`: автоматическая генерация канонических шаблонов новых команд с тестами.
  - `cle dev-validate`: pre-commit валидатор AST, PEP8 и запрета `print` в пользу структурированного логгера.
  - `cle system-docgen`: автогенерация документации и Markdown-таблиц в `SKILL.md`.
  - `cle exec`: безопасный интерпретатор выражений на лету без создания мусорных ad-hoc скриптов.
  - `cle rollback`: создание транзакционных снимков конфигураций и мгновенный откат с поддержкой `--dry-run`.
  - `cle sys-info` & `cle service-health`: системная диагностика окружения и статуса сервисов.
- **Правила и ДНК Агента (.agents/rules/):**
  - `agent-core.md`: закон Zero Ad-Hoc Scripts, экономия контекста, изоляция сред.
  - `self-learning.md`: протокол рефлексии Post-Task Audit и Definition of Done.
  - `cle-command-authoring.md`: строгие стандарты разработки новых модулей.
