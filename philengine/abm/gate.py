"""Layer-2 gate, `phil abm gate` (plan: plans/layer2-abm.md, "Pass tests (`phil abm gate`)"; mirrors
rules_gate: lettered criteria, precommitted expectations read from the dataset, PASS/FAIL table).

A criterion is PASS, FAIL or BLOCKED. BLOCKED means the check cannot run yet and says why (an institution the
dataset does not have, a mechanism module that is still a stub, a parameter the model does not take, too few
seeds); it is never a silent pass or a skip. Verdict: FAIL if any criterion fails, else BLOCKED if any is
blocked, else PASS.

(a) footbinding collapse (Mackie 1996), slice 4: FOOTBINDING collapses within A_STEPS in >= SEED_RATE_MIN of
    seeds iff `coordination` is on and pledge actions exist (`*_pledge`, A3); with either absent it persists
    (collapse rate <= 1 - SEED_RATE_MIN, review finding 6a). The pledge half of the "iff" is read on a
    pledge-ablated entry: A_PAIR from the dataset when present, else the entry minus its pledge actions and the
    rules naming them (ASSUMED, reported). Collapse is read off the ADOPTION SHARE (encoder caveat, 2026-11-04:
    state is role-level, one pledge sets `pledged` for every family and a set-true effect beats set-false in the
    successor, so the property can only flip when every family leaves unbound in one step): the late-window mean
    (last ceil(C_WINDOW*(steps+1)) values, step 0 included) of the actor role's share of the COLLAPSE ACTION, the
    base of the entry's pledge action (`leave_unbound`), is >= A_SHARE_HIGH. A_PROP through `Reference.prop` is an
    information line at the default point, not the criterion. Payoffs are swept, not calibrated (A1, A7): the
    collapse action's payoff over A_PAYOFF_GRID x `sanction_weight` over A_SANCTION_GRID (the entry's own payoffs
    otherwise), seeds capped at A_SEEDS_MAX per point. Pass criterion, written before the run: at SOME grid point
    every (entry, configuration) cell meets its expectation (collapse under every coordination configuration of
    the pledge entry; persistence under every other configuration and under every configuration of the ablated
    entry); FAIL otherwise, named vacuous when the collapse action is never adopted anywhere. BLOCKED: no
    FOOTBINDING entry, no coordination configuration, no `*_pledge` action (the collapse action is undefined).
(b) committed minority (Centola 2018), slice 4: sweep B_PARAM (`committed_minority`, a DEFAULT_PARAMS entry) over
    B_SWEEP on NAMING under every coordination configuration; the committed agents hold the entry's
    `committed_action` (payoffs block or entry key; BLOCKED when absent: the new-convention action is a dataset
    input, never a constant here). Adoption is the actor role's share of that action at the last step
    (`adoption_shares`, review finding 6: a property mean cannot express a population share under shared role
    state), mean over seeds per sweep point; PASS iff it jumps by more than B_JUMP between adjacent points under
    every coordination configuration. The sweep's resolution (0.05) sets only how finely the location is seen;
    the location itself comes from thresholds (`threshold_max`), the graph and the entry; "no constant in the code
    sets the location" stays a reviewer item printed with the result, Centola's band is recorded in the dataset.
(c) kibbutz regendering, redesigned 2026-11-04 (review finding 1: the first cut was decided at step 1 by the
    choice-set rule and was flat under any sanction sweep). The test is a TWO-AXIS SWEEP (plan: "swept, not
    calibrated"; ADR 0015 A1 payoff ranges, A4 swept sanction weight, A7 rates over a sweep): `sanction_weight`
    over C_SANCTION_GRID and the payoff of the forbidden instance C_FORBIDDEN (`assign(committee,male_member)`,
    the instance R2 forbids; a per-instance payoff key, A1 extension) over C_PAYOFF_GRID, with `seeds` runs per
    grid point. Readings per seed: the C_FORBIDDEN_ROLE's adoption share of C_FORBIDDEN (`adoption_shares`, step
    0 = 0.0 prepended) and PROP_C (through `Reference.prop`, never by fluent name), each as a late-window mean
    (last ceil(C_WINDOW*(steps+1)) values). At a grid point the forbidden instance PERSISTS-EXCLUDED when the late
    share <= C_SHARE_LOW and is ADOPTED (the norm collapses) when the late share >= C_SHARE_HIGH; a grid point's
    rate is the share of seeds meeting that. "Out-pays" = the instance's payoff strictly exceeds the best lawful
    payoff available to the role at step 0 (the strict admission rule in agent.py). Pass criterion, written
    before the run: on KIBBUTZ there is a sanction BAND (sanction_weight values at which the persist rate >=
    SEED_RATE_MIN for EVERY payoff point) and, for EVERY out-paying payoff point, a sanction_weight BELOW the band
    at which the adoption rate >= SEED_RATE_MIN (the sanction governs; the test FAILS when the persist verdict is
    independent of sanction_weight across the grid: that is the vacuity the review named); on KIBBUTZ_PAIR (the
    entry minus R2: nothing to sanction) the instance is adopted at every sanction_weight for every out-paying
    payoff point in >= SEED_RATE_MIN of seeds. BLOCKED, never PASS/FAIL, when the instance is not an action
    instance of the entry, is never available to the role at step 0, or is never a candidate for any agent at
    any grid point (vacuity guard: no payoff key reaches it). Extra reported line, not a criterion: the old
    property-trace reading at the default point (sanction_weight = DEFAULT_PARAMS, payoff = default_payoff):
    KIBBUTZ `rises_toward_one` (late >= C_HIGH and late >= early - C_FLAT_TOL) and KIBBUTZ_PAIR `ends_below_high`
    (late - early <= C_FLAT_TOL and late < C_HIGH; renamed from `stays_flat`, review finding 2: it accepts a 1 -> 0
    drop, so it measures "ends below C_HIGH without rising", not flatness). Note that under shared role-level
    state (A2) one adopting agent flips PROP_C for every agent and `release` is never available, so the property
    stays false once broken even after the committee has returned to lawful assignment: the share is the reading.
(d) seed stability: rank the institutions by the mean summed veil-of-ignorance score (`score.py`; nulls excluded)
    over each of two disjoint halves of the seeds (first half / second half, ASSUMED) and require Spearman >=
    D_RHO_MIN for every module configuration run; needs >= D_MIN_SEEDS seeds, else BLOCKED. Institutions whose
    runs raise are listed as errors and fail the criterion. Disagreement pairs (freedom vs flourishing) are
    printed as information. Ranks are AVERAGE ranks (ties share the mean of the ranks they span, marked "tie"),
    the same ranks `spearman` uses; `mean_measured` (sum / measured components) is printed beside the sum the
    ranking uses (review findings 3b, 4). Caveat printed on the line: (d) is necessary, not sufficient (a
    role-count scorer would also be stable), and the freedom components are static per role on this dataset,
    so seed variance there is role sampling only.

Module configurations: of the plan's eight, the gate runs those `_check_modules` accepts, minus the empty set:
since slice 4 that is {material}, {coordination}, {material, coordination}; the four subsets with `imagination`
(a stub) are listed as not run with the reason, and the empty set because the bootstrap rule (an agent with no
practice takes the best-paying candidate) belongs to the adaptive modules, so under {} no agent ever starts a
practice and every run is static.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .. import sexpr as sx
from ..schemas_rules import InstitutionJSON, Property
from .agent import PLEDGE_SUFFIX, action_label
from .model import (DEFAULT_AGENTS_PER_ROLE, DEFAULT_PARAMS, DEFAULT_STEPS, MODULES, InstitutionModel, _check_modules,
                    load_payoffs, split_payoffs)
from .score import PROBE_STEPS, disagreement, ranks, score, spearman

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
EXIT_CODES = {PASS: 0, FAIL: 1, BLOCKED: 2}  # ASSUMED (rules_gate has no BLOCKED); load/usage errors exit 3

FOOTBINDING = "footbinding"
A_PAIR = "footbinding-no-pledge"  # dataset: the footbinding entry minus the pledge action and its rule
NAMING = "naming-convention"
KIBBUTZ = "kibbutz-childrens-house"
KIBBUTZ_PAIR = "kibbutz-childrens-house-no-implicit"
PROP_C = "care_assigned_by_sex"

# Every threshold is ASSUMED unless the plan states it; all are printed in the gate output.
SEED_RATE_MIN = 0.80  # plan: ">= 80% of seeds" ((a), (c))
A_STEPS = 60  # plan (a): "within 60 steps"
A_PROP = "binding_practised"  # dataset: the property that reads footbinding as in force (information line)
A_SHARE_HIGH = 0.80  # ASSUMED: late-window actor-role share of the collapse action at or above which it collapsed
A_PAYOFF_GRID = [1.0, 1.5, 2.0]  # ASSUMED: payoff of the collapse action (the entry's bind pays its own, 1.0)
A_SANCTION_GRID = [0.0, 1.0, 4.0]  # ASSUMED: sanction_weight axis (A4, A7)
A_SEEDS_MAX = 50  # ASSUMED (budget): seeds per (a) grid point, min(seeds, A_SEEDS_MAX)
B_ACTION_KEY = "committed_action"  # dataset: payoffs-block / entry key naming the new-convention action
B_PARAM = "committed_minority"  # plan (b): the swept share of committed agents (DEFAULT_PARAMS since slice 4)
B_SWEEP = [round(0.05 * i, 2) for i in range(1, 11)]  # plan (b): 0.05-0.50
B_JUMP = 0.5  # plan (b): "> 0.5 between adjacent sweep points"
C_HIGH = 0.90  # ASSUMED: late-window rate at or above which care counts as sex-assigned ("toward 1")
C_WINDOW = 0.20  # ASSUMED: share of the run averaged at each end for the early / late rates
C_FLAT_TOL = 0.10  # ASSUMED: tolerance on late - early for "ends below high" and on early - late for "rises"
C_FORBIDDEN = "assign(committee,male_member)"  # dataset: the instance kibbutz R2 forbids (action_label format)
C_FORBIDDEN_ROLE = "committee"  # dataset: the role R2 binds (the actor of C_FORBIDDEN)
C_SANCTION_GRID = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0]  # ASSUMED: sanction_weight axis (A4, A7)
C_PAYOFF_GRID = [1.0, 1.5, 2.0, 3.0]  # ASSUMED: payoff of C_FORBIDDEN; lawful actions pay default_payoff (1.0)
C_SHARE_LOW = 0.20  # ASSUMED: late-window share at or below which the forbidden instance counts as excluded
C_SHARE_HIGH = 0.80  # ASSUMED: late-window share at or above which it counts as adopted (the norm collapsed)
C_SEEDS_MAX = 50  # ASSUMED (budget): seeds per (c) grid point, min(seeds, C_SEEDS_MAX); 24 points x 2 entries x 100 ran 9 min
D_MIN_SEEDS = 100  # plan (d): ">= 100 seeds"
D_RHO_MIN = 0.90  # plan (d): "Spearman >= 0.9"

ASSUMPTIONS = {
    "SEED_RATE_MIN": SEED_RATE_MIN, "A_STEPS": A_STEPS, "A_PROP": A_PROP, "A_SHARE_HIGH": A_SHARE_HIGH,
    "A_PAYOFF_GRID": A_PAYOFF_GRID, "A_SANCTION_GRID": A_SANCTION_GRID, "A_SEEDS_MAX": A_SEEDS_MAX,
    "B_ACTION_KEY": B_ACTION_KEY, "B_PARAM": B_PARAM, "B_SWEEP": B_SWEEP, "B_JUMP": B_JUMP, "C_HIGH": C_HIGH, "C_WINDOW": C_WINDOW, "C_FLAT_TOL": C_FLAT_TOL,
    "C_FORBIDDEN": C_FORBIDDEN, "C_FORBIDDEN_ROLE": C_FORBIDDEN_ROLE, "C_SANCTION_GRID": C_SANCTION_GRID,
    "C_PAYOFF_GRID": C_PAYOFF_GRID, "C_SHARE_LOW": C_SHARE_LOW, "C_SHARE_HIGH": C_SHARE_HIGH, "C_SEEDS_MAX": C_SEEDS_MAX,
    "D_MIN_SEEDS": D_MIN_SEEDS, "D_RHO_MIN": D_RHO_MIN, "D_HALVES": "first half of the seeds vs second half",
    "PROBE_STEPS": PROBE_STEPS, "EXIT_CODES": EXIT_CODES,
    "A_DEFINITIONS": ("per seed, grid point (sanction_weight x payoff of the collapse action), entry (FOOTBINDING, "
                      "A_PAIR or the entry minus its pledge actions) and configuration: collapsed = late-window mean "
                      "(last ceil(C_WINDOW*(A_STEPS+1)) values) of the actor role's share of the collapse action (the "
                      "base of the entry's `*_pledge` action) >= A_SHARE_HIGH; expected collapse (rate >= SEED_RATE_MIN) "
                      "iff the configuration has coordination and the entry has pledges, else persistence (rate <= "
                      "1 - SEED_RATE_MIN). PASS iff some grid point meets every expectation; FAIL named vacuous when "
                      "the collapse action is never adopted at any point. A_PROP trace at the default point is "
                      "information"),
    "B_DEFINITIONS": ("per coordination configuration and sweep point v of committed_minority: adoption = mean over "
                      "seeds of the actor role's last-step share of the entry's committed_action (committed agents "
                      "included, round(v*n) of n per role); PASS iff max adjacent jump > B_JUMP in every coordination "
                      "configuration"),
    "C_DEFINITIONS": ("per seed and grid point (sanction_weight x payoff of C_FORBIDDEN), late = mean over the last "
                      "ceil(C_WINDOW*(steps+1)) values (step 0 included): excluded = late share of C_FORBIDDEN in "
                      "C_FORBIDDEN_ROLE <= C_SHARE_LOW; adopted = late share >= C_SHARE_HIGH; out-pays = payoff > best "
                      "lawful payoff at step 0. PASS iff (KIBBUTZ) some sanction band is excluded in >= SEED_RATE_MIN "
                      "of seeds at every payoff AND every out-paying payoff is adopted in >= SEED_RATE_MIN of seeds at "
                      "some sanction_weight below the band; (KIBBUTZ_PAIR) every out-paying payoff is adopted at every "
                      "sanction_weight in >= SEED_RATE_MIN of seeds. FAIL named as vacuous when the excluded verdict is "
                      "independent of sanction_weight. Extra line (not a criterion): property rises toward 1 = late >= "
                      "C_HIGH and late >= early - C_FLAT_TOL; ends below high = late - early <= C_FLAT_TOL and late < "
                      "C_HIGH"),
}


@dataclass
class Criterion:
    key: str
    status: str  # PASS | FAIL | BLOCKED
    detail: str
    blocked_reason: str | None = None
    numbers: dict = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"key": self.key, "status": self.status, "detail": self.detail, "blocked_reason": self.blocked_reason,
                "numbers": self.numbers, "lines": self.lines}


@dataclass
class GateReport:
    criteria: list[Criterion]
    seeds: int
    configs_run: list[list[str]]
    configs_not_run: dict[str, str]
    settings: dict = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        if any(c.status == FAIL for c in self.criteria):
            return FAIL
        if any(c.status == BLOCKED for c in self.criteria):
            return BLOCKED
        return PASS

    @property
    def passed(self) -> bool:
        return self.verdict == PASS

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict]

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "passed": self.passed, "exit_code": self.exit_code, "seeds": self.seeds,
                "configs_run": self.configs_run, "configs_not_run": self.configs_not_run, "settings": self.settings,
                "assumptions": ASSUMPTIONS, "criteria": [c.to_dict() for c in self.criteria]}


# ------------------------------------------------------------------ configurations
def _cfg_key(cfg) -> str:
    return "+".join(cfg) if cfg else "{}"


def available_configs() -> tuple[list[tuple[str, ...]], dict[str, str]]:
    """(configurations the gate runs, {configuration: why not run}) over the plan's eight switch sets."""
    run: list[tuple[str, ...]] = []
    not_run: dict[str, str] = {}
    for r in range(len(MODULES) + 1):
        for cfg in itertools.combinations(MODULES, r):
            if not cfg:
                not_run[_cfg_key(cfg)] = ("not run: the bootstrap rule (an agent with no practice takes the best-paying "
                                          "candidate) belongs to the adaptive modules (material, coordination), so with "
                                          "no module no agent ever starts a practice and every run is static")
                continue
            try:
                _check_modules(cfg)
            except NotImplementedError as e:
                not_run[_cfg_key(cfg)] = str(e)
                continue
            run.append(cfg)
    return run, not_run


# ------------------------------------------------------------------ property traces through the reference
def property_trace(inst: InstitutionJSON, prop: Property, seed: int, steps: int, agents_per_role: int,
                   modules=("material",), payoffs: dict[str, float] | None = None, params: dict | None = None) -> list[int]:
    """The property's value (0/1) on the model's role-level state at steps 0..steps, evaluated through
    `Reference.prop` on the state as a one-step trace (never by fluent name)."""
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs, params=params)
    ast = sx.parse(prop.formal)
    vals = [int(m.ref.prop(ast, [m.state], 0))]
    for _ in range(steps):
        m.step()
        vals.append(int(m.ref.prop(ast, [m.state], 0)))
    return vals


def windows(vals: list[int | float]) -> tuple[float, float]:
    """(early, late): means over the first and last ceil(C_WINDOW * len) values."""
    w = max(1, math.ceil(C_WINDOW * len(vals)))
    return sum(vals[:w]) / w, sum(vals[-w:]) / w


def rises_toward_one(vals: list[int | float]) -> bool:
    early, late = windows(vals)
    return late >= C_HIGH and late >= early - C_FLAT_TOL


def ends_below_high(vals: list[int | float]) -> bool:
    """Late window below C_HIGH and no rise (a 1 -> 0 drop qualifies: this is not flatness; renamed from
    `stays_flat`, 2026-11-04 review finding 2)."""
    early, late = windows(vals)
    return (late - early) <= C_FLAT_TOL and late < C_HIGH


def _mean_trace(traces: list[list[int]]) -> list[float]:
    n = len(traces)
    return [sum(tr[t] for tr in traces) / n for t in range(len(traces[0]))] if traces else []


def _has_pledges(inst: InstitutionJSON) -> bool:
    names = {a.name for a in inst.actions}
    return any(n.endswith(PLEDGE_SUFFIX) and n[: -len(PLEDGE_SUFFIX)] in names for n in names)


def _pledge_names(inst: InstitutionJSON) -> list[str]:
    names = {a.name for a in inst.actions}
    return sorted(n for n in names if n.endswith(PLEDGE_SUFFIX) and n[: -len(PLEDGE_SUFFIX)] in names)


def ablate_pledges(inst: InstitutionJSON) -> InstitutionJSON:
    """The entry minus its `*_pledge` actions and every rule whose aim names one (ASSUMED stand-in for a
    dataset pair); the id gains `-no-pledge-ablated`."""
    pledges = set(_pledge_names(inst))
    d = inst.model_dump(mode="json")
    d["id"] = f"{inst.id}-no-pledge-ablated"
    d["actions"] = [a for a in d["actions"] if a["name"] not in pledges]
    d["rules"] = [r for r in d["rules"] if sx.parse(r["aim"]).pred not in pledges] if pledges else d["rules"]
    return InstitutionJSON.model_validate(d)


def name_share(row: dict[str, dict[str, float]], role: str, name: str) -> float:
    """The role's adoption share of every instance of action `name` in one `adoption_shares` row."""
    return sum(v for lab, v in row.get(role, {}).items() if lab.split("(", 1)[0] == name)


# ------------------------------------------------------------------ (a) footbinding
def a_run(inst: InstitutionJSON, prop_ast, seed: int, steps: int, agents_per_role: int, modules, payoffs: dict | None,
          params: dict, role: str, name: str) -> dict:
    """One (a) run: {share: the role's share of action `name` at steps 0..steps, prop: A_PROP at steps 0..steps
    through `Reference.prop` (all None when the property is missing)}."""
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs, params=params)
    share = [name_share(m.adoption_shares(), role, name)]
    prop = [int(m.ref.prop(prop_ast, [m.state], 0)) if prop_ast is not None else None]
    for _ in range(steps):
        m.step()
        share.append(name_share(m.adoption[-1], role, name))
        prop.append(int(m.ref.prop(prop_ast, [m.state], 0)) if prop_ast is not None else None)
    return {"share": share, "prop": prop}


def crit_a(by: dict, props: dict[str, Property], seeds: int, configs, not_run: dict[str, str],
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, payoffs_of=None, sanction_grid=None, payoff_grid=None,
           steps: int = A_STEPS) -> Criterion:
    sanction_grid = list(A_SANCTION_GRID if sanction_grid is None else sanction_grid)
    payoff_grid = list(A_PAYOFF_GRID if payoff_grid is None else payoff_grid)
    if FOOTBINDING not in by:
        return Criterion("a", BLOCKED, f"no {FOOTBINDING!r} institution in the dataset",
                         blocked_reason="no footbinding institution in the dataset")
    coord = [c for c in configs if "coordination" in c]
    if not coord:
        why = not_run.get("coordination", "coordination module not implemented")
        return Criterion("a", BLOCKED, f"{FOOTBINDING} present; coordination module not implemented ({why})",
                         blocked_reason="coordination module not implemented")
    inst = by[FOOTBINDING]
    pledges = _pledge_names(inst)
    bases = sorted({n[: -len(PLEDGE_SUFFIX)] for n in pledges})
    if len(bases) != 1:
        why = (f"{FOOTBINDING} has no `*_pledge` action: the collapse action (the pledge's base) is undefined"
               if not bases else f"{FOOTBINDING} has pledges for several actions {bases}: the collapse action is ambiguous")
        return Criterion("a", BLOCKED, why, blocked_reason=why)
    name = bases[0]
    if seeds < 1:
        return Criterion("a", BLOCKED, "seeds must be >= 1", blocked_reason="no seeds")
    base_pay = dict((payoffs_of(FOOTBINDING) if payoffs_of else None) or {})
    probe = InstitutionModel(inst, seed=0, agents_per_role=agents_per_role, modules=coord[0], payoffs=base_pay)
    roles = sorted({a[1][0] for a in probe.ref.action_insts if a[0] == name})
    if len(roles) != 1:
        why = f"collapse action {name!r} has actor roles {roles}; expected exactly one"
        return Criterion("a", BLOCKED, why, blocked_reason=why)
    role = roles[0]
    if A_PAIR in by:
        pair, pair_src = by[A_PAIR], f"dataset entry {A_PAIR}"
    else:
        pair, pair_src = ablate_pledges(inst), f"{FOOTBINDING} minus its pledge actions and their rules (ASSUMED, no {A_PAIR} entry)"
    pair_pay = dict((payoffs_of(A_PAIR) if payoffs_of and A_PAIR in by else None) or base_pay)
    prop = props.get(A_PROP)
    ast = sx.parse(prop.formal) if prop is not None else None
    seeds_asked, seeds = seeds, min(seeds, A_SEEDS_MAX)
    persist_max = round(1 - SEED_RATE_MIN, 9)  # rounded so 20/100 is not > 0.19999999999999996 (finding 6a)
    entries = [(FOOTBINDING, inst, base_pay, True), (pair.id, pair, pair_pay, _has_pledges(pair))]
    numbers: dict = {"collapse_action": name, "role": role, "pledge_actions": pledges, "pair": pair.id, "pair_source": pair_src,
                     "pair_has_pledges": _has_pledges(pair), "steps": steps, "seeds": seeds, "seeds_asked": seeds_asked,
                     "sanction_grid": sanction_grid, "payoff_grid": payoff_grid, "property": A_PROP if prop else None,
                     "grid": {}, "matching_points": [], "ever_collapsed": False}
    lines = [f"  collapse action {name} (base of {pledges}) in role {role!r}; ablated entry: {pair_src}"
             f"{'' if _has_pledges(pair) is False else ' (WARNING: it still has pledge actions)'}; late-window share >= "
             f"{A_SHARE_HIGH} = collapsed; {seeds} seed(s) per cell, {steps} steps"]
    if prop is None:
        lines.append(f"  property {A_PROP!r} not in properties.json: no property information line")
    for w in sanction_grid:
        numbers["grid"][str(w)] = {}
        for pv in payoff_grid:
            cell: dict = {"sanction_weight": w, "payoff": pv, "cells": {}, "match": True}
            for inst_id, e, pay0, has in entries:
                pay = dict(pay0, **{name: pv})
                for cfg in configs:
                    runs = [a_run(e, ast, s_, steps, agents_per_role, cfg, pay, {"sanction_weight": w}, role, name)
                            for s_ in range(seeds)]
                    late = [windows(r["share"])[1] for r in runs]
                    collapsed = [l >= A_SHARE_HIGH for l in late]
                    rate = sum(collapsed) / seeds
                    expect_collapse = ("coordination" in cfg) and has
                    good = (rate >= SEED_RATE_MIN) if expect_collapse else (rate <= persist_max)
                    cell["match"] &= good
                    numbers["ever_collapsed"] |= any(collapsed)
                    prop_late = None
                    if ast is not None:
                        prop_late = sum(windows(r["prop"])[1] for r in runs) / seeds
                    cell["cells"][f"{inst_id}|{_cfg_key(cfg)}"] = {
                        "entry": inst_id, "config": _cfg_key(cfg), "collapse_rate": rate, "mean_late_share": sum(late) / seeds,
                        "expected": "collapse" if expect_collapse else "persistence", "ok": good,
                        "property_late_mean": prop_late,
                        "per_seed": [{"seed": s_, "late_share": l, "collapsed": c} for s_, l, c in zip(range(seeds), late, collapsed)]}
            numbers["grid"][str(w)][str(pv)] = cell
            if cell["match"]:
                numbers["matching_points"].append({"sanction_weight": w, "payoff": pv})
            summ = "; ".join(f"{k}: {v['collapse_rate']:.0%}{'' if v['ok'] else ' NOT ok'}" for k, v in cell["cells"].items())
            lines.append(f"  sanction_weight={w} payoff({name})={pv}: {'MATCH' if cell['match'] else 'no match'} [{summ}]")
    dw = DEFAULT_PARAMS["sanction_weight"]
    dp = base_pay.get(name, DEFAULT_PARAMS["default_payoff"])
    if ast is not None and dw in sanction_grid and dp in payoff_grid:
        info = {k: v["property_late_mean"] for k, v in numbers["grid"][str(dw)][str(dp)]["cells"].items()}
        lines.append(f"  information (not a criterion): {A_PROP} late-window mean at the entry's own point "
                     f"sanction_weight={dw}, payoff({name})={dp}: " + ", ".join(f"{k} {v:.2f}" for k, v in info.items())
                     + "; under shared role-level state the property flips only when every family leaves unbound in one step")
    if seeds < seeds_asked:
        lines.append(f"  budget: (a) ran {seeds} of the {seeds_asked} seeds per cell (A_SEEDS_MAX={A_SEEDS_MAX})")
    ok = bool(numbers["matching_points"])
    if not numbers["ever_collapsed"]:
        detail = (f"vacuous: {name} is never adopted (late share >= {A_SHARE_HIGH}) by any seed at any grid point under any "
                  f"configuration or entry; nothing collapses")
        return Criterion("a", FAIL, detail, numbers=numbers, lines=lines)
    detail = (f"iff pattern (collapse under coordination with pledges, persistence otherwise) holds at grid points "
              f"{numbers['matching_points'] or 'NONE'} of {len(sanction_grid) * len(payoff_grid)} (sanction_weight x "
              f"payoff of {name}); min {SEED_RATE_MIN:.0%} of {seeds} seeds per cell; {len(configs)} configuration(s)")
    return Criterion("a", PASS if ok else FAIL, detail, numbers=numbers, lines=lines)


# ------------------------------------------------------------------ (b) committed minority
def crit_b(by: dict, props: dict[str, Property], seeds: int, configs, not_run: dict[str, str],
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, steps: int = DEFAULT_STEPS, payoffs_of=None,
           sweep_points=None) -> Criterion:
    sweep_points = list(B_SWEEP if sweep_points is None else sweep_points)
    if NAMING not in by:
        return Criterion("b", BLOCKED, f"no {NAMING!r} institution in the dataset",
                         blocked_reason="no naming-convention institution in the dataset")
    coord = [c for c in configs if "coordination" in c]
    if not coord:
        why = not_run.get("coordination", "coordination module not implemented")
        return Criterion("b", BLOCKED, f"{NAMING} present; coordination module not implemented ({why})",
                         blocked_reason="coordination module not implemented")
    if B_PARAM not in DEFAULT_PARAMS:
        return Criterion("b", BLOCKED, f"{B_PARAM!r} is not a model parameter (DEFAULT_PARAMS); the sweep cannot run",
                         blocked_reason=f"{B_PARAM} is not a model parameter")
    inst = by[NAMING]
    pay = dict((payoffs_of(NAMING) if payoffs_of else None) or {})
    _, reserved = split_payoffs(pay)
    spec = reserved.get(B_ACTION_KEY)
    if not spec:
        why = (f"{NAMING} names no {B_ACTION_KEY!r} (payoffs block or entry key): the new-convention action the "
               f"committed minority holds is a dataset input, not a gate constant")
        return Criterion("b", BLOCKED, why, blocked_reason=why)
    if seeds < 1:
        return Criterion("b", BLOCKED, "seeds must be >= 1", blocked_reason="no seeds")
    try:
        probe = InstitutionModel(inst, seed=0, agents_per_role=agents_per_role, modules=coord[0], payoffs=pay)
        target = probe.committed_action
    except (ValueError, NotImplementedError) as e:
        return Criterion("b", BLOCKED, str(e), blocked_reason=str(e))
    name, role = target[0], target[1][0]
    numbers: dict = {"committed_action": action_label(target), "role": role, "sweep": sweep_points, "steps": steps,
                     "seeds": seeds, "adoption_by_point": {}, "max_jump": {}, "jump_at": {}, "committed_share_by_point": {},
                     "per_seed": {}}
    lines, ok = [], True
    for cfg in coord:
        key = _cfg_key(cfg)
        adoption, committed_share, per_seed = [], [], {}
        for v in sweep_points:
            finals = []
            cs = None
            for s_ in range(seeds):
                try:
                    m = InstitutionModel(inst, seed=s_, agents_per_role=agents_per_role, modules=cfg, payoffs=pay,
                                         params={B_PARAM: v})
                except (ValueError, NotImplementedError) as e:
                    return Criterion("b", BLOCKED, str(e), blocked_reason=str(e), numbers=numbers)
                for _ in range(steps):
                    m.step()
                finals.append(name_share(m.adoption[-1], role, name))
                cs = m.committed_shares().get(role, 0.0)
            adoption.append(sum(finals) / seeds)
            committed_share.append(cs)
            per_seed[str(v)] = finals
        jumps = [b - a for a, b in zip(adoption, adoption[1:])]
        mj = max(jumps) if jumps else 0.0
        at = jumps.index(mj) if jumps else None
        numbers["adoption_by_point"][key] = dict(zip(map(str, sweep_points), adoption))
        numbers["committed_share_by_point"][key] = dict(zip(map(str, sweep_points), committed_share))
        numbers["max_jump"][key] = mj
        numbers["jump_at"][key] = [sweep_points[at], sweep_points[at + 1]] if at is not None else None
        numbers["per_seed"][key] = per_seed
        good = mj > B_JUMP
        ok &= good
        lines.append(f"  {key}: last-step share of {name} in {role!r} by {B_PARAM} "
                     f"{[round(x, 2) for x in adoption]} (committed share {[round(x, 2) for x in committed_share]}); "
                     f"max adjacent jump {mj:.2f} at {numbers['jump_at'][key]} ({'>' if good else '<='} {B_JUMP}): "
                     f"{'ok' if good else 'NOT ok'}")
    lines.append("  reviewer item (not mechanical): no constant in the code may set the tipping location (the sweep "
                 "resolution sets sharpness only; thresholds are U(0, threshold_max), swept); Centola's band is "
                 "recorded in the dataset, not asserted by the model")
    return Criterion("b", PASS if ok else FAIL, f"max adjacent jump {numbers['max_jump']} at {numbers['jump_at']} "
                     f"(min > {B_JUMP}; {seeds} seeds per point, {steps} steps)", numbers=numbers, lines=lines)


# ------------------------------------------------------------------ (c) kibbutz regendering
def _parse_label(label: str) -> tuple[str, tuple[str, ...]]:
    """`action_label` inverse: "assign(committee,male_member)" -> ("assign", ("committee", "male_member"))."""
    if "(" not in label or not label.endswith(")"):
        raise ValueError(f"{label!r} is not an action instance label (name(role,...))")
    name, rest = label[:-1].split("(", 1)
    return name, tuple(x for x in rest.split(",") if x)


def c_run(inst: InstitutionJSON, prop_ast, seed: int, steps: int, agents_per_role: int, modules, payoffs: dict | None,
          params: dict, role: str, label: str) -> dict:
    """One (c) run: {share: the role's adoption share of `label` at steps 0..steps (step 0 = 0.0), prop: PROP_C at
    steps 0..steps through `Reference.prop`, candidate: was `label` ever in a `role` agent's candidate set}."""
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs, params=params)
    target = _parse_label(label)
    share = [m.adoption_shares().get(role, {}).get(label, 0.0)]
    prop = [int(m.ref.prop(prop_ast, [m.state], 0))]
    candidate = False
    for _ in range(steps):
        m.step()
        share.append(m.adoption[-1].get(role, {}).get(label, 0.0))
        prop.append(int(m.ref.prop(prop_ast, [m.state], 0)))
        candidate = candidate or any(target in a.last_candidates for a in m.by_role.get(role, []))
    return {"share": share, "prop": prop, "candidate": candidate}


def _c_table(entry: dict, inst_id: str, role: str, label: str, seeds: int) -> list[str]:
    """Compact text table: rows sanction_weight, columns payoff; cell = mean late share, then the flag E (excluded
    in >= SEED_RATE_MIN of seeds) / A (adopted in >= SEED_RATE_MIN) / - with that flag's seed rate."""
    ws, ps = entry["sanction_grid"], entry["payoff_grid"]
    out = [f"  {inst_id}: mean late share of {label} in {role} [E=excluded / A=adopted in the shown share of "
           f"{seeds} seeds; min {SEED_RATE_MIN:.0%}]; out-paying payoffs {entry['out_paying']} (best lawful "
           f"{entry['lawful_best']})"]
    out.append("  sanction_weight \\ payoff " + "".join(f"{p:>12}" for p in ps))
    for w in ws:
        cells = []
        for p in ps:
            g = entry["grid"][str(w)][str(p)]
            if g["excluded_rate"] >= SEED_RATE_MIN:
                flag = f"E{g['excluded_rate']:.0%}"
            elif g["adopted_rate"] >= SEED_RATE_MIN:
                flag = f"A{g['adopted_rate']:.0%}"
            else:
                flag = "-"
            cells.append(f"{g['mean_late_share']:.2f} {flag}")
        out.append(f"  {w:<24}" + "".join(f"{c:>12}" for c in cells))
    return out


def crit_c(by: dict, props: dict[str, Property], seeds: int, configs, steps: int = DEFAULT_STEPS,
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, payoffs_of=None, forbidden: str = C_FORBIDDEN,
           role: str = C_FORBIDDEN_ROLE, sanction_grid=None, payoff_grid=None) -> Criterion:
    sanction_grid = list(C_SANCTION_GRID if sanction_grid is None else sanction_grid)
    payoff_grid = list(C_PAYOFF_GRID if payoff_grid is None else payoff_grid)
    missing = [i for i in (KIBBUTZ, KIBBUTZ_PAIR) if i not in by]
    if missing:
        return Criterion("c", BLOCKED, f"missing institutions {missing}", blocked_reason=f"missing institutions {missing}")
    prop = props.get(PROP_C)
    if prop is None:
        return Criterion("c", BLOCKED, f"property {PROP_C!r} not in properties.json", blocked_reason=f"no property {PROP_C}")
    if not configs:
        return Criterion("c", BLOCKED, "no module configuration can run", blocked_reason="no runnable module configuration")
    if seeds < 1:
        return Criterion("c", BLOCKED, "seeds must be >= 1", blocked_reason="no seeds")
    try:
        target = _parse_label(forbidden)
    except ValueError as e:
        return Criterion("c", BLOCKED, str(e), blocked_reason=str(e))
    ast = sx.parse(prop.formal)
    seeds_asked, seeds = seeds, min(seeds, C_SEEDS_MAX)  # budget cap per grid point, stated in the output
    numbers: dict = {"property": PROP_C, "steps": steps, "seeds": seeds, "seeds_asked": seeds_asked, "forbidden": forbidden, "role": role,
                     "sanction_grid": sanction_grid, "payoff_grid": payoff_grid, "by_config": {}}
    lines, ok, blocked = [], True, None
    for cfg in configs:
        key = _cfg_key(cfg)
        entry: dict = {}
        for inst_id in (KIBBUTZ, KIBBUTZ_PAIR):
            inst = by[inst_id]
            base_pay = dict((payoffs_of(inst_id) if payoffs_of else None) or {})
            probe = InstitutionModel(inst, seed=0, agents_per_role=agents_per_role, modules=cfg, payoffs=base_pay)
            if target not in probe.ref.action_insts:
                blocked = f"{forbidden} is not an action instance of {inst_id}"
                break
            if role not in probe.roles or target not in probe.available_for(role):
                blocked = f"{forbidden} is never available to {role!r} in {inst_id} at step 0 (no may/must rule names it)"
                break
            lawful_best = max([probe.payoff(a) for a in probe.available_for(role) if a not in probe.forbidden_for(role)]
                              + [0.0])
            e: dict = {"sanction_grid": sanction_grid, "payoff_grid": payoff_grid, "lawful_best": lawful_best,
                       "out_paying": [p for p in payoff_grid if p > lawful_best], "forbidden_at_step0":
                       target in probe.forbidden_for(role), "grid": {}, "ever_candidate": False}
            for w in sanction_grid:
                e["grid"][str(w)] = {}
                for p in payoff_grid:
                    pay = dict(base_pay, **{forbidden: p})
                    runs = [c_run(inst, ast, s, steps, agents_per_role, cfg, pay, {"sanction_weight": w}, role, forbidden)
                            for s in range(seeds)]
                    late_share = [windows(r["share"])[1] for r in runs]
                    pw = [windows(r["prop"]) for r in runs]
                    excl = [ls <= C_SHARE_LOW for ls in late_share]
                    adop = [ls >= C_SHARE_HIGH for ls in late_share]
                    e["ever_candidate"] |= any(r["candidate"] for r in runs)
                    e["grid"][str(w)][str(p)] = {
                        "sanction_weight": w, "payoff": p, "mean_late_share": sum(late_share) / seeds,
                        "excluded_rate": sum(excl) / seeds, "adopted_rate": sum(adop) / seeds,
                        "property_rises_rate": sum(rises_toward_one(r["prop"]) for r in runs) / seeds,
                        "property_ends_below_high_rate": sum(ends_below_high(r["prop"]) for r in runs) / seeds,
                        "property_late_mean": sum(l for _, l in pw) / seeds,
                        "property_early_mean": sum(ea for ea, _ in pw) / seeds,
                        "per_seed": [{"seed": s, "late_share": ls, "property_early": ea, "property_late": l,
                                      "candidate": r["candidate"]}
                                     for s, ls, (ea, l), r in zip(range(seeds), late_share, pw, runs)]}
            entry[inst_id] = e
        if blocked:
            break
        if not any(entry[i]["ever_candidate"] for i in (KIBBUTZ, KIBBUTZ_PAIR)):
            blocked = (f"{forbidden} was never a candidate for any {role!r} agent at any grid point in either entry: "
                       f"no payoff key reaches it, the sweep is vacuous")
            break
        # --- KIBBUTZ: a sanction band excludes it at every payoff; below the band every out-paying payoff adopts it
        k = entry[KIBBUTZ]
        g = k["grid"]
        excluded_at = lambda w, p: g[str(w)][str(p)]["excluded_rate"] >= SEED_RATE_MIN
        adopted_at = lambda w, p: g[str(w)][str(p)]["adopted_rate"] >= SEED_RATE_MIN
        band = [w for w in sanction_grid if all(excluded_at(w, p) for p in payoff_grid)]
        out_paying = k["out_paying"]
        below = {str(p): [w for w in sanction_grid if band and w < min(band) and adopted_at(w, p)] for p in out_paying}
        independent = bool(out_paying) and all(len({excluded_at(w, p) for w in sanction_grid}) == 1 for p in out_paying)
        k_ok = bool(band) and bool(out_paying) and all(below[str(p)] for p in out_paying)
        k.update(band=band, adopted_below_band=below, excluded_independent_of_sanction=independent, ok=k_ok)
        # --- KIBBUTZ_PAIR: adopted everywhere it out-pays, whatever the sanction weight
        q = entry[KIBBUTZ_PAIR]
        qg = q["grid"]
        q_out = q["out_paying"]
        q_fail = [(w, p) for p in q_out for w in sanction_grid if qg[str(w)][str(p)]["adopted_rate"] < SEED_RATE_MIN]
        q_ok = bool(q_out) and not q_fail
        q.update(not_adopted_at=q_fail, ok=q_ok)
        ok &= k_ok and q_ok
        numbers["by_config"][key] = entry
        lines.append(f"  {key} {KIBBUTZ}: sanction band excluding {forbidden} at every payoff: {band or 'NONE'}; "
                     f"out-paying payoffs adopted below the band at sanction_weight {below}; excluded verdict "
                     f"independent of sanction_weight: {'YES (vacuous)' if independent else 'no'}: "
                     f"{'ok' if k_ok else 'NOT ok'}")
        lines.append(f"  {key} {KIBBUTZ_PAIR}: out-paying payoffs {q_out} adopted at every sanction_weight: "
                     f"{'yes' if q_ok else 'NOT ok, not adopted at (sanction_weight, payoff) ' + str(q_fail)}")
        for inst_id in (KIBBUTZ, KIBBUTZ_PAIR):
            lines.extend(_c_table(entry[inst_id], inst_id, role, forbidden, seeds))
        dw, dp = DEFAULT_PARAMS["sanction_weight"], DEFAULT_PARAMS["default_payoff"]
        if dw in sanction_grid and dp in payoff_grid:
            kd, qd = g[str(dw)][str(dp)], qg[str(dw)][str(dp)]
            lines.append(f"  extra (not a criterion), property trace at the default point sanction_weight={dw}, "
                         f"payoff={dp}: {KIBBUTZ} {PROP_C} rises toward 1 in {kd['property_rises_rate']:.0%} of seeds "
                         f"(late mean {kd['property_late_mean']:.2f}); {KIBBUTZ_PAIR} ends_below_high in "
                         f"{qd['property_ends_below_high_rate']:.0%} (late mean {qd['property_late_mean']:.2f}); "
                         f"ends_below_high accepts a 1 -> 0 drop (finding 2)")
        if seeds < seeds_asked:
            lines.append(f"  budget: (c) ran {seeds} of the {seeds_asked} seeds at each of the "
                         f"{len(sanction_grid) * len(payoff_grid)} grid points per entry (C_SEEDS_MAX={C_SEEDS_MAX})")
        lines.append(f"  note: under shared role-level state one adopting agent breaks {PROP_C} for all and `release` "
                     f"is never available, so the property stays false after the committee returns to lawful "
                     f"assignment; the share is the reading, the property is reported per grid point in JSON")
    if blocked:
        return Criterion("c", BLOCKED, blocked, blocked_reason=blocked, numbers=numbers, lines=lines)
    summary = "; ".join(f"{k}: {KIBBUTZ} band {v[KIBBUTZ]['band'] or 'NONE'}, adopted below band "
                        f"{v[KIBBUTZ]['adopted_below_band']}, {KIBBUTZ_PAIR} adopted everywhere it out-pays: "
                        f"{'yes' if v[KIBBUTZ_PAIR]['ok'] else 'no'}"
                        for k, v in numbers["by_config"].items())
    return Criterion("c", PASS if ok else FAIL, f"{summary} (min {SEED_RATE_MIN:.0%} of {seeds} seeds per grid point; "
                     f"{len(configs)} configuration(s) run)", numbers=numbers, lines=lines)


# ------------------------------------------------------------------ (d) seed stability
def crit_d(insts: list[InstitutionJSON], seeds: int, configs, steps: int = DEFAULT_STEPS,
           probe_steps: int = PROBE_STEPS, agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, payoffs_of=None) -> Criterion:
    if not configs:
        return Criterion("d", BLOCKED, "no module configuration can run", blocked_reason="no runnable module configuration")
    if seeds < 2:
        return Criterion("d", BLOCKED, "needs at least 2 seeds to split", blocked_reason="too few seeds")
    half = seeds // 2
    numbers: dict = {"seeds": seeds, "halves": [[0, half - 1], [half, seeds - 1]], "by_config": {}}
    lines, ok = [], True
    for cfg in configs:
        key = _cfg_key(cfg)
        totals: dict[str, list[float]] = {}
        errors: dict[str, str] = {}
        summaries: list[dict] = []
        for inst in insts:
            try:
                pay = payoffs_of(inst.id) if payoffs_of else None
                sm = score(inst, seeds, steps=steps, probe_steps=probe_steps, agents_per_role=agents_per_role,
                           modules=cfg, payoffs=pay)
            except Exception as e:  # listed as an error, never skipped silently
                errors[inst.id] = f"{type(e).__name__}: {e}"
                continue
            summaries.append(sm)
            totals[inst.id] = [ps["total"]["value"] for ps in sm["per_seed"]]
        ids = sorted(totals)
        mean_a = [sum(totals[i][:half]) / half for i in ids]
        mean_b = [sum(totals[i][half:]) / (seeds - half) for i in ids]
        rho = spearman(mean_a, mean_b) if ids else None
        rank_a = sorted(ids, key=lambda i: -mean_a[ids.index(i)])
        rank_b = sorted(ids, key=lambda i: -mean_b[ids.index(i)])
        # average ranks (ties share the mean of the ranks they span), the ranks `spearman` uses (finding 3b)
        avg_a = dict(zip(ids, ranks([-x for x in mean_a]))) if ids else {}
        avg_b = dict(zip(ids, ranks([-x for x in mean_b]))) if ids else {}
        mm = {sm["institution"]: sm["total"].get("mean_measured") for sm in summaries}
        dis = disagreement(summaries)
        entry = {"rho": rho, "institutions": len(ids), "errors": errors,
                 "mean_total_half_a": dict(zip(ids, mean_a)), "mean_total_half_b": dict(zip(ids, mean_b)),
                 "ranking_half_a": rank_a, "ranking_half_b": rank_b, "avg_rank_half_a": avg_a, "avg_rank_half_b": avg_b,
                 "mean_measured_total": mm, "disagreement_pairs": dis,
                 "nulls": {sm["institution"]: sm["nulls"] for sm in summaries},
                 "scores": {sm["institution"]: {"freedom": sm["freedom"], "flourishing": sm["flourishing"],
                                                 "freedom_sum": sm["freedom_sum"], "flourishing_sum": sm["flourishing_sum"],
                                                 "total": sm["total"]} for sm in summaries}}
        numbers["by_config"][key] = entry
        good = rho is not None and rho >= D_RHO_MIN and not errors
        ok &= good
        rho_s = "undefined (no rank variance in a half)" if rho is None else f"{rho:.3f}"
        lines.append(f"  {key}: Spearman {rho_s} over {len(ids)} institutions, halves of {half}/{seeds - half} seeds "
                     f"(min {D_RHO_MIN}); {len(errors)} error(s); {len(dis)} freedom/flourishing disagreement pair(s): "
                     f"{'ok' if good else 'NOT ok'}")
        lines.append("  caveat: (d) is necessary, not sufficient (a role-count scorer would be as stable); the freedom "
                     "components are static per role on this dataset, so their seed variance is role sampling only; "
                     "ranked on the summed score (nulls excluded), mean over measured components printed beside it")

        tie_a = {r for r in avg_a.values() if list(avg_a.values()).count(r) > 1}
        tie_b = {r for r in avg_b.values() if list(avg_b.values()).count(r) > 1}
        for i in ids:
            ra, rb = avg_a[i], avg_b[i]
            lines.append(f"    {i}: total half A {mean_a[ids.index(i)]:.3f} (avg rank {ra:g}{' tie' if ra in tie_a else ''}), "
                         f"half B {mean_b[ids.index(i)]:.3f} (avg rank {rb:g}{' tie' if rb in tie_b else ''}); "
                         f"mean over measured components {mm.get(i) if mm.get(i) is None else format(mm[i], '.3f')}")
        for i, e in errors.items():
            lines.append(f"    error {i}: {e}")
        for d in dis:
            lines.append(f"    disagreement {d['a']} vs {d['b']}: freedom {d['freedom']}, flourishing {d['flourishing']}")
    rhos = {k: v["rho"] for k, v in numbers["by_config"].items()}
    n_err = sum(len(v["errors"]) for v in numbers["by_config"].values())
    detail = f"Spearman {rhos} (min {D_RHO_MIN}) over {len(insts)} institutions, {n_err} error(s)"
    if seeds < D_MIN_SEEDS:
        return Criterion("d", BLOCKED, f"{detail}; computed on {seeds} seeds, the plan requires >= {D_MIN_SEEDS}",
                         blocked_reason=f"fewer than {D_MIN_SEEDS} seeds ({seeds})", numbers=numbers, lines=lines)
    return Criterion("d", PASS if ok else FAIL, detail, numbers=numbers, lines=lines)


# ------------------------------------------------------------------ the gate
def run_gate(insts: list[InstitutionJSON], props: dict[str, Property], seeds: int, steps: int = DEFAULT_STEPS,
             probe_steps: int = PROBE_STEPS, agents_per_role: int = DEFAULT_AGENTS_PER_ROLE,
             institutions_path=None) -> GateReport:
    by = {i.id: i for i in insts}
    configs, not_run = available_configs()
    payoffs_of = (lambda i: load_payoffs(institutions_path, i)) if institutions_path else None
    crits = [crit_a(by, props, seeds, configs, not_run, agents_per_role, payoffs_of),
             crit_b(by, props, seeds, configs, not_run, agents_per_role, steps, payoffs_of),
             crit_c(by, props, seeds, configs, steps, agents_per_role, payoffs_of),
             crit_d(insts, seeds, configs, steps, probe_steps, agents_per_role, payoffs_of)]
    return GateReport(crits, seeds, [list(c) for c in configs], not_run,
                      {"steps": steps, "probe_steps": probe_steps, "agents_per_role": agents_per_role,
                       "institutions": len(insts)})


def format_gate(rep: GateReport, verbose: bool = False) -> str:
    rows = [("criterion", "status", "detail")]
    for c in rep.criteria:
        if c.status == BLOCKED:
            # a BLOCKED letter's computed detail travels with the text (finding 7), not only the JSON
            same = c.detail.replace("'", "") == (c.blocked_reason or "").replace("'", "")
            extra = f"; computed: {c.detail}" if c.detail and not same else ""
            rows.append((c.key, c.status, f"blocked: {c.blocked_reason}{extra}"))
        else:
            rows.append((c.key, c.status, c.detail))
    w0 = max(len(r[0]) for r in rows); w1 = max(len(r[1]) for r in rows)
    out = [f"{r[0]:<{w0}}  {r[1]:<{w1}}  {r[2]}" for r in rows]
    out.insert(1, "-" * (w0 + w1 + 4) + "-" * 40)
    out.append("")
    out.append(f"GATE {rep.verdict}  (exit {rep.exit_code}; any BLOCKED letter blocks the gate, any FAIL fails it)")
    out.append(f"seeds {rep.seeds}; configurations run: {[ '+'.join(c) for c in rep.configs_run]}; "
               f"settings {rep.settings}")
    out.append("configurations not run:")
    out.extend(f"  {k}: {v}" for k, v in rep.configs_not_run.items())
    out.append("assumed thresholds: " + ", ".join(f"{k}={v}" for k, v in ASSUMPTIONS.items()
                                                  if k not in ("C_DEFINITIONS", "EXIT_CODES")))
    out.append(f"  (c) definitions: {ASSUMPTIONS['C_DEFINITIONS']}")
    for c in rep.criteria:
        if c.lines:  # a BLOCKED letter's computed lines are printed too (finding 7); --verbose adds per-item lines
            out.append("")
            out.append(f"[{c.key}]")
            out.extend(c.lines if verbose else [l for l in c.lines if not l.startswith("    ")])
    return "\n".join(out)
