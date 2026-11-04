"""`phil abm ...`: layer 2 agent-based runs over data/institutions (registered from cli.py; see philengine/abm/).

  phil abm run --institution ID (--seed N | --seeds N) [--steps 50] [--agents-per-role 20] [--modules material]
               [--institutions path]
  phil abm sweep --institution ID --seeds N --param name=lo:hi:steps [--param ...] [--steps] [--agents-per-role]
                 [--modules] [--institutions path]
  phil abm score --institution ID --seeds N [--steps] [--probe-steps 10] [--agents-per-role] [--modules]
                 [--institutions path]
  phil abm gate --seeds N [--steps 50] [--probe-steps 10] [--agents-per-role 20] [--institutions path]
                [--properties path] [--json] [--verbose]
  every command takes --workers N: seeds run over N forked processes (default os.cpu_count(); 1 = serial; the
  results are identical whatever N, only the reported `timing` moves; serial where fork is unavailable)
--seed N prints the AbmReport JSON of one run; --seeds N runs seeds 0..N-1 and prints the per-seed reports plus
rates over seeds (mean final adoption share per role and action, mean final fluent rate, breach and sanction
rates). `sweep` runs the Cartesian grid of --param axes (a DEFAULT_PARAMS name or payoff.<action>) over seeds
0..N-1 and prints one row per (params, seed) plus rates per grid point (A7). Payoffs come from an
optional `payoffs` block on the institution's dataset entry (absent: uniform default). Seed 0 default.
`score` prints the veil-of-ignorance vectors (abm/score.py) as means over seeds with per-seed values (errors exit
3, as `gate`). `gate` runs the layer-2 gate (a)-(d) (abm/gate.py) and exits 0 PASS, 1 FAIL, 2 BLOCKED, 3 on a
load/usage error. A payoff key may name an action instance (`payoff.assign(committee,male_member)`).
`--committed-action NAME` (run, sweep, score) overrides the entry's `payoffs.committed_action`: the action a
`committed_minority` holds (coordination module; `--param committed_minority=0.05:0.5:10` sweeps the share).
"""
from __future__ import annotations

import json
import sys

from .abm import load_payoffs, parallel
from .abm.model import DEFAULT_AGENTS_PER_ROLE, DEFAULT_STEPS, MODULES, run_abm_many
from .abm.report import summarize
from .abm import gate as abm_gate
from .abm.score import PROBE_STEPS, score
from .abm.sweep import parse_param, sweep
from .schemas_rules import RulesLoadError, default_paths, load_institutions, load_properties


def _base_params(a) -> dict | None:
    return {"committed_action": a.committed_action} if getattr(a, "committed_action", None) else None


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
    clock = parallel.Stopwatch()
    try:
        with parallel.pool(a.workers):
            reps = run_abm_many(by_id[a.institution], seeds, a.workers, steps=a.steps, agents_per_role=a.agents_per_role,
                                modules=modules, payoffs=payoffs, params=_base_params(a))
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if a.seeds is not None:
        print(json.dumps(dict(summarize(reps), timing=parallel.timing(clock.seconds, len(seeds), a.workers)),
                         indent=1, sort_keys=True))
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
        with parallel.pool(a.workers):
            out = sweep(by_id[a.institution], axes, seeds=a.seeds, steps=a.steps, agents_per_role=a.agents_per_role,
                        modules=modules, payoffs=load_payoffs(path, a.institution), base_params=_base_params(a),
                        workers=a.workers)
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


def cmd_score(a) -> int:
    # errors exit 3, as `gate` does (2026-11-04 review finding 7; gate's 2 means BLOCKED)
    ip, _ = default_paths()
    path = a.institutions or ip
    try:
        insts = load_institutions(path)
    except RulesLoadError as e:
        print(str(e), file=sys.stderr)
        return 3
    by_id = {i.id: i for i in insts}
    if a.institution not in by_id:
        print(f"unknown institution {a.institution!r}; have {sorted(by_id)}", file=sys.stderr)
        return 3
    modules = [m.strip() for m in a.modules.split(",") if m.strip()]
    try:
        with parallel.pool(a.workers):
            out = score(by_id[a.institution], a.seeds, steps=a.steps, probe_steps=a.probe_steps,
                        agents_per_role=a.agents_per_role, modules=modules, payoffs=load_payoffs(path, a.institution),
                        params=_base_params(a), workers=a.workers)
    except (ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 3
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


def cmd_gate(a) -> int:
    ip, pp = default_paths()
    path, ppath = a.institutions or ip, a.properties or pp
    try:
        insts = load_institutions(path)
        props = load_properties(ppath)
    except (RulesLoadError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 3
    if a.seeds < 1:
        print("--seeds must be >= 1", file=sys.stderr)
        return 3
    with parallel.pool(a.workers):
        rep = abm_gate.run_gate(insts, props, seeds=a.seeds, steps=a.steps, probe_steps=a.probe_steps,
                                agents_per_role=a.agents_per_role, institutions_path=path, workers=a.workers)
    if a.json:
        print(json.dumps(rep.to_dict(), indent=1, sort_keys=True))
    else:
        print(abm_gate.format_gate(rep, verbose=a.verbose))
    return rep.exit_code


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
    s.add_argument("--committed-action", default=None, help="action (or instance label) a committed_minority holds")
    _workers(s)
    s.set_defaults(fn=cmd_run)
    s = rs.add_parser("sweep", help="parameter grid over seeds; every number is a rate over seeds")
    s.add_argument("--institution", "--inst", required=True, dest="institution")
    s.add_argument("--seeds", type=int, required=True, help="run seeds 0..N-1 at every grid point")
    s.add_argument("--param", action="append", default=[], metavar="name=lo:hi:steps",
                   help="sweep axis (repeatable): a DEFAULT_PARAMS name, payoff.<action> or payoff.<action>(<role>,...)")
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--modules", default="material", help=f"comma-separated subset of {','.join(MODULES)}")
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.add_argument("--committed-action", default=None, help="action (or instance label) a committed_minority holds")
    _workers(s)
    s.set_defaults(fn=cmd_sweep)
    s = rs.add_parser("score", help="veil-of-ignorance freedom and flourishing vectors, means over seeds")
    s.add_argument("--institution", "--inst", required=True, dest="institution")
    s.add_argument("--seeds", type=int, required=True, help="score seeds 0..N-1")
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS, help="stabilisation steps before the probe")
    s.add_argument("--probe-steps", type=int, default=PROBE_STEPS, help="steps the probe agent replays")
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--modules", default="material", help=f"comma-separated subset of {','.join(MODULES)}")
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.add_argument("--committed-action", default=None, help="action (or instance label) a committed_minority holds")
    _workers(s)
    s.set_defaults(fn=cmd_score)
    s = rs.add_parser("gate", help="layer-2 gate (a)-(d); exit 0 PASS, 1 FAIL, 2 BLOCKED, 3 load error")
    s.add_argument("--seeds", type=int, required=True, help="seeds 0..N-1 for every check ((d) needs >= 100)")
    s.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    s.add_argument("--probe-steps", type=int, default=PROBE_STEPS)
    s.add_argument("--agents-per-role", type=int, default=DEFAULT_AGENTS_PER_ROLE)
    s.add_argument("--institutions", default=None, help="path to institutions.json")
    s.add_argument("--properties", default=None, help="path to properties.json")
    s.add_argument("--json", action="store_true")
    s.add_argument("--verbose", action="store_true", help="print per-seed and per-institution lines")
    _workers(s)
    s.set_defaults(fn=cmd_gate)


def _workers(s) -> None:
    s.add_argument("--workers", type=int, default=parallel.workers_default(), metavar="N",
                   help="processes for the seed loop (default: cpu count; 1 = serial; identical results either way)")
