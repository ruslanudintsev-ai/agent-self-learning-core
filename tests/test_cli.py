"""tests/test_cli.py
Unit tests for Command Layer Engine (manage.py & core.cli).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pytest
from unittest.mock import patch

from core.cli import build_parser, main
from core.commands import load_commands


class TestCLECore:
    def test_dynamic_commands_discovery(self):
        """Проверяет, что все модули из core/commands/ обнаруживаются динамически."""
        commands = load_commands()
        assert "dev-scaffold" in commands
        assert "dev-validate" in commands
        assert "system-docgen" in commands
        assert "exec" in commands
        assert "rollback" in commands
        assert "sys-info" in commands

    def test_parser_subcommands_registration(self):
        """Проверяет регистрацию подкоманд в ArgumentParser."""
        commands = load_commands()
        parser = build_parser()
        for cmd in ["dev-scaffold", "dev-validate", "system-docgen", "exec", "rollback", "sys-info"]:
            assert cmd in commands

    def test_exec_eval_json(self, capsys):
        """Проверяет выполнение вычисления через exec --code в формате JSON."""
        parser = build_parser()
        args = parser.parse_args(["exec", "--code", "10 + 25", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert data["result"] == 35

    def test_exec_timeout_stops_running_code(self, capsys):
        """Ensure exec terminates a non-terminating snippet at its timeout."""
        parser = build_parser()
        args = parser.parse_args(["exec", "--code", "while True: pass", "--timeout", "1", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert ret == 1
        assert data["status"] == "error"
        assert data["error_type"] == "TimeoutExpired"
        assert data["timeout_sec"] == 1

    def test_sys_info_json(self, capsys):
        """Проверяет сбор системной информации через sys-info --json."""
        parser = build_parser()
        args = parser.parse_args(["sys-info", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert "os" in data
        assert "cpu_usage_pct" in data
        assert "ram_used_mb" in data

    def test_docgen_dry_run_json(self, capsys):
        """Проверяет генерацию документации в режиме dry-run."""
        parser = build_parser()
        args = parser.parse_args(["system-docgen", "--dry-run", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert data["mode"] == "dry-run"
        assert data["commands_count"] >= 6
        assert "### `cle dev-scaffold`" in data["markdown_preview"]
        assert str(Path(__file__).resolve().parents[1]) not in data["markdown_preview"]

    def test_docgen_redacts_absolute_defaults_outside_project(self):
        """Absolute defaults outside the project must not leak into generated docs."""
        from core.commands.system_docgen import SystemDocgenCommand

        parser = argparse.ArgumentParser()
        parser.add_argument("--private-path", default=str(Path.home() / "private-workspace"))
        actions = SystemDocgenCommand()._extract_actions(parser)

        assert actions[0]["default"] == "<absolute path>"

    def test_rollback_list_json(self, capsys):
        """Проверяет получение списка снимков отката."""
        parser = build_parser()
        args = parser.parse_args(["rollback", "list", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert "snapshots" in data

    def test_dev_validate_self(self, capsys):
        """Проверяет валидацию собственного модуля через dev-validate."""
        parser = build_parser()
        args = parser.parse_args(["dev-validate", "--file", "core/commands/exec.py", "--json"])
        cmd = args._handler_command
        ret = cmd.run(args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert data["verdict"] == "PASSED_COMPLIANCE"
