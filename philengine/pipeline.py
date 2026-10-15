"""Convenience driver: run stages in order via Runner."""
from __future__ import annotations

from . import (stage_formalize, stage_iso, stage_judge, stage_reconstruct, stage_select)  # noqa: F401  (register)
from .runner import STAGES, Ctx, RunSummary, Runner
from .stage_common import n_candidates
from .store import Store

ALL_STAGES = ("reconstruct", "formalize", "judge", "select", "iso")
ISO_UNIT = "*"


def run_all(store: Store, run_id: int, llm, argument_ids: list[str] | None = None,
            stages: tuple[str, ...] = ALL_STAGES, options: dict | None = None,
            resume: bool = True, retry_failed: bool = False) -> dict[str, RunSummary]:
    """Run `stages` in order. formalize/judge run one job per (argument, candidate); iso once for the corpus."""
    ids = list(argument_ids) if argument_ids is not None else store.argument_ids()
    ctx = Ctx(store, run_id, llm, dict(options or {}))
    runner = Runner(store, run_id, ctx)
    out = {}
    for st in stages:
        if st not in STAGES:
            raise KeyError(f"unknown stage {st!r}")
        if st in ("formalize", "judge"):
            out[st] = runner.run(st, ids, resume, retry_failed, candidate_idxs=list(range(n_candidates(ctx))))
        elif st == "iso":
            out[st] = runner.run(st, [ISO_UNIT], resume, retry_failed)
        else:
            out[st] = runner.run(st, ids, resume, retry_failed)
    return out
