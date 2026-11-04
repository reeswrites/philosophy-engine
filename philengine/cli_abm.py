"""`phil abm ...`: layer 2 agent-based runs over data/institutions (registered from cli.py; see philengine/abm/).

  phil abm run --institution ID --seed N [--steps 50] [--agents-per-role 20] [--modules material]
               [--institutions path]
Prints the AbmReport JSON for one run. Payoffs come from an optional `payoffs` block on the institution's dataset
entry (absent: uniform default). Seed 0 default; every draw goes through the model rng.
"""
from __future__ import annotations

import sys

from .abm import load_payoffs, run_abm
from .abm.model import DEFAULT_AGENTS_PER_ROLE, DEFAULT_STEPS, MODULES
from .schemas_rules import RulesLoadError, default_paths, load_institutions


def cmd_run(a) -> int:
    ip, _ = default_paths()
    path = a.institutions or ip
    try:
        insts = load_institutions(path)
    except RulesLoadError as e:
        print(str(e), file=sys.stderr)
        return 2
    by_id = {i.id: i for i in insts}
    if a.institution not in by_id:
        print(f"unknown institution {a.institution!r}; have {sorted(by_id)}", file=sys.stderr)
        return 2
    modules = [m.strip() for m in a.modules.split(",") if m.strip()]
    try:
        rep = run_abm(by_id[a.institution], seed=a.seed, steps=a.steps, agents_per_role=a.agents_per_role,
                      modules=modules, payoffs=load_payoffs(path, a.institution))
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 2
    print(rep.to_json())
    return 0


def register(sub) -> None:
    """Attach `abm` to the top-level `phil` subparsers."""
    p = sub.add_parser("abm", help="institutions family, layer 2: agent-based runs over ADICO rules")
    rs = p.add_subparsers(dest="abm_cmd", required=True)
    s = rs.add_parser("run", help="one seeded run; prints AbmReport JSON")
    s.add_argument("--institution", "--inst", required=True, dest="institution")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--modules", default="material", help=f"comma-separated subset of {','.join(MODULES)}")
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.set_defaults(fn=cmd_run)
