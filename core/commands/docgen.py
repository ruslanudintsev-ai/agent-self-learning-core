"""core/commands/docgen.py
Алиас для system-docgen.
"""

from __future__ import annotations

import argparse
from core.commands.system_docgen import SystemDocgenCommand


class DocgenCommand(SystemDocgenCommand):
    name: str = "docgen"
    description: str = "Автогенерация SKILL.md (алиас для system-docgen)"
