"""Process pool over seeds (A7: every number is a rate over seeds, and seeds are independent: one rng per seed).

`run_map(fn, jobs, workers)` returns `[fn(*job) for job in jobs]` in job order, computed by `workers` forked
processes when workers > 1 and fork is available, else serially. Results are byte-identical to the serial path:
each job is one seeded run, the worker returns a plain picklable value (a report dict, a trace, a ProbeScore) and
the parent keeps seed order. `workers=1` is the serial path exactly (no pool, no pickling).

The pool is forked (never spawned: importing mesa costs ~1 s per process, and a forked child inherits the parent's
imports and the model code as loaded, monkeypatches included), so it is only used where `fork` is an available
start method and the platform is not macOS (fork is unsafe there under CPython's default libraries); elsewhere
every call runs serially, whatever `workers` says. `pool(workers)` opens one pool for a whole command (`phil abm
run/sweep/score/gate`): every `run_map` inside the block reuses it (and reports the pool's count as `workers`);
outside a block `run_map` forks its own pool for the call and shuts it down after (fork is cheap, so a library
caller pays little). `fn` must be a module-level
function; `necessary_modules` passes a predicate that may be a lambda, so `run_map(..., fresh=True)` forks a
fresh pool for that call and the predicate travels through `_INHERITED` by inheritance rather than by pickle.
`workers_default()` is `os.cpu_count()` (the CLI `--workers` default). `timing(...)` builds the timing record
the sweep and gate JSON carry.
"""
from __future__ import annotations

import contextlib
import multiprocessing
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Iterable

_ACTIVE: list[ProcessPoolExecutor | None] = [None]  # the pool `pool()` opened, if any
_ACTIVE_WORKERS: list[int] = [1]
_INHERITED: dict[str, Any] = {}  # values a fresh (forked) pool inherits without pickling


def fork_available() -> bool:
    """Fork is used on a platform that offers it (not macOS: unsafe there under CPython's default libraries) from a
    process with no other Python thread, and never inside a pytest-xdist worker (its execnet threads are what
    CPython's fork warning is about; the serial suite covers the pool tests, which skip under `-n auto`). The idle
    BLAS threads numpy starts are fine to fork over (atfork handlers), so OS-level thread counts are not read."""
    return (sys.platform != "darwin" and "fork" in multiprocessing.get_all_start_methods()
            and threading.active_count() == 1 and "PYTEST_XDIST_WORKER" not in os.environ)


def workers_default() -> int:
    return max(1, os.cpu_count() or 1)


def resolve_workers(workers: int | None) -> int:
    """The number of processes a call will use: inside a `pool()` block the pool's count (decided once, when the
    pool was opened: its own manager thread must not count as "multi-threaded" afterwards); outside, `workers`
    when > 1 and fork is available, else 1 (serial)."""
    if _ACTIVE[0] is not None:
        return _ACTIVE_WORKERS[0]
    if workers is None:
        return 1
    workers = max(1, int(workers))
    return workers if workers > 1 and fork_available() else 1


def _make_pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("fork"))


@contextlib.contextmanager
def pool(workers: int | None):
    """Open one pool for a command; `run_map` calls inside reuse it. `workers <= 1` (or no fork) opens nothing."""
    if _ACTIVE[0] is not None:
        raise RuntimeError("a parallel.pool() block is already open")
    n = resolve_workers(workers)
    prev, prev_n = _ACTIVE[0], _ACTIVE_WORKERS[0]
    ex = _make_pool(n) if n > 1 else None
    _ACTIVE[0], _ACTIVE_WORKERS[0] = ex, n
    try:
        yield n
    finally:
        _ACTIVE[0], _ACTIVE_WORKERS[0] = prev, prev_n
        if ex is not None:
            ex.shutdown(wait=True)


def _call(fn: Callable, args: tuple) -> Any:
    return fn(*args)


def run_map(fn: Callable, jobs: Iterable[tuple], workers: int | None = None, fresh: bool = False) -> list:
    """`[fn(*job) for job in jobs]`, in order. `workers=None` uses the open pool's count (1 outside a `pool()`
    block). `fresh=True` forks a pool of its own for this call (so module globals set just before, such as
    `_INHERITED`, are seen by the workers)."""
    jobs = list(jobs)
    n = resolve_workers(workers)
    if n <= 1 or len(jobs) <= 1:
        return [fn(*job) for job in jobs]
    ex = _ACTIVE[0]
    if ex is not None and not fresh:
        return list(ex.map(_call, [fn] * len(jobs), jobs))
    with _make_pool(min(n, len(jobs))) as own:  # shut down (its thread joined) before returning
        return list(own.map(_call, [fn] * len(jobs), jobs))


def timing(seconds: float, runs: int, workers: int | None = None, **extra) -> dict:
    """{seconds, runs, runs_per_second, workers, ...extra}: the timing record of a seed loop."""
    return {"seconds": round(seconds, 3), "runs": runs,
            "runs_per_second": round(runs / seconds, 2) if seconds > 0 else None,
            "workers": resolve_workers(workers), **extra}


class Stopwatch:
    def __init__(self):
        self.t0 = time.perf_counter()

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self.t0
