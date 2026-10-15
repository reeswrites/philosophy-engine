"""Job-table driven stage runner with resume.

Stages register by name: `@register("reconstruct") def fn(ctx, unit): ...` (step 3 does this).
`Runner(store, run_id, ctx).run(stage, argument_ids, resume=True)` upserts one job per (argument, candidate),
skips `done`, runs `pending` (and `failed` only with retry_failed). `running` rows left by a crashed process
are reset to pending at the start of every run(). resume=False re-runs everything in scope.
Exceptions (Exception subclasses) mark the job failed and the run continues; BaseException (Ctrl-C, a
simulated crash) propagates and leaves the job `running`, to be recovered by the next run().
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from .store import Store

STAGES: dict[str, Callable[["Ctx", "Unit"], None]] = {}


def register(name: str):
    def deco(fn):
        STAGES[name] = fn
        return fn
    return deco


@dataclass
class Unit:
    argument_id: str
    candidate_idx: int = -1  # -1 = whole-argument unit
    job_id: int = 0
    attempts: int = 0


@dataclass
class Ctx:
    store: Store
    run_id: int
    llm: Any = None  # LLMClient | MockLLMClient
    options: dict = field(default_factory=dict)  # n_candidates, from_human, ...


@dataclass
class RunSummary:
    stage: str
    done: int = 0
    failed: int = 0
    skipped: int = 0  # already done / failed-not-retried
    reset: int = 0  # crashed `running` jobs recovered

    @property
    def ok(self) -> bool:
        return self.failed == 0


class Runner:
    def __init__(self, store: Store, run_id: int, ctx: Ctx | None = None, stages: dict | None = None):
        self.store, self.run_id = store, run_id
        self.ctx = ctx or Ctx(store, run_id)
        self.stages = STAGES if stages is None else stages

    def run(self, stage: str, argument_ids: list[str], resume: bool = True, retry_failed: bool = False,
            candidate_idxs: list[int] | None = None) -> RunSummary:
        if stage not in self.stages:
            raise KeyError(f"unknown stage {stage!r}; registered: {sorted(self.stages)}")
        fn = self.stages[stage]
        s = RunSummary(stage)
        s.reset = self.store.reset_running_jobs(self.run_id)
        for aid in argument_ids:
            for ci in (candidate_idxs if candidate_idxs is not None else [-1]):
                job = self.store.upsert_job(self.run_id, aid, stage, ci)
                status = job["status"]
                if not resume:
                    self.store.set_job(job["id"], "pending")
                elif status in ("done", "skipped") or (status == "failed" and not retry_failed):
                    s.skipped += 1
                    continue
                self.store.set_job(job["id"], "running")
                unit = Unit(aid, ci, job["id"], job["attempts"] + 1)
                try:
                    fn(self.ctx, unit)
                except Exception as e:
                    self.store.set_job(job["id"], "failed", "".join(traceback.format_exception_only(type(e), e)).strip())
                    s.failed += 1
                else:
                    self.store.set_job(job["id"], "done")
                    s.done += 1
        return s

    def status(self, stage: str | None = None) -> dict[str, int]:
        out: dict[str, int] = {}
        for j in self.store.jobs(self.run_id, stage):
            out[j["status"]] = out.get(j["status"], 0) + 1
        return out
