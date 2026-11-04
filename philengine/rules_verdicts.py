"""Golden verdicts: a small, stable baseline of every (institution, property, check) -> verdict, and its diff.

Baseline file (sorted, timing-free):
  {"format": 1, "engine_hash": rules_cache.code_hash(), "z3": ..., "params": {k, init, compliance, step_mode},
   "rows": [{"institution", "property", "check", "verdict"}, ...]}
Rows are keyed by (institution, property NAME, check), never by formal text, so two properties that share a formal
text stay two rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import z3

from . import rules_cache

FORMAT = 1
Key = tuple[str, str, str]


def rows_from_reports(reports) -> dict[Key, str]:
    return {(r.institution, x.property, x.check): x.verdict for r in reports for x in r.results}


def make_baseline(reports, *, k: int, init, compliance: str, step_mode: str) -> dict:
    rows = rows_from_reports(reports)
    return {"format": FORMAT, "engine_hash": rules_cache.code_hash(), "z3": z3.get_version_string(),
            "params": {"k": k, "init": init, "compliance": compliance, "step_mode": step_mode},
            "rows": [{"institution": i, "property": p, "check": c, "verdict": v} for (i, p, c), v in sorted(rows.items())]}


def write_baseline(path, baseline: dict) -> None:
    Path(path).write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n")


def load_baseline(path) -> dict:
    d = json.loads(Path(path).read_text())
    if d.get("format") != FORMAT or "rows" not in d or "params" not in d:
        raise ValueError(f"{path}: not a format-{FORMAT} verdict baseline")
    return d


def baseline_rows(baseline: dict) -> dict[Key, str]:
    return {(r["institution"], r["property"], r["check"]): r["verdict"] for r in baseline["rows"]}


def diff_rows(old: dict[Key, str], new: dict[Key, str]) -> dict:
    changed = [{"institution": k[0], "property": k[1], "check": k[2], "old": old[k], "new": new[k]}
               for k in sorted(old.keys() & new.keys()) if old[k] != new[k]]
    added = [{"institution": k[0], "property": k[1], "check": k[2], "verdict": new[k]} for k in sorted(new.keys() - old.keys())]
    removed = [{"institution": k[0], "property": k[1], "check": k[2], "verdict": old[k]} for k in sorted(old.keys() - new.keys())]
    total = len(new)
    return {"changed": changed, "added": added, "removed": removed, "total": total,
            "summary": f"{len(changed)} changed, {len(added)} added, {len(removed)} removed (of {total} rows)",
            "ok": not changed and not removed}


def format_diff(d: dict) -> str:
    by_inst: dict[str, list[str]] = {}
    for x in d["changed"]:
        by_inst.setdefault(x["institution"], []).append(f"  changed  {x['property']} [{x['check']}]: {x['old']} -> {x['new']}")
    for x in d["removed"]:
        by_inst.setdefault(x["institution"], []).append(f"  removed  {x['property']} [{x['check']}] (was {x['verdict']})")
    for x in d["added"]:
        by_inst.setdefault(x["institution"], []).append(f"  added    {x['property']} [{x['check']}]: {x['verdict']}")
    out = []
    for inst in sorted(by_inst):
        out.append(f"{inst}:")
        out.extend(by_inst[inst])
    out.append(d["summary"])
    return "\n".join(out)
