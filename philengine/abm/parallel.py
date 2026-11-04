"""Process pool over seeds (A7: every number is a rate over seeds, and seeds are independent: one rng per seed).

`run_map(fn, jobs, workers)` returns `[fn(*job) for job in jobs]` in job order, computed by `workers` worker
processes (forked or spawned, see below) when workers > 1, else serially. Results are byte-identical to the serial path:
each job is one seeded run, the worker returns a plain picklable value (a report dict, a trace, a ProbeScore) and
the parent keeps seed order. `workers=1` is the serial path exactly (no pool, no pickling).

Start method (updated 2026-11-04): the pool is FORKED where fork is available and safe (Linux, from a process with no
other Python thread: a forked child inherits the parent's imports, monkeypatches and lambdas, and costs nothing to
start), and SPAWNED everywhere else, notably macOS, where fork is unsafe under CPython's default libraries (objc /
system frameworks; CPython made spawn the macOS default for that reason) but spawn is safe. `start_method()` says
which; `PHIL_START_METHOD=fork|spawn` overrides it (tests use it to exercise spawn on Linux). Spawn rules: `fn` and
every job argument must be picklable (module-level functions, plain data, pydantic models; z3 objects are NOT picklable,
so a job that needs a z3 lowering rebuilds it inside the worker from the JSON entry and parameters and returns plain
dicts/dataclasses); each worker imports the package afresh (~1 s for mesa/z3/pydantic, paid once per worker because
pool workers persist: open ONE pool per command with `pool(workers)`, not one per call); a script that calls this
must guard its entry with `if __name__ == "__main__":`. Module globals set in the parent are NOT seen by spawned
workers, so `run_map(..., fresh=True)` (which relies on `_INHERITED`) falls back to the serial loop under spawn. Only
inside a pytest-xdist worker is everything serial. `pool(workers)` opens one pool for a whole command (`phil abm
run/sweep/score/gate`, `phil rules ablate`): every `run_map` inside the block reuses it (and reports the pool's count
as `workers`); outside a block `run_map` opens its own pool for the call and shuts it down after. `fn` must be a
module-level function; `necessary_modules` passes a predicate that may be a lambda, so under fork `fresh=True` forks a
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
_ACTIVE_METHOD: list[str] = ["fork"]  # start method decided when `pool()` opened (its own threads must not change it)
_INHERITED: dict[str, Any] = {}  # values a fresh (forked) pool inherits without pickling


def fork_available() -> bool:
    """Fork is used on a platform that offers it (not macOS: unsafe there under CPython's default libraries) from a
    process with no other Python thread, and never inside a pytest-xdist worker (its execnet threads are what
    CPython's fork warning is about; the serial suite covers the pool tests, which skip under `-n auto`). The idle
    BLAS threads numpy starts are fine to fork over (atfork handlers), so OS-level thread counts are not read."""
    return (sys.platform != "darwin" and "fork" in multiprocessing.get_all_start_methods()
            and threading.active_count() == 1 and "PYTEST_XDIST_WORKER" not in os.environ)


def parallel_available() -> bool:
    """Any pool at all: never inside a pytest-xdist worker (its execnet threads; the serial suite covers the pools)."""
    return "PYTEST_XDIST_WORKER" not in os.environ


def start_method() -> str:
    """"fork" where fork_available(), else "spawn" (macOS, or a multi-threaded process); PHIL_START_METHOD overrides."""
    forced = os.environ.get("PHIL_START_METHOD")
    if forced in ("fork", "spawn"):
        return forced
    return "fork" if fork_available() else "spawn"


def workers_default() -> int:
    return max(1, os.cpu_count() or 1)


def resolve_workers(workers: int | None) -> int:
    """The number of processes a call will use: inside a `pool()` block the pool's count (decided once, when the
    pool was opened: its own manager thread must not count as "multi-threaded" afterwards); outside, `workers`
    when > 1 and a pool can be used here (parallel_available), else 1 (serial)."""
    if _ACTIVE[0] is not None:
        return _ACTIVE_WORKERS[0]
    if workers is None:
        return 1
    workers = max(1, int(workers))
    return workers if workers > 1 and parallel_available() else 1


def _make_pool(workers: int, method: str | None = None) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context(method or start_method()))


def _method() -> str:
    return _ACTIVE_METHOD[0] if _ACTIVE[0] is not None else start_method()


@contextlib.contextmanager
def pool(workers: int | None):
    """Open one pool for a command; `run_map` calls inside reuse it. `workers <= 1` (or xdist) opens nothing."""
    if _ACTIVE[0] is not None:
        raise RuntimeError("a parallel.pool() block is already open")
    n = resolve_workers(workers)
    prev, prev_n = _ACTIVE[0], _ACTIVE_WORKERS[0]
    method = start_method()
    ex = _make_pool(n, method) if n > 1 else None
    _ACTIVE[0], _ACTIVE_WORKERS[0], _ACTIVE_METHOD[0] = ex, n, method
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
    block). `fresh=True` forks a pool of its own (serial under spawn) for this call (so module globals set just before, such as
    `_INHERITED`, are seen by the workers)."""
    jobs = list(jobs)
    n = resolve_workers(workers)
    if n <= 1 or len(jobs) <= 1:
        return [fn(*job) for job in jobs]
    if fresh and _method() != "fork":  # `_INHERITED` is invisible to spawned workers: stay serial (identical results)
        return [fn(*job) for job in jobs]
    ex = _ACTIVE[0]
    if ex is not None and not fresh:
        return list(ex.map(_call, [fn] * len(jobs), jobs))
    with _make_pool(min(n, len(jobs)), _method()) as own:  # shut down (its thread joined) before returning
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
