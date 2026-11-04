"""Content-addressed cache for rule-check results (`phil rules check|check-all`; `phil rules cache stats|clear`).

One small JSON file per entry under `<runs>/rules-cache/<sha256>.json` (runs/ is gitignored). Two entry kinds:
  property     one PropertyResult (verdict, trace, vacuity flags, reason) for (institution, property, check)
  institution  the per-institution findings: consistent, deontic conflicts, inert rules, lowering warnings, resolved init
The key is the sha256 of canonical JSON of: the institution, the property's formal text (empty for an institution
entry), the check kind, k, step_mode, init mode, compliance mode, z3 version, solver settings (seed / timeout /
retry), CACHE_SCHEMA, and a hash of the source of rules_lower.py, rules_reference.py, rules_checks.py and sexpr.py,
so a change to the lowering or the check logic invalidates every entry automatically.
Results in which z3 answered `unknown` (timeouts) are never stored.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import z3

from . import config

CACHE_SCHEMA = 1
CODE_FILES = ("rules_lower.py", "rules_reference.py", "rules_checks.py", "sexpr.py")
INSTITUTION_KIND = "institution"
PROPERTY_KIND = "property"


@lru_cache(maxsize=1)
def code_hash() -> str:
    h = hashlib.sha256()
    here = Path(__file__).parent
    for name in CODE_FILES:
        p = here / name
        h.update(name.encode() + b"\0")
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def make_key(inst, *, entry: str, formal: str = "", check: str = "", k: int, step_mode: str, init: str,
             compliance: str, timeout_ms: int | None = None, retry_unknown: bool = True,
             z3_version: str | None = None, code: str | None = None, schema: int | None = None) -> str:
    """sha256 over every component that can change a result (the keyword overrides exist for tests)."""
    parts = {
        "schema": CACHE_SCHEMA if schema is None else schema,
        "code": code_hash() if code is None else code,
        "z3": z3.get_version_string() if z3_version is None else z3_version,
        "entry": entry,
        "institution": inst.model_dump(mode="json"),
        "formal": formal,
        "check": check,
        "k": k,
        "step_mode": step_mode,
        "init": init,
        "compliance": compliance,
        "solver": [config.Z3_SEED, config.Z3_TIMEOUT_MS if timeout_ms is None else timeout_ms,
                   config.Z3_RETRY_FACTOR, bool(retry_unknown)],
    }
    return hashlib.sha256(canonical(parts).encode()).hexdigest()


class RuleCache:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else config.runs_dir() / "rules-cache"
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str, count: bool = True) -> dict | None:
        try:
            d = json.loads(self._path(key).read_text())
            if d.get("schema") != CACHE_SCHEMA or d.get("key") != key:
                raise ValueError("stale entry")
            payload = d["payload"]
        except (OSError, ValueError, KeyError):
            if count:
                self.misses += 1
            return None
        if count:
            self.hits += 1
        return payload

    def put(self, key: str, kind: str, payload: dict) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = self._path(key).with_suffix(".tmp")
            tmp.write_text(canonical({"schema": CACHE_SCHEMA, "key": key, "kind": kind, "payload": payload}))
            tmp.replace(self._path(key))
        except OSError:
            pass  # the cache is best-effort

    def rate(self) -> float:
        n = self.hits + self.misses
        return self.hits / n if n else 0.0

    def summary(self) -> str:
        return f"cache: {self.hits} hit(s), {self.misses} miss(es), hit rate {self.rate():.0%}"

    def stats(self) -> dict:
        files = sorted(self.root.glob("*.json")) if self.root.is_dir() else []
        kinds: dict[str, int] = {}
        for f in files:
            try:
                kind = json.loads(f.read_text()).get("kind", "?")
                kinds[kind] = kinds.get(kind, 0) + 1
            except (OSError, ValueError):
                kinds["unreadable"] = kinds.get("unreadable", 0) + 1
        return {"root": str(self.root), "entries": len(files), "bytes": sum(f.stat().st_size for f in files),
                "by_kind": kinds, "schema": CACHE_SCHEMA, "code_hash": code_hash()[:12]}

    def clear(self) -> int:
        n = 0
        if self.root.is_dir():
            for f in [*self.root.glob("*.json"), *self.root.glob("*.tmp")]:
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
        return n
