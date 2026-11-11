"""Subprocess worker for executing user-supplied CLE snippets."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.commands.exec import BASE_DIR, ProjectConfig, _sanitize_for_json


def main() -> int:
    request = json.load(sys.stdin)
    code_str = request["code"]
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    scope: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "Path": Path,
        "json": json,
        "os": os,
        "sys": sys,
        "time": time,
        "datetime": datetime,
        "timezone": timezone,
        "config": ProjectConfig(BASE_DIR),
        "BASE_DIR": BASE_DIR,
        "result": None,
    }

    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                compiled = compile(code_str, "<cle-exec>", "eval")
                scope["result"] = eval(compiled, scope)
            except SyntaxError:
                compiled = compile(code_str, "<cle-exec>", "exec")
                exec(compiled, scope)

        payload = {
            "status": "ok",
            "result": _sanitize_for_json(scope.get("result")),
            "stdout": stdout_buf.getvalue().strip() or None,
            "stderr": stderr_buf.getvalue().strip() or None,
        }
        exit_code = 0
    except Exception as exc:
        payload = {
            "status": "error",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
            "stdout": stdout_buf.getvalue().strip() or None,
            "stderr": stderr_buf.getvalue().strip() or None,
        }
        exit_code = 1

    sys.__stdout__.write(json.dumps(payload, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
