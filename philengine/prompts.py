"""Versioned prompt files: prompts/<name>.<version>.md, `{{ var }}` substitution, no jinja.

A prompt file has two sections introduced by the lines `=== SYSTEM ===` and `=== USER ===`.
"""
from __future__ import annotations

import re

from . import config


def load(name: str, version: str = "v1") -> str:
    p = config.PROMPTS_DIR / f"{name}.{version}.md"
    if not p.is_file():
        raise FileNotFoundError(f"prompt not found: {p}")
    return p.read_text()


def render(template: str, **vars) -> str:
    def sub(m):
        k = m.group(1)
        if k not in vars:
            raise KeyError(f"prompt variable {k!r} not supplied")
        return str(vars[k])
    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", sub, template)


def split(template: str) -> tuple[str, str]:
    """-> (system, user)."""
    m = re.search(r"^=== SYSTEM ===\n(.*?)^=== USER ===\n(.*)\Z", template, re.S | re.M)
    if not m:
        raise ValueError("prompt needs '=== SYSTEM ===' and '=== USER ===' sections")
    return m.group(1).strip(), m.group(2).strip()


def load_split(name: str, version: str = "v1", **vars) -> tuple[str, str]:
    return split(render(load(name, version), **vars))
