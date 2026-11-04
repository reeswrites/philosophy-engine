"""Layer-2 gate, `phil abm gate` (plan: plans/layer2-abm.md, "Pass tests (`phil abm gate`)"; mirrors
rules_gate: lettered criteria, precommitted expectations read from the dataset, PASS/FAIL table).

A criterion is PASS, FAIL or BLOCKED. BLOCKED means the check cannot run yet and says why (an institution the
dataset does not have, a mechanism module that is still a stub, a parameter the model does not take, too few
seeds); it is never a silent pass or a skip. Verdict: FAIL if any criterion fails, else BLOCKED if any is
blocked, else PASS.

(a) footbinding collapse (Mackie 1996): a `footbinding` institution collapses within A_STEPS in >= SEED_RATE_MIN
    of seeds iff `coordination` is on and pledge actions exist (`*_pledge`, A3); with either absent it persists.
    Collapse (ASSUMED): the dataset property A_PROP holds at step 0 and is false at step A_STEPS. Today BLOCKED:
    no `footbinding` institution; then the coordination module.
(b) committed minority: sweep B_PARAM over B_SWEEP on a `naming-convention` institution; pass iff the adoption
    of B_PROP (mean over seeds at the last step) jumps by more than B_JUMP between adjacent sweep points. "No
    constant in the code sets the location" is a reviewer item the gate prints, not a mechanical check. Today
    BLOCKED: no `naming-convention` institution; the coordination module; B_PARAM is not a model parameter.
(c) kibbutz regendering: PROP_C (`care_assigned_by_sex`, the dataset property, evaluated per step on the model's
    role-level state through `Reference.prop`, never by fluent name) on KIBBUTZ rises toward 1 in >= SEED_RATE_MIN
    of seeds and on KIBBUTZ_PAIR (the entry minus the implicit rule) stays flat in >= SEED_RATE_MIN of seeds, under
    every module configuration the engine can run. Definitions (ASSUMED, printed in the output): with v_t the
    property's value at steps 0..steps, early = mean over the first ceil(C_WINDOW*(steps+1)) values and late the
    mean over the last as many; "rises toward 1" = late >= C_HIGH and late >= early - C_FLAT_TOL (ends
    sex-assigned, did not fall); "flat" = late - early <= C_FLAT_TOL and late < C_HIGH (no rise, does not end
    sex-assigned). The dataset's initial state already satisfies PROP_C at t=0, so on KIBBUTZ the "rise" clause is
    degenerate and the check reads as persistence at 1; the pair is what separates the two.
(d) seed stability: rank the institutions by the mean summed veil-of-ignorance score (`score.py`; nulls excluded)
    over each of two disjoint halves of the seeds (first half / second half, ASSUMED) and require Spearman >=
    D_RHO_MIN for every module configuration run; needs >= D_MIN_SEEDS seeds, else BLOCKED. Institutions whose
    runs raise are listed as errors and fail the criterion. Disagreement pairs (freedom vs flourishing) are
    printed as information.

Module configurations: of the plan's eight, the gate runs those `_check_modules` accepts, minus the empty set.
The stubs (`coordination`, `imagination`) make six unavailable; the empty set is listed as not run because the
bootstrap rule (an agent with no practice takes the best-paying candidate) belongs to the material module, so
under {} no agent ever starts a practice and every run is static (slice-3 scope: material only).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from .. import sexpr as sx
from ..schemas_rules import InstitutionJSON, Property
from .model import (DEFAULT_AGENTS_PER_ROLE, DEFAULT_PARAMS, DEFAULT_STEPS, MODULES, InstitutionModel, _check_modules,
                    load_payoffs)
from .score import PROBE_STEPS, disagreement, score, spearman

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
EXIT_CODES = {PASS: 0, FAIL: 1, BLOCKED: 2}  # ASSUMED (rules_gate has no BLOCKED); load/usage errors exit 3

FOOTBINDING = "footbinding"
NAMING = "naming-convention"
KIBBUTZ = "kibbutz-childrens-house"
KIBBUTZ_PAIR = "kibbutz-childrens-house-no-implicit"
PROP_C = "care_assigned_by_sex"

# Every threshold is ASSUMED unless the plan states it; all are printed in the gate output.
SEED_RATE_MIN = 0.80  # plan: ">= 80% of seeds" ((a), (c))
A_STEPS = 60  # plan (a): "within 60 steps"
A_PROP = "binding_practised"  # ASSUMED placeholder: the dataset property that reads footbinding as in force
B_PROP = "new_convention_adopted"  # ASSUMED placeholder: the property that reads the new name as adopted
B_PARAM = "committed_minority"  # plan (b): the swept share of committed agents (not a model parameter yet)
B_SWEEP = [round(0.05 * i, 2) for i in range(1, 11)]  # plan (b): 0.05-0.50
B_JUMP = 0.5  # plan (b): "> 0.5 between adjacent sweep points"
C_HIGH = 0.90  # ASSUMED: late-window rate at or above which care counts as sex-assigned ("toward 1")
C_WINDOW = 0.20  # ASSUMED: share of the run averaged at each end for the early / late rates
C_FLAT_TOL = 0.10  # ASSUMED: tolerance on late - early for "flat" and on early - late for "rises"
D_MIN_SEEDS = 100  # plan (d): ">= 100 seeds"
D_RHO_MIN = 0.90  # plan (d): "Spearman >= 0.9"

ASSUMPTIONS = {
    "SEED_RATE_MIN": SEED_RATE_MIN, "A_STEPS": A_STEPS, "A_PROP": A_PROP, "B_PROP": B_PROP, "B_PARAM": B_PARAM,
    "B_SWEEP": B_SWEEP, "B_JUMP": B_JUMP, "C_HIGH": C_HIGH, "C_WINDOW": C_WINDOW, "C_FLAT_TOL": C_FLAT_TOL,
    "D_MIN_SEEDS": D_MIN_SEEDS, "D_RHO_MIN": D_RHO_MIN, "D_HALVES": "first half of the seeds vs second half",
    "PROBE_STEPS": PROBE_STEPS, "EXIT_CODES": EXIT_CODES,
    "C_DEFINITIONS": ("rises toward 1: late >= C_HIGH and late >= early - C_FLAT_TOL; flat: late - early <= "
                      "C_FLAT_TOL and late < C_HIGH; early/late = mean of the property over the first/last "
                      "ceil(C_WINDOW*(steps+1)) steps (step 0 included)"),
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
                                          "candidate) is the material module's, so with no module no agent ever starts "
                                          "a practice and every run is static (slice 3 is scoped to material)")
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


def stays_flat(vals: list[int | float]) -> bool:
    early, late = windows(vals)
    return (late - early) <= C_FLAT_TOL and late < C_HIGH


def _mean_trace(traces: list[list[int]]) -> list[float]:
    n = len(traces)
    return [sum(tr[t] for tr in traces) / n for t in range(len(traces[0]))] if traces else []


def _has_pledges(inst: InstitutionJSON) -> bool:
    names = {a.name for a in inst.actions}
    return any(n.endswith("_pledge") and n[: -len("_pledge")] in names for n in names)


# ------------------------------------------------------------------ (a) footbinding
def crit_a(by: dict, props: dict[str, Property], seeds: int, configs, not_run: dict[str, str],
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, payoffs_of=None) -> Criterion:
    if FOOTBINDING not in by:
        return Criterion("a", BLOCKED, f"no {FOOTBINDING!r} institution in the dataset",
                         blocked_reason="no footbinding institution in the dataset")
    coord = [c for c in configs if "coordination" in c]
    if not coord:
        why = not_run.get("coordination", "coordination module not implemented")
        return Criterion("a", BLOCKED, f"{FOOTBINDING} present; coordination module not implemented ({why})",
                         blocked_reason="coordination module not implemented")
    # body (runs once the blockers lift): collapse within A_STEPS iff coordination on and pledges exist
    inst = by[FOOTBINDING]
    prop = props.get(A_PROP)
    if prop is None:
        return Criterion("a", FAIL, f"property {A_PROP!r} (ASSUMED name) not in properties.json: collapse undefined")
    pledges = _has_pledges(inst)
    numbers: dict = {"pledge_actions": pledges, "collapse_rate": {}}
    lines, ok = [], True
    pay = payoffs_of(FOOTBINDING) if payoffs_of else None
    for cfg in configs:
        collapsed = 0
        for s in range(seeds):
            vals = property_trace(inst, prop, s, A_STEPS, agents_per_role, cfg, pay)
            collapsed += int(vals[0] == 1 and vals[-1] == 0)
        rate = collapsed / seeds
        numbers["collapse_rate"][_cfg_key(cfg)] = rate
        expect_collapse = "coordination" in cfg and pledges
        good = (rate >= SEED_RATE_MIN) if expect_collapse else (rate < SEED_RATE_MIN)
        ok &= good
        lines.append(f"  {_cfg_key(cfg)}: collapse within {A_STEPS} steps in {rate:.0%} of {seeds} seeds "
                     f"(expected {'collapse' if expect_collapse else 'persistence'}): {'ok' if good else 'NOT ok'}")
    return Criterion("a", PASS if ok else FAIL, f"collapse rates {numbers['collapse_rate']}; pledges={pledges}",
                     numbers=numbers, lines=lines)


# ------------------------------------------------------------------ (b) committed minority
def crit_b(by: dict, props: dict[str, Property], seeds: int, configs, not_run: dict[str, str],
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, steps: int = DEFAULT_STEPS, payoffs_of=None) -> Criterion:
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
    prop = props.get(B_PROP)
    if prop is None:
        return Criterion("b", FAIL, f"property {B_PROP!r} (ASSUMED name) not in properties.json: adoption undefined")
    pay = payoffs_of(NAMING) if payoffs_of else None
    numbers: dict = {"adoption_by_point": {}, "max_jump": {}}
    lines, ok = [], True
    for cfg in coord:
        adoption = []
        for v in B_SWEEP:
            finals = [property_trace(inst, prop, s, steps, agents_per_role, cfg, pay, {B_PARAM: v})[-1] for s in range(seeds)]
            adoption.append(sum(finals) / seeds)
        jumps = [b - a for a, b in zip(adoption, adoption[1:])]
        mj = max(jumps) if jumps else 0.0
        numbers["adoption_by_point"][_cfg_key(cfg)] = dict(zip(map(str, B_SWEEP), adoption))
        numbers["max_jump"][_cfg_key(cfg)] = mj
        good = mj > B_JUMP
        ok &= good
        lines.append(f"  {_cfg_key(cfg)}: adoption by {B_PARAM} {adoption}; max adjacent jump {mj:.2f} "
                     f"({'>' if good else '<='} {B_JUMP})")
    lines.append("  reviewer item (not mechanical): no constant in the code may set the tipping location; "
                 "Centola's band is recorded in the dataset, not asserted by the model")
    return Criterion("b", PASS if ok else FAIL, f"max adjacent jump {numbers['max_jump']}", numbers=numbers, lines=lines)


# ------------------------------------------------------------------ (c) kibbutz regendering
def crit_c(by: dict, props: dict[str, Property], seeds: int, configs, steps: int = DEFAULT_STEPS,
           agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, payoffs_of=None) -> Criterion:
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
    numbers: dict = {"property": PROP_C, "steps": steps, "seeds": seeds, "by_config": {}}
    lines, ok = [], True
    for cfg in configs:
        key = _cfg_key(cfg)
        entry: dict = {}
        for inst_id, pred, label in ((KIBBUTZ, rises_toward_one, "rises toward 1"), (KIBBUTZ_PAIR, stays_flat, "flat")):
            pay = payoffs_of(inst_id) if payoffs_of else None
            traces = [property_trace(by[inst_id], prop, s, steps, agents_per_role, cfg, pay) for s in range(seeds)]
            hits = [pred(tr) for tr in traces]
            rate = sum(hits) / seeds
            ew = [windows(tr) for tr in traces]
            entry[inst_id] = {"criterion": label, "rate": rate, "seeds_meeting": sum(hits),
                              "early_mean": sum(e for e, _ in ew) / seeds, "late_mean": sum(l for _, l in ew) / seeds,
                              "mean_trace": _mean_trace(traces),
                              "per_seed": [{"seed": s, "early": e, "late": l, "ok": h}
                                           for s, (e, l), h in zip(range(seeds), ew, hits)]}
            good = rate >= SEED_RATE_MIN
            ok &= good
            lines.append(f"  {key} {inst_id}: {PROP_C} {label} in {rate:.0%} of {seeds} seeds "
                         f"(early {entry[inst_id]['early_mean']:.2f} -> late {entry[inst_id]['late_mean']:.2f}; "
                         f"min {SEED_RATE_MIN:.0%}): {'ok' if good else 'NOT ok'}")
            mt = entry[inst_id]["mean_trace"]
            lines.append(f"    mean {PROP_C} per step (0..{steps}): " + " ".join(f"{v:.2f}" for v in mt))
        numbers["by_config"][key] = entry
    summary = "; ".join(f"{k}: {KIBBUTZ} rises {v[KIBBUTZ]['rate']:.0%}, {KIBBUTZ_PAIR} flat {v[KIBBUTZ_PAIR]['rate']:.0%}"
                        for k, v in numbers["by_config"].items())
    lines.append(f"  note: the dataset's initial state already satisfies {PROP_C} at t=0, so on {KIBBUTZ} the rise "
                 "clause is degenerate (read as persistence at 1); the pair is what separates the two")
    return Criterion("c", PASS if ok else FAIL, f"{summary} (min {SEED_RATE_MIN:.0%} of seeds; {len(configs)} "
                     f"configuration(s) run)", numbers=numbers, lines=lines)


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
        dis = disagreement(summaries)
        entry = {"rho": rho, "institutions": len(ids), "errors": errors,
                 "mean_total_half_a": dict(zip(ids, mean_a)), "mean_total_half_b": dict(zip(ids, mean_b)),
                 "ranking_half_a": rank_a, "ranking_half_b": rank_b, "disagreement_pairs": dis,
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
        for i in ids:
            lines.append(f"    {i}: total half A {mean_a[ids.index(i)]:.3f} (rank {rank_a.index(i) + 1}), "
                         f"half B {mean_b[ids.index(i)]:.3f} (rank {rank_b.index(i) + 1})")
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
        rows.append((c.key, c.status, c.detail if c.status != BLOCKED else f"blocked: {c.blocked_reason}"))
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
        if c.lines and (verbose or c.status != BLOCKED):
            out.append("")
            out.append(f"[{c.key}]")
            out.extend(c.lines if verbose else [l for l in c.lines if not l.startswith("    ")])
    return "\n".join(out)
