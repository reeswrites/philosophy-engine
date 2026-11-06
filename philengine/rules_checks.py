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
from typing import TYPE_CHECKING

import z3

from . import config
from . import sexpr as sx
from .rules_lower import DEFAULT_K, Grounded, LowerError, ground, lower_property, lower_state_formula, resolve_init, trace_of, validate_property
from .schemas_rules import InstitutionJSON, Property, PropertyResult, QueryTiming, RuleCheckReport, RuleStatus

if TYPE_CHECKING:
    from .rules_cache import RuleCache

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


# Timing log: every _check appends one record; run_all drains it into RuleCheckReport.timing.
_LOG: list[dict] = []
_CTX = {"phase": "", "property": "", "check": "", "mark": time.perf_counter()}


def _begin(phase: str, property: str = "", check: str = "") -> None:
    """Label the z3 queries that follow; build time is measured from here (and from the end of each query)."""
    _CTX.update(phase=phase, property=property, check=check, mark=time.perf_counter())


def _drain() -> list[dict]:
    out = list(_LOG)
    _LOG.clear()
    return out


def _check(exprs, timeout_ms: int = config.Z3_TIMEOUT_MS, retry_unknown: bool = True) -> _Res:
    t_enter = time.perf_counter()
    acc = {"add": 0.0, "solve": 0.0}

    def once(T, tactic):
        s = z3.Then("simplify", "smt").solver() if tactic else z3.Solver()
        s.set("timeout", T)
        s.set("random_seed", config.Z3_SEED)
        t = time.perf_counter()
        for e in exprs:
            s.add(e)
        t2 = time.perf_counter()
        r = s.check()
        acc["add"] += t2 - t
        acc["solve"] += time.perf_counter() - t2
        return s, r

    s, r = once(timeout_ms, False)
    retries = 0
    if r == z3.unknown and retry_unknown:
        retries = 1
        s, r = once(timeout_ms * config.Z3_RETRY_FACTOR, True)
    t_exit = time.perf_counter()
    _LOG.append({"phase": _CTX["phase"], "property": _CTX["property"], "check": _CTX["check"],
                 "build_ms": round((t_enter - _CTX["mark"] + acc["add"]) * 1000, 3),
                 "solve_ms": round(acc["solve"] * 1000, 3),
                 "result": "sat" if r == z3.sat else "unsat" if r == z3.unsat else "unknown", "retries": retries})
    _CTX["mark"] = t_exit
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
    return PropertyResult(property="", check="reachable", verdict="open", z3_unknown=r.result == "unknown",
                          reason=r.reason or f"no compliant trace reaches it within k={G.k} (not 'safe': unbounded behaviour unknown)")


def check_invariant(G: Grounded, ast, **kw) -> PropertyResult:
    P = _prop_at(ast, G)
    r = _check([G.system(), z3.Or(*[z3.Not(P(t)) for t in range(G.k + 1)])], **kw)
    if r.result == "sat":
        return PropertyResult(property="", check="invariant", verdict="violated", trace=trace_of(r.model, G, P))
    if r.result == "unsat":
        return PropertyResult(property="", check="invariant", verdict="holds_to_k")
    return PropertyResult(property="", check="invariant", verdict="open", z3_unknown=True, reason=r.reason)


def check_persists(G: Grounded, ast, **kw) -> PropertyResult:
    P = _prop_at(ast, G)
    bad = z3.Or(*[z3.And(P(t1), z3.Not(P(t2))) for t1 in range(G.k + 1) for t2 in range(t1 + 1, G.k + 1)])
    r = _check([G.system(), bad], **kw)
    if r.result == "sat":
        return PropertyResult(property="", check="persists", verdict="fails", trace=trace_of(r.model, G, P))
    if r.result == "unsat":
        return PropertyResult(property="", check="persists", verdict="persists")
    return PropertyResult(property="", check="persists", verdict="open", z3_unknown=True, reason=r.reason)


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


# ------------------------------------------------------------------ goods states (revision 2, R2.1)
def goods_queries(G: Grounded, ast, subj_ast, **kw) -> tuple[str | None, str | None, dict[str, str]]:
    """(state, reason, queries) for one goods formula on G, decided in this order (plans/priority-slice2.md R2.1):
      1. subject   S = sat(system and OR_t Subj(t))          unsat: not_applicable   unknown: uncounted subject_unknown
      2. witness   W = sat(system and OR_t Wit(t))           unsat: uncounted no_witness_within_k   unknown: witness_unknown
      3. possible  P = sat(system and OR_t (Wit(t) and Good(t)))   unsat: absent      unknown: possible_unknown
      4. guaranteed: invariant of formal                     holds_to_k: stable   violated: fragile   else guaranteed_unknown
    Wit(t) = the implication premise (antecedent) when formal has implication shape, else Subj(t). An undecided query is
    never read as any state (state None, reason given)."""
    from .rules_goods import implication_shape
    Good = _prop_at(ast, G)
    Subj = _prop_at(subj_ast, G)
    Wit = _prop_at(antecedent(ast), G) if implication_shape(ast) else Subj
    ts = range(G.k + 1)
    q: dict[str, str] = {}
    r = _check([G.system(), z3.Or(*[Subj(t) for t in ts])], **kw)
    q["subject"] = r.result
    if r.result == "unsat":
        return "not_applicable", None, q
    if r.result != "sat":
        return None, "subject_unknown", q
    r = _check([G.system(), z3.Or(*[Wit(t) for t in ts])], **kw)
    q["witness"] = r.result
    if r.result == "unsat":
        return None, "no_witness_within_k", q
    if r.result != "sat":
        return None, "witness_unknown", q
    r = _check([G.system(), z3.Or(*[z3.And(Wit(t), Good(t)) for t in ts])], **kw)
    q["possible"] = r.result
    if r.result == "unsat":
        return "absent", None, q
    if r.result != "sat":
        return None, "possible_unknown", q
    inv = check_invariant(G, ast, **kw)
    q["guaranteed"] = inv.verdict if not inv.z3_unknown else "unknown"
    if inv.verdict == "holds_to_k":
        return "stable", None, q
    if inv.verdict == "violated":
        return "fragile", None, q
    return None, "guaranteed_unknown", q


# ------------------------------------------------------------------ run_all
def _has_unknown(log: list[dict]) -> bool:
    return any(e["result"] == "unknown" for e in log)


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
    cache: "RuleCache | None" = None,
) -> RuleCheckReport:
    """which: {property name: [check kinds]}. Default: the check named by each expected verdict in
    inst.expected_properties; a property without an expectation gets all three checks.
    cache: a rules_cache.RuleCache to read / write results (None = off, the default). A hit reproduces the stored
    PropertyResult exactly; results in which z3 answered `unknown` are never stored."""
    from . import rules_cache as rcache
    t0 = time.monotonic()
    ver = z3.get_version_string()
    kw = dict(timeout_ms=timeout_ms, retry_unknown=retry_unknown)
    rep = RuleCheckReport(institution=inst.id, bound_k=k, consistent="unknown", z3_version=ver,
                          init=init or "?", compliance=compliance, step_mode=step_mode)
    _drain()
    timing: list[dict] = []
    ckw = dict(k=k, step_mode=step_mode, compliance=compliance, timeout_ms=timeout_ms, retry_unknown=retry_unknown)
    try:
        init_req = resolve_init(inst, init)
    except LowerError:
        init_req, cache = init, None  # ground() below reports the error
    gcell: list = []

    def get_G() -> Grounded:
        if not gcell:
            tg = time.perf_counter()
            gcell.append(ground(inst, k=k, init=init, compliance=compliance, step_mode=step_mode))
            timing.append({"phase": "ground", "property": "", "check": "", "build_ms": round((time.perf_counter() - tg) * 1000, 3),
                           "solve_ms": 0.0, "result": "", "retries": 0})
        return gcell[0]

    def finish() -> RuleCheckReport:
        rep.z3_ms = int((time.monotonic() - t0) * 1000)
        rep.timing = [QueryTiming(institution=inst.id, k=k, step_mode=step_mode, init=rep.init, z3_version=ver, **e)
                      for e in timing]
        return rep

    ikey = rcache.make_key(inst, entry=rcache.INSTITUTION_KIND, init=init_req, **ckw) if cache else None
    hit = cache.get(ikey) if cache else None
    if hit is not None:
        rep.init = hit["init"]
        rep.warnings.extend(hit["warnings"])
        rep.consistent = hit["consistent"]
        rep.conflicts = [tuple(c) for c in hit["conflicts"]]
        rep.rule_status = [RuleStatus.model_validate(x) for x in hit["rule_status"]]
        rep.inert = [st.rule for st in rep.rule_status if st.kind == "inert"]
        timing.append({"phase": "cached", "property": "", "check": "institution", "build_ms": 0.0, "solve_ms": 0.0,
                       "result": rep.consistent, "retries": 0, "cached": True})
        cons = _Res(rep.consistent, None, "cached")
    else:
        try:
            G = get_G()
        except (LowerError, sx.ParseError) as e:
            rep.warnings.append(f"lowering failed: {e}")
            return finish()
        rep.init = G.init
        rep.warnings.extend(G.warnings)
        _begin("consistent")
        cons = check_consistent(G, **kw)
        rep.consistent = cons.result
        _begin("conflict")
        rep.conflicts = check_deontic_conflict(G, **kw)
        if cons.result == "sat":
            _begin("inert")
            rep.rule_status = check_inert(G, **kw)
            rep.inert = [st.rule for st in rep.rule_status if st.kind == "inert"]
        log = _drain()
        timing.extend(log)
        if cache and not _has_unknown(log):
            cache.put(ikey, rcache.INSTITUTION_KIND, {
                "init": rep.init, "warnings": list(G.warnings), "consistent": rep.consistent,
                "conflicts": [list(c) for c in rep.conflicts],
                "rule_status": [st.model_dump(mode="json") for st in rep.rule_status]})
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
            pkey = None
            if cons.result == "unsat":
                res = PropertyResult(property=name, check=kind, verdict="inconsistent", reason="rules have no compliant trace")
            elif cons.result == "unknown":
                res = PropertyResult(property=name, check=kind, verdict="open", z3_unknown=True, reason=f"consistency unknown: {cons.reason}")
            else:
                goods = p.kind == "goods" and kind == "persists" and bool(p.subject)
                ckey_formal = p.formal + (f"\n;subject {p.subject}" if goods else "")
                pkey = rcache.make_key(inst, entry=rcache.PROPERTY_KIND, formal=ckey_formal, check=kind, init=rep.init,
                                       **ckw) if cache else None
                cached = cache.get(pkey) if cache else None
                if cached is not None:
                    res = PropertyResult.model_validate(cached)
                    res.property = name  # the key is formal-text based: a twin property's stored row carries ITS name
                    timing.append({"phase": "cached", "property": name, "check": kind, "build_ms": 0.0, "solve_ms": 0.0,
                                   "result": res.verdict, "retries": 0, "cached": True})
                    rep.results.append(res)
                    continue
                try:
                    _begin("check", name, kind)
                    res = CHECKS[kind](get_G(), ast, **kw)
                    if goods:  # revision 2: goods read the four states from their own subject, not vacuity()
                        _begin("goods", name, kind)
                        res.goods_state, res.goods_reason, res.goods_queries = goods_queries(
                            get_G(), ast, sx.parse(p.subject), **kw)
                    elif kind in ("invariant", "persists"):
                        _begin("vacuity", name, kind)
                        res.antecedent_reachable, res.subject_exists = vacuity(get_G(), ast, **kw)
                        res.vacuous = res.antecedent_reachable is False or res.subject_exists is False
                except LowerError as e:
                    res = PropertyResult(property=name, check=kind, verdict="error", reason=str(e))
                log = _drain()
                timing.extend(log)
                res.property = name
                res.z3_ms = int((time.monotonic() - t1) * 1000)
                if pkey and res.verdict != "error" and not _has_unknown(log):
                    cache.put(pkey, rcache.PROPERTY_KIND, res.model_dump(mode="json"))
                rep.results.append(res)
                continue
            res.property = name
            res.z3_ms = int((time.monotonic() - t1) * 1000)
            rep.results.append(res)
    return finish()
