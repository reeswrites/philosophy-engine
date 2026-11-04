"""Parameter sweep (A7: every reported number is a rate over seeds, never a single point).

`parse_param("copy_rate=0:1:5")` -> ("copy_rate", [0.0, 0.25, 0.5, 0.75, 1.0]); `sweep(...)` runs the Cartesian
grid of the given axes over seeds 0..N-1 and returns one row per (params, seed) plus `summarize` rates per grid
point. Payoff keys can be swept too: an axis named `payoff.<action>` sets that action's payoff.
"""
from __future__ import annotations

import itertools

from ..schemas_rules import InstitutionJSON
from .model import DEFAULT_AGENTS_PER_ROLE, DEFAULT_PARAMS, DEFAULT_STEPS, run_abm
from .report import summarize


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
          payoffs: dict[str, float] | None = None) -> dict:
    for name in axes:
        if not (name in DEFAULT_PARAMS or name.startswith("payoff.")):
            raise ValueError(f"unknown parameter {name!r}; have {sorted(DEFAULT_PARAMS)} or payoff.<action>")
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    names = list(axes)
    grid = []
    for values in itertools.product(*[axes[n] for n in names]):
        point = dict(zip(names, values))
        params = {k: v for k, v in point.items() if not k.startswith("payoff.")}
        pay = dict(payoffs or {}, **{k[len("payoff."):]: v for k, v in point.items() if k.startswith("payoff.")})
        reps = [run_abm(inst, seed=s, steps=steps, agents_per_role=agents_per_role, modules=modules, payoffs=pay,
                        params=params) for s in range(seeds)]
        summary = summarize(reps)
        rows = [{"params": point, "seed": r.seed, "final_adoption": r.final_adoption(), "fluent_rates": r.fluent_rates,
                 "breach_rate": r.breach_rate(), "sanctioned_rate": r.sanctioned_rate()} for r in reps]
        grid.append({"params": point, "rates": {k: v for k, v in summary.items() if k != "runs"}, "rows": rows})
    return {"institution": inst.id, "seeds": seeds, "steps": steps, "agents_per_role": agents_per_role,
            "modules": list(modules), "axes": {n: axes[n] for n in names}, "grid": grid}
