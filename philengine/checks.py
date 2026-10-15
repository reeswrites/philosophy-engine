"""Z3 checks over a FormalizationJSON: consistency, entailment, minimality (unsat core),
non-triviality (incl. orphan conclusion predicate), countermodel text, timeouts -> open.

Public API:
  run_all(f, reconstruction_ids=None, timeout_ms=5000, retry_unknown=True) -> CheckReport
  verdict_of(report) -> "valid" | "refuted" | "open"
  countermodel_text(model, env, parsed) -> str
Lower-level: check_consistency, check_entailment, check_minimality, check_nontrivial.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import z3

from . import config, fol
from . import sexpr as sx
from .schemas import CheckReport, FormalizationJSON, Verdict

_PRE = fol.TRACKER_PREFIX


def verdict_of(r: CheckReport) -> Verdict:
    """valid->valid; refuted->refuted ("invalid as formalized", NOT "unsound"); unknown/parse fail->open."""
    if r.valid == "valid" and r.consistent == "unknown":
        return "open"  # cannot rule out vacuity -> fail closed
    return {"valid": "valid", "refuted": "refuted"}.get(r.valid, "open")


@dataclass
class _Res:
    result: str  # "sat" | "unsat" | "unknown"
    solver: z3.Solver
    core: list  # tracked names (ids) in unsat core
    reason: str | None = None


def _check(assertions, timeout_ms: int = config.Z3_TIMEOUT_MS, retry_unknown: bool = True) -> _Res:
    """assertions: [(name, z3 expr)]. Fresh solver, fixed seed, timeout; one retry at x3 on unknown."""

    def once(T, tactic):
        if tactic:
            s = z3.Then("simplify", "smt").solver()
        else:
            s = z3.Solver()
        s.set("timeout", T)
        s.set("random_seed", config.Z3_SEED)
        for name, e in assertions:
            s.assert_and_track(e, z3.Bool(_PRE + name))
        return s, s.check()

    s, r = once(timeout_ms, False)
    if r == z3.unknown and retry_unknown:
        s, r = once(timeout_ms * config.Z3_RETRY_FACTOR, True)
    res = "sat" if r == z3.sat else "unsat" if r == z3.unsat else "unknown"
    core = [str(c)[len(_PRE):] for c in s.unsat_core()] if res == "unsat" else []
    return _Res(res, s, core, s.reason_unknown() if res == "unknown" else None)


def _lower_all(parsed: fol.Parsed):
    env = fol.build_env(parsed.formalization)
    prem = {k: fol.lower(a, env) for k, a in parsed.premises.items()}
    return env, prem, fol.lower(parsed.conclusion, env)


# ------------------------------------------------------------- countermodel
def countermodel_text(m: z3.ModelRef, env: fol.Env, parsed: fol.Parsed) -> str:
    f = parsed.formalization
    names: dict[tuple, str] = {}

    def nm(sort_name, e) -> str:
        key = (sort_name, str(e))
        if key not in names:
            k = sum(1 for kk in names if kk[0] == sort_name)
            names[key] = f"{sort_name.lower()}{k}"
        return names[key]

    universe: dict[str, list] = {}
    for sname, srt in env.sorts.items():
        u = m.get_universe(srt)
        universe[sname] = list(u) if u else []
        for x in universe[sname]:
            nm(sname, x)
    lines = ["Countermodel: premises all true, conclusion false."]
    for c in f.constants:
        v = m.eval(env.consts[c.name], model_completion=True)
        if str(v) and v.sort().name() == c.sort and not universe[c.sort]:
            universe[c.sort].append(v)
        lines.append(f"  {c.name} = {nm(c.sort, v)}   ({c.gloss})")
    for sname in env.sorts:
        lines.insert(1, f"  {sname} domain: {{{', '.join(nm(sname, x) for x in universe[sname]) or '(unconstrained)'}}}")
    import itertools

    for p in f.predicates:
        if not p.arg_sorts:
            v = z3.is_true(m.eval(env.preds[p.name], model_completion=True))
            lines.append(f"  {p.name} = {str(v).lower()}   ({p.gloss})")
            continue
        doms = [universe[s] for s in p.arg_sorts]
        if any(not d for d in doms):
            lines.append(f"  {p.name} ({p.gloss}): no elements to evaluate")
            continue
        true_for = []
        for tup in itertools.product(*doms):
            if z3.is_true(m.eval(env.preds[p.name](*tup), model_completion=True)):
                true_for.append("(" + ", ".join(nm(s, t) for s, t in zip(p.arg_sorts, tup)) + ")")
        lines.append(f"  {p.name} ({p.gloss}): true for {', '.join(true_for) if true_for else 'nothing'}; false otherwise")
    for k, a in parsed.formulas.items():
        val = z3.is_true(m.eval(fol.lower(a, env), model_completion=True))
        lines.append(f"  {k} is {str(val).lower()}:  {sx.to_sexpr(a)}")
    return "\n".join(lines)


# ----------------------------------------------------------------- checks
def check_consistency(prem: dict, **kw) -> _Res:
    return _check(list(prem.items()), **kw)


def check_entailment(prem: dict, concl, **kw) -> _Res:
    return _check([*prem.items(), ("NEG_C", z3.Not(concl))], **kw)


def _unsat(assertions, probe: str, unknowns: list, **kw) -> bool | None:
    """True = unsat, False = sat, None = unknown (probe name appended to `unknowns`: fail closed)."""
    r = _check(assertions, **kw)
    if r.result == "unknown":
        unknowns.append(probe)
        return None
    return r.result == "unsat"


def check_minimality(prem: dict, concl, core: list, unknowns: list | None = None, **kw) -> list[str]:
    """Redundant premise ids (argument stays valid without them). Premises outside the core are
    redundant for free; core members are re-verified individually. A re-verification that returns
    unknown is neither redundant nor minimal: its probe name is appended to `unknowns`."""
    unknowns = [] if unknowns is None else unknowns
    redundant = [p for p in prem if p not in core]
    for p in core:
        rest = [(k, v) for k, v in prem.items() if k != p]
        if _unsat([*rest, ("NEG_C", z3.Not(concl))], f"minimality:{p}", unknowns, **kw):
            redundant.append(p)
    return [p for p in prem if p in redundant]


def check_nontrivial(parsed: fol.Parsed, env, prem: dict, concl, unknowns: list | None = None, **kw) -> list[str]:
    """Returns trivial_reasons (empty => nontrivial, unless `unknowns` got entries: then undecided).

    Bounded probes (O(#premises) solver calls each, no subset search):
      (a) syntactic: C equals a premise / is a conjunct of one (after normalize);
      (b) C entailed by one premise alone (only reported when there are >= 2 premises);
      (b') C logically EQUIVALENT to a single premise (both directions unsat), any premise count,
           which catches semantic duplicates such as (and p (or q (not q))) vs p;
      (b'') `conclusion_via_biconditional`: premise P_i is an iff with one side syntactically C
           and the remaining premises alone do not entail C (so P_i does the work of smuggling C in);
      (c) C or a premise is a tautology; orphan conclusion predicates.
    Does NOT catch: smuggling through other shapes (e.g. (=> d c) with d separately asserted, which is
    ordinary modus ponens), conclusions that need >= 2 premises jointly to be restated (no subset
    search), or biconditionals whose side is only semantically (not syntactically) C.
    Any probe returning unknown appends its name to `unknowns` and adds no reason."""
    unknowns = [] if unknowns is None else unknowns
    reasons: list[str] = []
    f = parsed.formalization
    nc = fol.normalized_text(parsed.conclusion)
    # (a) syntactic
    for pid, a in parsed.premises.items():
        if fol.normalized_text(a) == nc:
            reasons.append(f"C syntactically equals {pid} (up to renaming of bound variables / commutativity)")
        elif any(sx.to_sexpr(c) == nc for c in fol.conjuncts(a)):
            reasons.append(f"C is a conjunct of {pid}")
    # (b)/(b') single-premise entailment / equivalence
    for pid, e in prem.items():
        fwd = _unsat([(pid, e), ("NEG_C", z3.Not(concl))], f"nontrivial:entails-alone:{pid}", unknowns, **kw)
        if fwd and len(prem) >= 2:
            reasons.append(f"C entailed by {pid} alone")
        if fwd and _unsat([("C", concl), ("NEG_P", z3.Not(e))], f"nontrivial:equivalence:{pid}", unknowns, **kw):
            reasons.append(f"C is logically equivalent to {pid}")
    # (b'') conclusion smuggled through a biconditional premise
    for pid, a in parsed.premises.items():
        if isinstance(a, sx.Iff) and nc in (fol.normalized_text(a.left), fol.normalized_text(a.right)):
            rest = [(k, v) for k, v in prem.items() if k != pid]
            if _unsat([*rest, ("NEG_C", z3.Not(concl))], f"nontrivial:biconditional:{pid}", unknowns, **kw) is False:
                reasons.append(f"conclusion_via_biconditional: {pid} is an iff with C as one side and the other "
                               f"premises alone do not entail C")
    # (c) tautologies
    if _unsat([("NEG_C", z3.Not(concl))], "nontrivial:tautology:C", unknowns, **kw):
        reasons.append("C is a tautology (premises irrelevant)")
    for pid, e in prem.items():
        if _unsat([("NEG_P", z3.Not(e))], f"nontrivial:tautology:{pid}", unknowns, **kw):
            reasons.append(f"{pid} is a tautology (decorative premise)")
    # orphan conclusion predicates
    in_prem = set()
    for a in parsed.premises.values():
        in_prem |= fol.predicates_used(a, f)
    orphans = sorted(fol.predicates_used(parsed.conclusion, f) - in_prem)
    if orphans:
        reasons.append(f"orphan conclusion predicate(s) {orphans}: appear in C but in no premise")
    return list(dict.fromkeys(reasons))


# ---------------------------------------------------------------- run_all
def run_all(
    f: FormalizationJSON,
    reconstruction_ids: list[str] | None = None,
    timeout_ms: int = config.Z3_TIMEOUT_MS,
    retry_unknown: bool = True,
) -> CheckReport:
    t0 = time.monotonic()
    ver = z3.get_version_string()
    parsed, errs = fol.validate(f, reconstruction_ids)
    if parsed is None:
        return CheckReport(
            parse_ok=False, parse_errors=errs, consistent="unknown", valid="unknown",
            countermodel_text=None, minimal=None, nontrivial=None, vacuous=False,
            z3_ms=int((time.monotonic() - t0) * 1000), z3_version=ver,
        )
    kw = dict(timeout_ms=timeout_ms, retry_unknown=retry_unknown)
    env, prem, concl = _lower_all(parsed)

    cons = check_consistency(prem, **kw)
    ent = check_entailment(prem, concl, **kw)
    valid = {"unsat": "valid", "sat": "refuted"}.get(ent.result, "unknown")
    unknown_reason = ent.reason or cons.reason
    unknowns: list[str] = []
    if cons.result == "unknown":
        unknowns.append("consistency")
    if ent.result == "unknown":
        unknowns.append("entailment")

    cm = None
    if ent.result == "sat":
        cm = countermodel_text(ent.solver.model(), env, parsed)

    core = [c for c in ent.core if c != "NEG_C"] if ent.result == "unsat" else []
    if cons.result == "unsat":
        core = list(cons.core)

    minimal, redundant = None, []
    if ent.result == "unsat":
        n0 = len(unknowns)
        redundant = check_minimality(prem, concl, [c for c in ent.core if c != "NEG_C"], unknowns, **kw)
        minimal = None if len(unknowns) > n0 else not redundant

    n0 = len(unknowns)
    reasons = check_nontrivial(parsed, env, prem, concl, unknowns, **kw)
    nontrivial = False if reasons else (None if len(unknowns) > n0 else True)
    if cons.result == "unsat":
        reasons.insert(0, "premises inconsistent (argument vacuously valid)")
    tautological_c = any(r.startswith("C is a tautology") for r in reasons)
    return CheckReport(
        parse_ok=True,
        consistent=cons.result,
        valid=valid,
        countermodel_text=cm,
        unsat_core=core,
        minimal=minimal,
        redundant_premises=redundant,
        nontrivial=nontrivial,
        unknown_probes=unknowns,
        trivial_reasons=reasons,
        vacuous=cons.result == "unsat" or tautological_c,
        z3_ms=int((time.monotonic() - t0) * 1000),
        unknown_reason=unknown_reason,
        z3_version=ver,
    )
