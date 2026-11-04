"""Parameter sweep (A7: every reported number is a rate over seeds, never a single point).

`parse_param("copy_rate=0:1:5")` -> ("copy_rate", [0.0, 0.25, 0.5, 0.75, 1.0]); `sweep(...)` runs the Cartesian
grid of the given axes over seeds 0..N-1 and returns one row per (params, seed) plus `summarize` rates per grid
point. Payoff keys can be swept too: an axis named `payoff.<action>` sets that action's payoff, and
`payoff.<action>(<role>,...)` (an `action_label`, 2026-11-04 A1 extension) one instance's payoff, validated
against the reference's action instances. `base_params` (e.g. `{"committed_action": "new_name"}`) are held fixed
under every grid point; `committed_minority` is a DEFAULT_PARAMS axis (gate (b)).

`necessary_modules(inst, predicate, seeds)` (plan: "Eight configurations; `necessary_modules` lists the minimal
subsets under which the expected outcome occurs in >= 80% of seeds"): runs every subset of the modules that can
run (the stubs are left out and named; `{}` is included, it is static but it is a configuration) and reports,
per subset, the rate of seeds where `predicate(model)` holds on the finished model, plus the MINIMAL subsets
whose rate meets `rate_min` (no proper subset meets it). The predicate reads the finished `InstitutionModel`
(its `report()`, `state`, `ref`), so a gate letter can evaluate a dataset property through the reference.
"""
from __future__ import annotations

import itertools
from typing import Callable

from ..rules_reference import Reference
from ..schemas_rules import InstitutionJSON
from .agent import action_label
from .model import (DEFAULT_AGENTS_PER_ROLE, DEFAULT_PARAMS, DEFAULT_STEPS, MODULES, STUB_MODULES, InstitutionModel,
                    run_abm)
from .report import summarize

RATE_MIN = 0.80  # plan: "occurs in >= 80% of seeds"


def parse_param(text: str) -> tuple[str, list[float]]:
    """name=lo:hi:steps (steps >= 1; steps == 1 gives [lo]); name=v for a single value."""
    if "=" not in text:
        raise ValueError(f"--param {text!r}: expected name=lo:hi:steps")
    name, spec = text.split("=", 1)
    name = name.strip()
    parts = spec.split(":")
    if len(parts) == 1:
        return name, [float(parts[0])]
    if len(parts) != 3:
        raise ValueError(f"--param {text!r}: expected name=lo:hi:steps")
    lo, hi, n = float(parts[0]), float(parts[1]), int(parts[2])
    if n < 1:
        raise ValueError(f"--param {text!r}: steps must be >= 1")
    if n == 1:
        return name, [lo]
    return name, [lo + i * (hi - lo) / (n - 1) for i in range(n)]


def sweep(inst: InstitutionJSON, axes: dict[str, list[float]], seeds: int, steps: int = DEFAULT_STEPS,
          agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, modules=("material",),
          payoffs: dict | None = None, base_params: dict | None = None) -> dict:
    declared = sorted(a.name for a in inst.actions)
    instances = sorted(action_label(i) for i in Reference(inst, k=1).action_insts)
    for name in axes:
        if name.startswith("payoff."):
            action = name[len("payoff."):]
            if action not in declared and action not in instances:
                raise ValueError(f"sweep axis {name!r}: {action!r} is not an action of {inst.id} nor one of its action "
                                 f"instances; declared actions: {declared}; instances: {instances}")
        elif name not in DEFAULT_PARAMS:
            raise ValueError(f"unknown parameter {name!r}; have {sorted(DEFAULT_PARAMS)} or payoff.<action>")
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    names = list(axes)
    grid = []
    for values in itertools.product(*[axes[n] for n in names]):
        point = dict(zip(names, values))
        params = dict(base_params or {}, **{k: v for k, v in point.items() if not k.startswith("payoff.")})
        pay = dict(payoffs or {}, **{k[len("payoff."):]: v for k, v in point.items() if k.startswith("payoff.")})
        reps = [run_abm(inst, seed=s, steps=steps, agents_per_role=agents_per_role, modules=modules, payoffs=pay,
                        params=params) for s in range(seeds)]
        summary = summarize(reps)
        rows = [{"params": point, "seed": r.seed, "final_adoption": r.final_adoption(), "fluent_rates": r.fluent_rates,
                 "breach_rate": r.breach_rate(), "unavoidable_rate": r.unavoidable_rate(),
                 "sanctioned_rate": r.sanctioned_rate()} for r in reps]
        grid.append({"params": point, "rates": {k: v for k, v in summary.items() if k != "runs"}, "rows": rows})
    return {"institution": inst.id, "seeds": seeds, "steps": steps, "agents_per_role": agents_per_role,
            "modules": list(modules), "axes": {n: axes[n] for n in names}, "grid": grid}


def module_subsets(modules=MODULES) -> tuple[list[tuple[str, ...]], dict[str, str]]:
    """(every subset of the runnable modules, smallest first, `()` included; {module: why it cannot run})."""
    stubs = {m: f"mechanism module {m!r} is a stub (not built yet)" for m in modules if m in STUB_MODULES}
    live = [m for m in modules if m not in stubs]
    subsets = [cfg for r in range(len(live) + 1) for cfg in itertools.combinations(live, r)]
    return subsets, stubs


def necessary_modules(inst: InstitutionJSON, predicate: Callable[[InstitutionModel], bool], seeds: int,
                      steps: int = DEFAULT_STEPS, agents_per_role: int = DEFAULT_AGENTS_PER_ROLE,
                      payoffs: dict | None = None, params: dict | None = None, rate_min: float = RATE_MIN,
                      modules=MODULES, graph_k=None, graph_p=None) -> dict:
    """Which module subsets produce an outcome. Runs seeds 0..seeds-1 under every subset of the runnable modules
    and returns {"rates": {config key: rate of seeds where predicate(model) held}, "sufficient": [subsets meeting
    rate_min], "necessary": [the MINIMAL sufficient subsets: no proper subset meets rate_min], "not_run": {stub:
    why}, "rate_min", "seeds"}. Config keys are "+"-joined module names, "{}" for the empty set. An empty
    `necessary` with a non-empty `sufficient` cannot happen; both empty means no subset reaches the rate."""
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    subsets, not_run = module_subsets(modules)
    kw = {}
    if graph_k is not None:
        kw["graph_k"] = graph_k
    if graph_p is not None:
        kw["graph_p"] = graph_p
    rates: dict[tuple[str, ...], float] = {}
    for cfg in subsets:
        hits = 0
        for s in range(seeds):
            m = InstitutionModel(inst, seed=s, agents_per_role=agents_per_role, modules=cfg, payoffs=payoffs,
                                 params=params, **kw)
            for _ in range(steps):
                m.step()
            hits += int(bool(predicate(m)))
        rates[cfg] = hits / seeds
    sufficient = [cfg for cfg in subsets if rates[cfg] >= rate_min]
    necessary = [cfg for cfg in sufficient
                 if not any(set(o) < set(cfg) for o in sufficient)]
    key = lambda cfg: "+".join(cfg) if cfg else "{}"
    return {"institution": inst.id, "seeds": seeds, "steps": steps, "rate_min": rate_min,
            "rates": {key(c): rates[c] for c in subsets}, "sufficient": [list(c) for c in sufficient],
            "necessary": [list(c) for c in necessary], "not_run": not_run}
