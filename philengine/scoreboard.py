"""Append-only markdown scoreboard: one table, one row per run (`--scoreboard PATH`).

append_row(path, row) writes the header when the file is absent or empty, then one row. `row` is a dict keyed by
column name; missing columns render as "-". Columns are chosen by `kind` ("rules": check-all / diff; "ablate").
A file holds one table, so a file is tied to one kind; appending a different kind's row to it raises ValueError.
"""
from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path

RULES_COLUMNS = ("date", "engine", "command", "rows", "verdict_changes", "z3_unknowns", "wall_s", "inconsistent")
ABLATE_COLUMNS = ("date", "engine", "command", "entries", "rows", "uncounted", "inconsistent_after",
                  "k_disagreements", "top_rule_changes", "goods_rows", "contested_readings")
KINDS = {"rules": RULES_COLUMNS, "ablate": ABLATE_COLUMNS}


def engine_commit(repo: Path | str | None = None) -> str:
    """`git rev-parse --short HEAD`, or `dirty+<sha>` if the tree has uncommitted changes, or `unknown`."""
    cwd = str(repo or Path(__file__).resolve().parent)
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"dirty+{sha}" if dirty else sha


def today() -> str:
    return _dt.date.today().isoformat()


def _cell(v) -> str:
    return "-" if v is None or v == "" else str(v).replace("|", "\\|").replace("\n", " ")


def append_row(path, row: dict, kind: str = "rules") -> None:
    cols = KINDS[kind]
    p = Path(path)
    head = "| " + " | ".join(cols) + " |"
    existing = p.read_text() if p.exists() else ""
    if existing.strip():
        first = existing.splitlines()[0]
        if first != head:
            raise ValueError(f"{p}: existing table header does not match kind {kind!r}")
        if not existing.endswith("\n"):
            existing += "\n"
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = head + "\n|" + "|".join(" --- " for _ in cols) + "|\n"
    line = "| " + " | ".join(_cell(row.get(c)) for c in cols) + " |\n"
    p.write_text(existing + line)
