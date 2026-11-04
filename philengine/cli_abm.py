"""`phil abm ...`: layer 2 agent-based runs over data/institutions (registered from cli.py; see philengine/abm/).

  phil abm run --institution ID (--seed N | --seeds N) [--steps 50] [--agents-per-role 20] [--modules material]
               [--institutions path]
  phil abm sweep --institution ID --seeds N --param name=lo:hi:steps [--param ...] [--steps] [--agents-per-role]
                 [--modules] [--institutions path]
--seed N prints the AbmReport JSON of one run; --seeds N runs seeds 0..N-1 and prints the per-seed reports plus
rates over seeds (mean final adoption share per role and action, mean final fluent rate, breach and sanction
rates). `sweep` runs the Cartesian grid of --param axes (a DEFAULT_PARAMS name or payoff.<action>) over seeds
0..N-1 and prints one row per (params, seed) plus rates per grid point (A7). Payoffs come from an
optional `payoffs` block on the institution's dataset entry (absent: uniform default). Seed 0 default.
"""
from __future__ import annotations

import json
import sys

from .abm import load_payoffs, run_abm
from .abm.model import DEFAULT_AGENTS_PER_ROLE, DEFAULT_STEPS, MODULES
from .abm.report import summarize
from .abm.sweep import parse_param, sweep
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
    payoffs = load_payoffs(path, a.institution)
    seeds = list(range(a.seeds)) if a.seeds is not None else [a.seed]
    if not seeds:
        print("--seeds must be >= 1", file=sys.stderr)
        return 2
    try:
        reps = [run_abm(by_id[a.institution], seed=s, steps=a.steps, agents_per_role=a.agents_per_role,
                        modules=modules, payoffs=payoffs) for s in seeds]
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if a.seeds is not None:
        print(json.dumps(summarize(reps), indent=1, sort_keys=True))
    else:
        print(reps[0].to_json())
    return 0


def cmd_sweep(a) -> int:
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
        axes = dict(parse_param(t) for t in a.param)
        out = sweep(by_id[a.institution], axes, seeds=a.seeds, steps=a.steps, agents_per_role=a.agents_per_role,
                    modules=modules, payoffs=load_payoffs(path, a.institution))
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


def register(sub) -> None:
    """Attach `abm` to the top-level `phil` subparsers."""
    p = sub.add_parser("abm", help="institutions family, layer 2: agent-based runs over ADICO rules")
    rs = p.add_subparsers(dest="abm_cmd", required=True)
    s = rs.add_parser("run", help="seeded run(s); prints AbmReport JSON, or rates over seeds with --seeds")
    s.add_argument("--institution", "--inst", required=True, dest="institution")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--seed", type=int, default=0, help="one run with this seed (default 0)")
    g.add_argument("--seeds", type=int, default=None, help="run seeds 0..N-1 and report rates over seeds")
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--modules", default="material", help=f"comma-separated subset of {','.join(MODULES)}")
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.set_defaults(fn=cmd_run)
    s = rs.add_parser("sweep", help="parameter grid over seeds; every number is a rate over seeds")
    s.add_argument("--institution", "--inst", required=True, dest="institution")
    s.add_argument("--seeds", type=int, required=True, help="run seeds 0..N-1 at every grid point")
    s.add_argument("--param", action="append", default=[], metavar="name=lo:hi:steps",
                   help="sweep axis (repeatable): a DEFAULT_PARAMS name or payoff.<action>")
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--modules", default="material", help=f"comma-separated subset of {','.join(MODULES)}")
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.set_defaults(fn=cmd_sweep)
