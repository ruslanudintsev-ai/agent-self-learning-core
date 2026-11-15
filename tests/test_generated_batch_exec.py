"""Тесты для команды batch-exec (Code Mode Batch Orchestrator)."""

from __future__ import annotations

import json
import pytest
from core.cli import build_parser, main
from core.commands.batch_exec import BatchExecCommand


class TestBatchExecCommand:
    """Набор тестов для команды batch-exec."""

    def test_batch_exec_registration(self):
        """Проверка регистрации в основном парсере."""
        parser = build_parser()
        subparser_action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
        assert "batch-exec" in subparser_action.choices

    def test_batch_exec_dry_run_success(self, capsys):
        """Проверка валидации синтаксиса в режиме --dry-run."""
        main(["batch-exec", "--script", "x = 1 + 2; result = x * 10", "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("status") == "ok"
        assert data.get("mode") == "dry-run"
        assert data.get("syntax_check") == "passed"

    def test_batch_exec_dry_run_syntax_error(self, capsys):
        """Проверка обнаружения синтаксических ошибок в режиме --dry-run."""
        with pytest.raises(SystemExit) as exc_info:
            main(["batch-exec", "--script", "def invalid syntax :(", "--dry-run", "--json"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("status") == "error"
        assert data.get("mode") == "dry-run"
        assert data.get("syntax_check") == "failed"

    def test_batch_exec_execution(self, capsys):
        """Проверка фактического выполнения и возврата результата."""
        main(["batch-exec", "--script", "result = {'sum': 10 + 20, 'name': 'test'}", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("status") == "ok"
        assert data.get("result") == {"sum": 30, "name": "test"}

    def test_batch_exec_context_availability(self, capsys):
        """Проверка доступности контекста ctx и хелперов."""
        main(["batch-exec", "--script", "result = hasattr(ctx, 'http_get') and hasattr(ctx, 'check_ssl')", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("status") == "ok"
        assert data.get("result") is True
