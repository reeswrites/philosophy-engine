"""Bounded checks over an InstitutionJSON (plan: "Checks" table).

  consistent         the unrolled system has a compliant trace at all ("inconsistent" otherwise)
  deontic_conflict   (must, must_not) rule pairs on the same action instance whose conditions can hold together
  reachable(P, k)    "reachable" + trace, or "open" (never "safe": beyond k nothing is known)
  invariant(P, k)    "holds_to_k", or "violated" + trace
  persists(P, k)     "persists", or "fails" + trace (P true at some t1, false at some t2 > t1)
  inert              (review finding 3) a must-be / must-not-be rule whose breach no compliant trace of the
                     other rules reaches within k: it constrains nothing. Reported in RuleCheckReport.inert /
                     rule_status, never an error; gate (a) fails on an inert rule marked load_bearing.
  vacuity            (review finding 6) invariant / persists results carry antecedent_reachable (the implication
                     premise of the property, after stripping leading foralls, is true at some step of some
                     compliant trace; the whole formula when it is not an implication) and subject_exists (some
                     `is_*` fluent holds at some step; None if the institution declares none); `vacuous` when
                     either is False.

Same solver discipline as checks.py: fresh solver, seed 0, per-check timeout, one retry at x3 with simplify.
z3 unknown -> "open" (fail closed). Verdict strings are exactly the plan's.

Public API:
  run_all(inst, properties, k=6, which=None, init=None, compliance="strict", step_mode="one", timeout_ms=...)
      -> RuleCheckReport   (init=None: "declared" when the institution has defaults/initial/initial_free, else "empty")
  check_for_expected(expected) -> which check an expected verdict names (reachable / invariant / persists)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import z3

from . import config
from . import sexpr as sx
from .rules_lower import DEFAULT_K, Grounded, LowerError, ground, lower_property, lower_state_formula, trace_of, validate_property
from .schemas_rules import InstitutionJSON, Property, PropertyResult, RuleCheckReport, RuleStatus

# dataset spelling "unreachable_open" is the plan's "open"
EXPECTED_ALIASES = {"unreachable_open": "open", "unreachable": "open"}
CHECK_OF_VERDICT = {
    "reachable": "reachable", "open": "reachable",
    "holds_to_k": "invariant", "violated": "invariant",
    "persists": "persists", "fails": "persists",
}


def normalize_expected(v: str) -> str:
    return EXPECTED_ALIASES.get(v, v)


def check_for_expected(expected: str) -> str | None:
    return CHECK_OF_VERDICT.get(normalize_expected(expected))


@dataclass
class _Res:
    result: str  # sat | unsat | unknown
    model: z3.ModelRef | None
    reason: str | None = None


def _check(exprs, timeout_ms: int = config.Z3_TIMEOUT_MS, retry_unknown: bool = True) -> _Res:
    def once(T, tactic):
        s = z3.Then("simplify", "smt").solver() if tactic else z3.Solver()
        s.set("timeout", T)
        s.set("random_seed", config.Z3_SEED)
        for e in exprs:
            s.add(e)
        return s, s.check()

    s, r = once(timeout_ms, False)
    if r == z3.unknown and retry_unknown:
        s, r = once(timeout_ms * config.Z3_RETRY_FACTOR, True)
    if r == z3.sat:
        return _Res("sat", s.model())
    if r == z3.unsat:
        return _Res("unsat", None)
    return _Res("unknown", None, s.reason_unknown())


# ------------------------------------------------------------------ checks
def check_consistent(G: Grounded, **kw) -> _Res:
    return _check([G.system()], **kw)


def check_deontic_conflict(G: Grounded, **kw) -> list[tuple[str, str]]:
    """(must id, must_not id) pairs on one grounded action instance whose conditions are jointly satisfiable
    in some single state (fluents free, no frame, no init)."""
    out: list[tuple[str, str]] = []
    musts = [ri for ri in G.rule_instances if ri.rule.deontic == "must"]
    nots = [ri for ri in G.rule_instances if ri.rule.deontic == "must_not"]
    for a in musts:
        for b in nots:
            if (a.action, a.args) != (b.action, b.args) or (a.rule.id, b.rule.id) in out:
                continue
            cs = [e for _, e in G.derived_defs if _.endswith("@0")]  # derived fluents keep their definitions
            for ri in (a, b):
                if ri.cond is not None:
                    cs.append(lower_state_formula(ri.cond, G, 0, ri.binding))
            if _check(cs, **kw).result != "unsat":
                out.append((a.rule.id, b.rule.id))
    return out


def _prop_at(ast, G: Grounded):
    return lambda t: lower_property(ast, G, t)


def check_reachable(G: Grounded, ast, **kw) -> PropertyResult:
    P = _prop_at(ast, G)
    r = _check([G.system(), z3.Or(*[P(t) for t in range(G.k + 1)])], **kw)
    if r.result == "sat":
        return PropertyResult(property="", check="reachable", verdict="reachable", trace=trace_of(r.model, G, P))
    return PropertyResult(property="", check="reachable", verdict="open",
                          reason=r.reason or f"no compliant trace reaches it within k={G.k} (not 'safe': unbounded behaviour unknown)")


def check_invariant(G: Grounded, ast, **kw) -> PropertyResult:
    P = _prop_at(ast, G)
    r = _check([G.system(), z3.Or(*[z3.Not(P(t)) for t in range(G.k + 1)])], **kw)
    if r.result == "sat":
        return PropertyResult(property="", check="invariant", verdict="violated", trace=trace_of(r.model, G, P))
    if r.result == "unsat":
        return PropertyResult(property="", check="invariant", verdict="holds_to_k")
    return PropertyResult(property="", check="invariant", verdict="open", reason=r.reason)


def check_persists(G: Grounded, ast, **kw) -> PropertyResult:
    P = _prop_at(ast, G)
    bad = z3.Or(*[z3.And(P(t1), z3.Not(P(t2))) for t1 in range(G.k + 1) for t2 in range(t1 + 1, G.k + 1)])
    r = _check([G.system(), bad], **kw)
    if r.result == "sat":
        return PropertyResult(property="", check="persists", verdict="fails", trace=trace_of(r.model, G, P))
    if r.result == "unsat":
        return PropertyResult(property="", check="persists", verdict="persists")
    return PropertyResult(property="", check="persists", verdict="open", reason=r.reason)


CHECKS = {"reachable": check_reachable, "invariant": check_invariant, "persists": check_persists}


# ------------------------------------------------------------------ inert must-be rules
def check_inert(G: Grounded, **kw) -> list[RuleStatus]:
    """For every state rule (must F / must_not F when C): is C and not F (C and F) reachable at some step of a
    compliant trace of every *other* assertion (the rule's own hard constraints dropped)? If not, the rule is
    inert: no action and no exogenous (initial_free / free-at-0) fluent can break it within k."""
    out: list[RuleStatus] = []
    for r in G.inst.rules:
        insts = [ri for ri in G.rule_instances if ri.rule.id == r.id and ri.kind == "state"]
        if not insts or r.deontic == "may":
            continue
        own = {f"{r.id}@{t}" for t in range(G.k + 1)}
        rest = [e for n, e in G.assertions if n not in own]
        breaches = []
        for t in range(G.k + 1):
            for ri in insts:
                c = G.cond_at(ri, t)
                f = ri.aim_at(G, t)
                breaches.append(z3.And(c, z3.Not(f)) if r.deontic == "must" else z3.And(c, f))
        res = _check([*rest, z3.Or(*breaches)], **kw)
        if res.result == "unsat":
            out.append(RuleStatus(rule=r.id, kind="inert", load_bearing=r.load_bearing,
                                  detail=f"{r.deontic} {r.aim} when {r.conditions}: no compliant trace of the other rules "
                                         f"breaks it within k={G.k}"))
    return out


# ------------------------------------------------------------------ vacuity
def antecedent(ast):
    """The premise of a universal implication, existentially closed over the stripped quantifiers; the formula
    itself when it is not of that shape."""
    vs = []
    x = ast
    while isinstance(x, sx.Quant) and x.kind == "forall":
        vs.extend(x.vars)
        x = x.body
    if isinstance(x, sx.Implies):
        return sx.Quant("exists", tuple(vs), x.left) if vs else x.left
    return ast


SUBJECT_PREFIX = "is_"


def vacuity(G: Grounded, ast, **kw) -> tuple[bool | None, bool | None]:
    """(antecedent_reachable, subject_exists); None when z3 is unknown / no `is_*` fluent is declared."""
    ant = antecedent(ast)
    A = lambda t: lower_property(ant, G, t)
    r = _check([G.system(), z3.Or(*[A(t) for t in range(G.k + 1)])], **kw)
    ant_ok = True if r.result == "sat" else False if r.result == "unsat" else None
    subj = [f.name for f in G.inst.fluents if f.name.startswith(SUBJECT_PREFIX)]
    if not subj:
        return ant_ok, None
    atoms = [G.fluent(n, tup, t) for n in subj for tup in G.fluent_tuples[n] for t in range(G.k + 1)]
    r = _check([G.system(), z3.Or(*atoms) if atoms else z3.BoolVal(False)], **kw)
    return ant_ok, (True if r.result == "sat" else False if r.result == "unsat" else None)


# ------------------------------------------------------------------ run_all
def run_all(
    inst: InstitutionJSON,
    properties: dict[str, Property],
    k: int = 6,
    which: dict[str, list[str]] | None = None,
    init: str | None = None,
    compliance: str = "strict",
    step_mode: str = "one",
    timeout_ms: int = config.Z3_TIMEOUT_MS,
    retry_unknown: bool = True,
) -> RuleCheckReport:
    """which: {property name: [check kinds]}. Default: the check named by each expected verdict in
    inst.expected_properties; a property without an expectation gets all three checks."""
    t0 = time.monotonic()
    ver = z3.get_version_string()
    kw = dict(timeout_ms=timeout_ms, retry_unknown=retry_unknown)
    rep = RuleCheckReport(institution=inst.id, bound_k=k, consistent="unknown", z3_version=ver,
                          init=init or "?", compliance=compliance, step_mode=step_mode)
    try:
        G = ground(inst, k=k, init=init, compliance=compliance, step_mode=step_mode)
    except (LowerError, sx.ParseError) as e:
        rep.warnings.append(f"lowering failed: {e}")
        rep.z3_ms = int((time.monotonic() - t0) * 1000)
        return rep
    rep.init = G.init
    rep.warnings.extend(G.warnings)
    cons = check_consistent(G, **kw)
    rep.consistent = cons.result
    rep.conflicts = check_deontic_conflict(G, **kw)
    if cons.result == "sat":
        rep.rule_status = check_inert(G, **kw)
        rep.inert = [st.rule for st in rep.rule_status if st.kind == "inert"]
    if which is None:
        which = {}
        for name, exp in inst.expected_properties.items():
            c = check_for_expected(exp)
            which[name] = [c] if c else list(CHECKS)
    for name, kinds in which.items():
        p = properties.get(name)
        if p is None:
            rep.results.append(PropertyResult(property=name, check="reachable", verdict="error", reason="unknown property"))
            continue
        errs, warns = validate_property(p, inst)
        rep.warnings.extend(warns)
        if errs:
            for kind in kinds:
                rep.results.append(PropertyResult(property=name, check=kind, verdict="error", reason="; ".join(errs)))
            continue
        ast = sx.parse(p.formal)
        for kind in kinds:
            t1 = time.monotonic()
            if cons.result == "unsat":
                res = PropertyResult(property=name, check=kind, verdict="inconsistent", reason="rules have no compliant trace")
            elif cons.result == "unknown":
                res = PropertyResult(property=name, check=kind, verdict="open", reason=f"consistency unknown: {cons.reason}")
            else:
                try:
                    res = CHECKS[kind](G, ast, **kw)
                    if kind in ("invariant", "persists"):
                        res.antecedent_reachable, res.subject_exists = vacuity(G, ast, **kw)
                        res.vacuous = res.antecedent_reachable is False or res.subject_exists is False
                except LowerError as e:
                    res = PropertyResult(property=name, check=kind, verdict="error", reason=str(e))
            res.property = name
            res.z3_ms = int((time.monotonic() - t1) * 1000)
            rep.results.append(res)
    rep.z3_ms = int((time.monotonic() - t0) * 1000)
    return rep
