"""Stage: iso. Isomorphism matcher v0 over the SELECTED formalization of every argument.

skeleton   = normalize each formula, abstract predicates to canonical ids (arity-grouped, order of first
             occurrence over premises sorted by a name-erased key) and constants to c1..cn, hash it.
candidate  = equal skeleton hash (primary) or equal symbol signature (fallback; canonical ordering can be
             name-dependent when symmetric subterms tie).
confirm    = find a bijection of predicate/constant names (within arity+sort groups, <= ISO_MAX_PREDS preds)
             under which normalize(rename(A)) equals B formula-for-formula, then Z3: renamed_A <=> B valid
             for every matched premise pair and for the conclusion.
Stored as relation(kind='isomorphic-to', evidence={mapping, hash, method, z3_verified}) and, per argument,
relation(kind='skeleton-hash') so reports can list "false friends" (same hash, not confirmed / graded weak).
"""
from __future__ import annotations

import hashlib
import itertools
import math
from dataclasses import dataclass

import z3

from . import config, fol
from . import sexpr as sx
from .runner import Ctx, Unit, register
from .stage_common import pick_reconstruction

ARITY_PREFIX = {0: "A", 1: "U", 2: "B", 3: "T"}


@dataclass
class Skel:
    argument_id: str
    f: object            # FormalizationX
    parsed: object       # fol.Parsed
    canonical: str
    hash: str
    to_canon: dict       # original symbol -> canonical id
    preds: dict          # used pred name -> arg_sorts tuple
    consts: dict         # used const name -> sort
    norm: dict           # formula id ('C' too) -> normalized AST
    sorts: dict = None   # original sort name -> canonical sort id (S1.. by first occurrence)
    structured: bool = True  # has >= 1 quantifier or >= 1 predicate of arity >= 1 (else: all 0-ary atoms)
    unverified: bool = False  # built from the top-ranked parsed candidate of an `open` argument (nothing was selected)
    redundant: tuple = ()     # Z3 redundant_premises of the source candidate (round 3: dropped in the relaxed pass)
    abstractions: tuple = ()  # round 3: what the relaxed pass changed to build this skeleton ('' for strict skeletons)


def _occurrences(ast, bound, out):
    if isinstance(ast, sx.Sym):
        if ast.name not in bound:
            out.append(ast.name)
    elif isinstance(ast, sx.App):
        out.append(ast.pred)
        for t in ast.args:
            _occurrences(t, bound, out)
    elif isinstance(ast, sx.Not):
        _occurrences(ast.arg, bound, out)
    elif isinstance(ast, (sx.And, sx.Or)):
        for a in ast.args:
            _occurrences(a, bound, out)
    elif isinstance(ast, (sx.Implies, sx.Iff, sx.Eq)):
        _occurrences(ast.left, bound, out)
        _occurrences(ast.right, bound, out)
    elif isinstance(ast, sx.Quant):
        _occurrences(ast.body, bound | {v for v, _ in ast.vars}, out)


def _canon_id(arity: int, n: int, sorts: tuple = ()) -> str:
    base = f"{ARITY_PREFIX.get(arity, f'N{arity}_')}{n}"
    return base + ("_" + ".".join(sorts) if sorts else "")


def _has_quant(ast) -> bool:
    if isinstance(ast, sx.Quant):
        return True
    if isinstance(ast, sx.Not):
        return _has_quant(ast.arg)
    if isinstance(ast, (sx.And, sx.Or)):
        return any(_has_quant(a) for a in ast.args)
    if isinstance(ast, (sx.Implies, sx.Iff)):
        return _has_quant(ast.left) or _has_quant(ast.right)
    return False


def _nested_quant(ast) -> bool:
    """A quantifier whose body (at any depth) contains another quantifier."""
    if isinstance(ast, sx.Quant):
        return _has_quant(ast.body) or _nested_quant(ast.body)
    if isinstance(ast, sx.Not):
        return _nested_quant(ast.arg)
    if isinstance(ast, (sx.And, sx.Or)):
        return any(_nested_quant(a) for a in ast.args)
    if isinstance(ast, (sx.Implies, sx.Iff)):
        return _nested_quant(ast.left) or _nested_quant(ast.right)
    return False


def is_rich(s: "Skel") -> bool:
    """Structural-richness gate for a strong isomorphism claim: >= 3 premises, OR >= 2 distinct predicates of
    arity >= 1 together with a nested quantifier or a binary-or-higher predicate. Bare `forall x (A->B), A(c) |- B(c)`
    shapes fail it (they match every modus-ponens-over-a-universal and say little)."""
    if len(s.parsed.premises) >= 3:
        return True
    live = [v for v in s.preds.values() if len(v) >= 1]
    return len(live) >= 2 and (any(len(v) >= 2 for v in live) or any(_nested_quant(a) for a in s.norm.values()))


def _sort_occurrences(ast, pdecl, cdecl, bound, out):
    """Sorts in order of first mention: predicate argument sorts, constant sorts, quantified variable sorts."""
    if isinstance(ast, sx.Sym):
        if ast.name in cdecl and ast.name not in bound:
            out.append(cdecl[ast.name])
    elif isinstance(ast, sx.App):
        out.extend(pdecl.get(ast.pred, ()))
        for t in ast.args:
            _sort_occurrences(t, pdecl, cdecl, bound, out)
    elif isinstance(ast, sx.Not):
        _sort_occurrences(ast.arg, pdecl, cdecl, bound, out)
    elif isinstance(ast, (sx.And, sx.Or)):
        for a in ast.args:
            _sort_occurrences(a, pdecl, cdecl, bound, out)
    elif isinstance(ast, (sx.Implies, sx.Iff, sx.Eq)):
        _sort_occurrences(ast.left, pdecl, cdecl, bound, out)
        _sort_occurrences(ast.right, pdecl, cdecl, bound, out)
    elif isinstance(ast, sx.Quant):
        out.extend(s for _, s in ast.vars)
        _sort_occurrences(ast.body, pdecl, cdecl, bound | {v for v, _ in ast.vars}, out)


def skeleton(argument_id: str, f) -> Skel | None:
    parsed, errs = fol.validate(f)
    if parsed is None:
        return None
    pdecl = {p.name: tuple(p.arg_sorts) for p in f.predicates}
    cdecl = {c.name: c.sort for c in f.constants}
    norm = {k: fol.normalize(a) for k, a in parsed.formulas.items()}
    erase = {n: f"U{len(s)}" for n, s in pdecl.items()} | {n: "c" for n in cdecl}
    erase_sorts = {s.name: "S" for s in f.sorts}
    prem_ids = sorted(parsed.premises,
                      key=lambda k: fol.normalized_text(fol.rename(norm[k], erase, erase_sorts)))
    occ: list[str] = []
    sort_occ: list[str] = []
    for k in [*prem_ids, "C"]:
        _occurrences(norm[k], frozenset(), occ)
        _sort_occurrences(norm[k], pdecl, cdecl, frozenset(), sort_occ)
    sort_canon: dict = {}
    for sname in sort_occ:
        sort_canon.setdefault(sname, f"S{len(sort_canon) + 1}")
    to_canon, counts, nc = {}, {}, 0
    for name in occ:
        if name in to_canon:
            continue
        if name in pdecl:
            ar = len(pdecl[name])
            counts[ar] = counts.get(ar, 0) + 1
            to_canon[name] = _canon_id(ar, counts[ar], tuple(sort_canon[x] for x in pdecl[name]))
        elif name in cdecl:
            nc += 1
            to_canon[name] = f"c{nc}_{sort_canon[cdecl[name]]}"
    texts = sorted(fol.normalized_text(fol.rename(norm[k], to_canon, sort_canon)) for k in prem_ids)
    canonical = "\n".join(texts) + "\n|-\n" + fol.normalized_text(fol.rename(norm["C"], to_canon, sort_canon))
    preds = {n: pdecl[n] for n in to_canon if n in pdecl}
    structured = any(_has_quant(a) for a in norm.values()) or any(len(v) >= 1 for v in preds.values())
    return Skel(argument_id, f, parsed, canonical, hashlib.sha256(canonical.encode()).hexdigest(), to_canon,
                preds, {n: cdecl[n] for n in to_canon if n in cdecl}, norm, sort_canon, structured)


def _signature(s: Skel):
    return (len(s.parsed.premises), tuple(sorted(len(v) for v in s.preds.values())), len(s.consts),
            len(s.sorts or {}))


def _texts(norm_by_id: dict, mapping: dict, sorts: dict | None = None):
    prem = sorted(fol.normalized_text(fol.rename(a, mapping, sorts)) for k, a in norm_by_id.items() if k != "C")
    return prem, fol.normalized_text(fol.rename(norm_by_id["C"], mapping, sorts))


def _sort_sig(sorts: tuple) -> tuple:
    """Sort tuple canonicalized by first occurrence: (Person, Obj, Person) -> (0, 1, 0)."""
    seen: dict = {}
    return tuple(seen.setdefault(x, len(seen)) for x in sorts)


def _derive_sort_map(a: Skel, b: Skel, m: dict) -> dict | None:
    """Sort bijection A->B implied by the symbol mapping m; None if inconsistent."""
    sm: dict = {}
    inv: dict = {}
    pairs = [(a.preds[n], b.preds[m[n]]) for n in a.preds] + [((a.consts[n],), (b.consts[m[n]],)) for n in a.consts]
    for sa, sb in pairs:
        for x, y in zip(sa, sb):
            if sm.setdefault(x, y) != y or inv.setdefault(y, x) != x:
                return None
    for x in (a.sorts or {}):  # sorts only mentioned by quantifiers: map by canonical id if unambiguous
        if x not in sm:
            y = next((k for k, v in (b.sorts or {}).items() if v == a.sorts[x] and k not in inv), None)
            if y is not None:
                sm[x] = y
                inv[y] = x
    return sm


def _candidate_mappings(a: Skel, b: Skel, skips: list | None = None):
    """Yield A->B name mappings: canonical-label bijection first (always, whatever the caps), then bounded
    permutations. Cap hits are appended to `skips`."""
    if a.hash == b.hash:
        inv = {v: k for k, v in b.to_canon.items()}
        yield {n: inv[c] for n, c in a.to_canon.items() if c in inv}
    ga: dict = {}
    gb: dict = {}
    for n, s in a.preds.items():
        ga.setdefault(("p", _sort_sig(s)), []).append(n)
    for n, s in b.preds.items():
        gb.setdefault(("p", _sort_sig(s)), []).append(n)
    for n, s in a.consts.items():
        ga.setdefault(("c", 0), []).append(n)
    for n, s in b.consts.items():
        gb.setdefault(("c", 0), []).append(n)
    if {k: len(v) for k, v in ga.items()} != {k: len(v) for k, v in gb.items()}:
        return
    if len(a.preds) > config.ISO_MAX_PREDS or len(b.preds) > config.ISO_MAX_PREDS:
        if skips is not None:
            skips.append(f"permutation search skipped: more than ISO_MAX_PREDS={config.ISO_MAX_PREDS} predicates")
        return
    n_perms = math.prod(math.factorial(len(v)) for v in ga.values())
    if n_perms > config.ISO_MAX_PERMS:
        if skips is not None:
            skips.append(f"permutation search skipped: {n_perms} mappings > ISO_MAX_PERMS={config.ISO_MAX_PERMS}")
        return
    keys = sorted(ga, key=str)
    for combo in itertools.product(*[itertools.permutations(sorted(gb[k])) for k in keys]):
        m = {}
        for k, perm in zip(keys, combo):
            m.update(dict(zip(sorted(ga[k]), perm)))
        yield m


def find_mapping(a: Skel, b: Skel, skips: list | None = None) -> tuple[dict, dict] | None:
    """-> (symbol mapping, sort mapping) or None."""
    target = _texts(b.norm, {})
    for m in _candidate_mappings(a, b, skips):
        sm = _derive_sort_map(a, b, m)
        if sm is not None and _texts(a.norm, m, sm) == target:
            return m, sm
    return None


def z3_confirm(a: Skel, b: Skel, mapping: dict, timeout_ms: int = config.Z3_TIMEOUT_MS,
               sort_mapping: dict | None = None, log: list | None = None, flips: tuple = (),
               key=None) -> bool:
    """renamed_A <=> B valid for every matched premise pair and for the conclusion. Failures other than a
    plain mismatch (exception, z3 unknown) are appended to `log` (never swallowed silently).
    `flips` (round 3, relaxed pass): A's binary predicates whose argument order is swapped before renaming;
    `key` pairs premises by text (default fol.normalized_text; the relaxed pass uses binder_canonical_text)."""
    log = [] if log is None else log
    key = key or fol.normalized_text
    if sort_mapping is None:
        sort_mapping = _derive_sort_map(a, b, mapping) or {}
    env = fol.build_env(b.f)
    ra = {k: fol.normalize(fol.rename(_flip(v, set(flips)), mapping, sort_mapping)) for k, v in a.norm.items()}
    pool = {k: key(v) for k, v in ra.items() if k != "C"}
    pairs = [("C", "C")]
    used = set()
    for kb, bast in b.parsed.premises.items():
        t = key(bast)
        ka = next((k for k, v in pool.items() if v == t and k not in used), None)
        if ka is None:
            return False
        used.add(ka)
        pairs.append((ka, kb))
    for ka, kb in pairs:
        bast = b.parsed.conclusion if kb == "C" else b.parsed.premises[kb]
        try:
            fa, fb = fol.lower(ra[ka], env), fol.lower(bast, env)
            s = z3.Solver()
            s.set("timeout", timeout_ms)
            s.set("random_seed", config.Z3_SEED)
            s.add(z3.Not(fa == fb))
            r = s.check()
        except Exception as e:
            log.append(f"z3_confirm {ka}~{kb}: {type(e).__name__}: {e}")
            return False
        if r != z3.unsat:
            if r == z3.unknown:
                log.append(f"z3_confirm {ka}~{kb}: z3 unknown ({s.reason_unknown()})")
            return False
    return True


def match(a: Skel, b: Skel, timeout_ms: int = config.Z3_TIMEOUT_MS, notes: list | None = None) -> dict | None:
    """-> evidence dict if a and b are confirmed isomorphic, else None. Cap skips / z3 problems go to `notes`."""
    notes = [] if notes is None else notes
    same_hash = a.hash == b.hash
    if not same_hash and _signature(a) != _signature(b):
        return None
    found = find_mapping(a, b, notes)
    if found is None:
        return None
    m, sm = found
    if not z3_confirm(a, b, m, timeout_ms, sm, notes):
        return None
    return {"mapping": m, "sort_mapping": sm, "hash": a.hash,
            "method": "hash" if same_hash else "permutation-fallback", "z3_verified": True}


def match_all(skels: list[Skel], timeout_ms: int = config.Z3_TIMEOUT_MS,
              skipped: list | None = None, relaxed: bool = True) -> list[tuple[Skel, Skel, dict]]:
    """Strict pass over every pair, then (round 3) the relaxed pass over the pairs the strict pass did not match.
    `skipped` (optional) collects (a_id, b_id, reason) for cap skips and z3 problems."""
    out = []
    missed = []
    for a, b in itertools.combinations(sorted(skels, key=lambda s: s.argument_id), 2):
        notes: list = []
        ev = match(a, b, timeout_ms, notes)
        if ev:
            out.append((a, b, ev))
        else:
            missed.append((a, b))
        if skipped is not None:
            skipped.extend((a.argument_id, b.argument_id, n) for n in notes)
    if relaxed and missed:
        rel = {s.argument_id: relax_skeleton(s) for s in skels}
        for a, b in missed:
            ra, rb = rel[a.argument_id], rel[b.argument_id]
            if ra is None or rb is None:
                continue
            notes = []
            ev = match_relaxed(ra, rb, timeout_ms, notes)
            if ev:
                out.append((a, b, ev))
            if skipped is not None:
                skipped.extend((a.argument_id, b.argument_id, "relaxed: " + n) for n in notes)
    return out


# ---- round 3: relaxed (guard-abstracted) second pass -----------------------------------------------------------
# Why: the one strong human pair in the rees family (commitment-reauthoring ~ evaluator-drift) was missed with both
# sides formalized valid. Their skeletons differ only by formalizer choices that carry no logical content:
#   - an extra typing guard (`author_of a r`) repeated in P2/P3's antecedents on one side;
#   - explicit sorts (Agent/Rule) on one side vs unary guards + one sort on the other;
#   - the binder order of `forall ((r Obj) (a Obj))` vs `((l Obj) (r Obj))` (normalize alpha-renames by position);
#   - the argument order of one binary relation (`evaluator_of r l` vs `author_of a r`);
#   - (elsewhere) premises Z3 found redundant.
# The relaxed pass erases sorts, flattens curried implications, drops guard-only atoms from antecedents that keep a
# substantive conjunct, drops Z3-redundant premises, canonicalizes binder order, and tries binary argument flips in
# the mapping search. Matches are still Z3-confirmed (on the relaxed formulas) and stored with method='relaxed'.

def _flatten_curry(ast):
    """(=> A (=> B C)) -> (=> (and A B) C), recursively."""
    if isinstance(ast, sx.Implies):
        left, right = _flatten_curry(ast.left), _flatten_curry(ast.right)
        if isinstance(right, sx.Implies):
            lc = list(left.args) if isinstance(left, sx.And) else [left]
            rc = list(right.left.args) if isinstance(right.left, sx.And) else [right.left]
            return sx.Implies(sx.And(tuple(lc + rc)), right.right)
        return sx.Implies(left, right)
    if isinstance(ast, sx.Not):
        return sx.Not(_flatten_curry(ast.arg))
    if isinstance(ast, (sx.And, sx.Or)):
        return type(ast)(tuple(_flatten_curry(a) for a in ast.args))
    if isinstance(ast, sx.Iff):
        return sx.Iff(_flatten_curry(ast.left), _flatten_curry(ast.right))
    if isinstance(ast, sx.Quant):
        return sx.Quant(ast.kind, ast.vars, _flatten_curry(ast.body))
    return ast


def _positions(ast, pdecl: dict, out: dict, in_guard: bool = False) -> None:
    """out[pred] |= {'guard'|'body'}: 'guard' = a bare atom (or conjunct) in the antecedent of an implication."""
    if isinstance(ast, sx.Sym):
        if ast.name in pdecl:
            out.setdefault(ast.name, set()).add("guard" if in_guard else "body")
    elif isinstance(ast, sx.App):
        out.setdefault(ast.pred, set()).add("guard" if in_guard else "body")
    elif isinstance(ast, sx.Not):
        _positions(ast.arg, pdecl, out, False)
    elif isinstance(ast, sx.And):
        for a in ast.args:
            _positions(a, pdecl, out, in_guard)
    elif isinstance(ast, sx.Or):
        for a in ast.args:
            _positions(a, pdecl, out, False)
    elif isinstance(ast, sx.Implies):
        _positions(ast.left, pdecl, out, True)
        _positions(ast.right, pdecl, out, False)
    elif isinstance(ast, sx.Iff):
        _positions(ast.left, pdecl, out, False)
        _positions(ast.right, pdecl, out, False)
    elif isinstance(ast, sx.Quant):
        _positions(ast.body, pdecl, out, in_guard)


def guard_only_predicates(formulas: dict, pdecl: dict) -> set[str]:
    """Predicates of arity >= 1 that occur ONLY as antecedent atoms across all formulas (typing guards)."""
    pos: dict = {}
    for a in formulas.values():
        _positions(_flatten_curry(a), pdecl, pos)
    return {n for n, p in pos.items() if p == {"guard"} and len(pdecl.get(n, ())) >= 1}


def _drop_guards(ast, guards: set[str]) -> tuple:
    """Remove guard-only atoms from antecedent conjunctions that keep at least one other conjunct. -> (ast, dropped)."""
    dropped: list = []

    def is_guard(x):
        return isinstance(x, sx.App) and x.pred in guards

    def go(x):
        if isinstance(x, sx.Implies):
            left = x.left
            if isinstance(left, sx.And):
                keep = [c for c in left.args if not is_guard(c)]
                if keep and len(keep) < len(left.args):
                    dropped.extend(c.pred for c in left.args if is_guard(c))
                    left = keep[0] if len(keep) == 1 else sx.And(tuple(keep))
            return sx.Implies(go(left), go(x.right))
        if isinstance(x, sx.Not):
            return sx.Not(go(x.arg))
        if isinstance(x, (sx.And, sx.Or)):
            return type(x)(tuple(go(a) for a in x.args))
        if isinstance(x, sx.Iff):
            return sx.Iff(go(x.left), go(x.right))
        if isinstance(x, sx.Quant):
            return sx.Quant(x.kind, x.vars, go(x.body))
        return x

    return go(_flatten_curry(ast)), dropped


def relax(f, redundant=()) -> tuple[object | None, list[str]]:
    """Relaxed copy of a FormalizationX for the second iso pass -> (f', abstractions). None if nothing parses."""
    from .models_ext import ConstDeclX, FormalizationX, PredDeclX
    from .schemas import FormulaItem, SortDecl
    parsed, _ = fol.validate(f)
    if parsed is None:
        return None, []
    abstractions: list[str] = []
    sorts = {s.name for s in f.sorts}
    sort_map = {s: "Obj" for s in sorts}
    if len(sorts) > 1 or "Obj" not in sorts:
        abstractions.append("sorts-erased:" + ",".join(sorted(sorts)))
    pdecl = {p.name: tuple(p.arg_sorts) for p in f.predicates}
    formulas = dict(parsed.formulas)
    red = [p for p in redundant if p in parsed.premises and len(parsed.premises) > 1]
    for pid in red:
        formulas.pop(pid, None)
        abstractions.append(f"redundant-dropped:{pid}")
    guards = guard_only_predicates(formulas, pdecl)
    new: dict = {}
    dropped_all: list = []
    for k, a in formulas.items():
        a2, dropped = _drop_guards(a, guards)
        dropped_all.extend(dropped)
        new[k] = fol.rename(a2, {}, sort_map)
    for g in sorted(set(dropped_all)):
        abstractions.append(f"guard-dropped:{g}")
    used = set()
    for a in new.values():
        p, c = fol.symbols(a)
        used |= p | c
    preds = [PredDeclX(name=p.name, arg_sorts=["Obj"] * len(p.arg_sorts), gloss=p.gloss,
                       sense=getattr(p, "sense", "")) for p in f.predicates if p.name in used]
    consts = [ConstDeclX(name=c.name, sort="Obj", gloss=c.gloss, sense=getattr(c, "sense", ""))
              for c in f.constants if c.name in used]
    f2 = FormalizationX(sorts=[SortDecl(name="Obj")], predicates=preds, constants=consts,
                        premises=[FormulaItem(premise_id=k, sexpr=sx.to_sexpr(a)) for k, a in new.items() if k != "C"],
                        conclusion=FormulaItem(premise_id="C", sexpr=sx.to_sexpr(new["C"])), notes=f.notes)
    return f2, abstractions


def relax_skeleton(s: Skel) -> Skel | None:
    f2, abstractions = relax(s.f, s.redundant)
    if f2 is None:
        return None
    r = skeleton(s.argument_id, f2)
    if r is None:
        return None
    r.unverified = s.unverified
    r.abstractions = tuple(abstractions)
    return r


def _flip(ast, flips: set):
    """Swap the two arguments of every binary application whose predicate is in `flips`."""
    if not flips:
        return ast
    if isinstance(ast, sx.App):
        if ast.pred in flips and len(ast.args) == 2:
            return sx.App(ast.pred, (ast.args[1], ast.args[0]))
        return ast
    if isinstance(ast, sx.Not):
        return sx.Not(_flip(ast.arg, flips))
    if isinstance(ast, (sx.And, sx.Or)):
        return type(ast)(tuple(_flip(a, flips) for a in ast.args))
    if isinstance(ast, (sx.Implies, sx.Iff)):
        return type(ast)(_flip(ast.left, flips), _flip(ast.right, flips))
    if isinstance(ast, sx.Quant):
        return sx.Quant(ast.kind, ast.vars, _flip(ast.body, flips))
    return ast


def _binder_variants(ast):
    """Every reordering of each quantifier's binder list (blocks of <= 4 variables are permuted)."""
    if isinstance(ast, sx.Quant):
        perms = list(itertools.permutations(ast.vars)) if len(ast.vars) <= 4 else [ast.vars]
        for body in _binder_variants(ast.body):
            for vs in perms:
                yield sx.Quant(ast.kind, tuple(vs), body)
    elif isinstance(ast, sx.Not):
        for a in _binder_variants(ast.arg):
            yield sx.Not(a)
    elif isinstance(ast, (sx.And, sx.Or)):
        for args in itertools.product(*[list(_binder_variants(a)) for a in ast.args]):
            yield type(ast)(tuple(args))
    elif isinstance(ast, (sx.Implies, sx.Iff, sx.Eq)):
        for l in _binder_variants(ast.left):
            for r in _binder_variants(ast.right):
                yield type(ast)(l, r)
    else:
        yield ast


def binder_canonical_text(ast, cap: int = config.ISO_MAX_PERMS) -> str:
    """Normalized text minimized over binder orderings: `forall ((x S) (y S))` and `forall ((y S) (x S))` agree."""
    best = None
    for i, v in enumerate(_binder_variants(ast)):
        t = fol.normalized_text(v)
        if best is None or t < best:
            best = t
        if i >= cap:
            break
    return best if best is not None else fol.normalized_text(ast)


def _relaxed_texts(norm_by_id: dict, mapping: dict, flips: set):
    prem = sorted(binder_canonical_text(fol.rename(_flip(a, flips), mapping)) for k, a in norm_by_id.items() if k != "C")
    return prem, binder_canonical_text(fol.rename(_flip(norm_by_id["C"], flips), mapping))


def match_relaxed(a: Skel, b: Skel, timeout_ms: int = config.Z3_TIMEOUT_MS, notes: list | None = None) -> dict | None:
    """Second pass over RELAXED skeletons: predicate bijection x binary argument flips, compared under binder-canonical
    text, then Z3-confirmed on the relaxed formulas. Evidence carries method='relaxed' and the abstractions used."""
    notes = [] if notes is None else notes
    if _signature(a) != _signature(b):
        return None
    bin_a = sorted(n for n, s in a.preds.items() if len(s) == 2)
    if 2 ** len(bin_a) > config.ISO_MAX_PERMS:
        notes.append(f"relaxed flip search skipped: 2^{len(bin_a)} flip sets > ISO_MAX_PERMS")
        return None
    target = _relaxed_texts(b.norm, {}, set())
    flip_sets = [set(c) for k in range(len(bin_a) + 1) for c in itertools.combinations(bin_a, k)]
    for m in _candidate_mappings(a, b, notes):
        for flips in flip_sets:
            if _relaxed_texts(a.norm, m, flips) != target:
                continue
            if z3_confirm(a, b, m, timeout_ms, {}, notes, tuple(sorted(flips)), binder_canonical_text):
                return {"mapping": m, "sort_mapping": {}, "hash": a.hash, "method": "relaxed", "relaxed": True,
                        "z3_verified": True, "flips": sorted(flips),
                        "abstractions": {a.argument_id: list(a.abstractions), b.argument_id: list(b.abstractions)}}
    return None


def top_parsed_candidate(store, reconstruction_id: int):
    """For an `open` argument: the best parsed candidate whose Z3 verdict is valid/inconsistent, ranked by judge
    mean score (candidate_idx breaks ties). None if there is none."""
    from . import checks
    from .stage_common import latest_by_candidate
    cands = [f for f in latest_by_candidate(store.list_formalizations(reconstruction_id))
             if f.formalization is not None and f.check is not None and f.check.parse_ok
             and checks.verdict_of(f.check) in ("valid", "inconsistent")]
    cands.sort(key=lambda f: (-(f.judge.mean_score if f.judge else 0.0), f.candidate_idx))
    return cands[0] if cands else None


def selected_skeletons(store, argument_ids: list[str], options: dict | None = None,
                       skipped: list | None = None) -> list[Skel]:
    """Skeletons of selected formalizations whose selection verdict is "valid" (or "inconsistent") and that have real structure
    (a quantifier or a predicate of arity >= 1). For `open` arguments the top-ranked parsed candidate is used and the
    skeleton is flagged `unverified` (candidate not selected). Others are appended to `skipped` as (argument_id, reason)."""
    def skip(aid, why):
        if skipped is not None:
            skipped.append((aid, why))

    ctx = Ctx(store, 0, None, options or {})
    out = []
    for aid in argument_ids:
        try:
            rec = pick_reconstruction(ctx, aid)
        except LookupError:
            continue
        sel = store.get_selection(rec.id)
        unverified = False
        if sel and sel.verdict == "open":
            form = top_parsed_candidate(store, rec.id)
            if form is None:
                skip(aid, "open, and no parsed valid/inconsistent candidate")
                continue
            unverified = True
        elif not sel or sel.chosen_formalization_id is None:
            skip(aid, "no selected formalization")
            continue
        elif sel.verdict not in ("valid", "inconsistent"):
            skip(aid, f"selection verdict is {sel.verdict!r}, not 'valid' or 'inconsistent'")
            continue
        else:
            form = store.get_formalization(sel.chosen_formalization_id)
        if form.formalization is None:
            skip(aid, "selected formalization did not parse")
            continue
        sk = skeleton(aid, form.formalization)
        if sk is not None:
            sk.unverified = unverified
            sk.redundant = tuple(form.check.redundant_premises) if form.check else ()
        if sk is None:
            skip(aid, "skeleton failed validation")
        elif not sk.structured:
            skip(aid, "propositional skeleton (only 0-ary atoms, no quantifier): too weak to compare")
        else:
            out.append(sk)
    return out


@register("iso")
def iso(ctx: Ctx, unit: Unit) -> None:
    """Whole-corpus stage: run via pipeline with the single pseudo-argument '*' (argument_id is ignored)."""
    st = ctx.store
    st.execute("DELETE FROM relation WHERE run_id=? AND kind IN ('isomorphic-to','weak-isomorphic','skeleton-hash','iso-skipped')", (ctx.run_id,))
    skipped_args: list = []
    skels = selected_skeletons(st, st.argument_ids(), ctx.options, skipped_args)
    for aid, why in skipped_args:
        st.insert_relation("argument", aid, "skeleton", "-", "iso-skipped", {"reason": why}, ctx.run_id)
    for s in skels:
        st.insert_relation("argument", s.argument_id, "skeleton", s.hash, "skeleton-hash",
                           {"canonical": s.canonical, **({"unverified": True} if s.unverified else {})}, ctx.run_id)
    skipped_pairs: list = []
    matches = match_all(skels, ctx.options.get("z3_timeout_ms") or config.Z3_TIMEOUT_MS, skipped_pairs)
    for x, y, why in skipped_pairs:
        st.insert_relation("argument", x, "argument", y, "iso-skipped", {"reason": why}, ctx.run_id)
    for a, b, ev in matches:
        if a.unverified or b.unverified:
            ev = {**ev, "unverified": True, "unverified_args": sorted(s.argument_id for s in (a, b) if s.unverified)}
        if is_rich(a) and is_rich(b):
            st.insert_relation("argument", a.argument_id, "argument", b.argument_id, "isomorphic-to", ev, ctx.run_id)
        else:  # confirmed, but the shared shape is too bare to be evidence of a shared argument form
            st.insert_relation("argument", a.argument_id, "argument", b.argument_id, "weak-isomorphic",
                               {**ev, "rich": {a.argument_id: is_rich(a), b.argument_id: is_rich(b)}}, ctx.run_id)


# ---- query helpers for reports
def _rels(store, kind, run_id, unverified: bool | None, relaxed: bool | None = False):
    """Relations of `kind`; unverified=False -> selected-only, True -> unverified-only, None -> both; likewise
    `relaxed` (round 3 second-pass matches; default False = strict matches only)."""
    rels = store.relations(kind, **({"run_id": run_id} if run_id is not None else {}))
    out = []
    for r in rels:
        ev = r["evidence"] or {}
        if unverified is not None and bool(ev.get("unverified")) != unverified:
            continue
        if relaxed is not None and bool(ev.get("relaxed")) != relaxed:
            continue
        out.append(r)
    return out


def iso_pairs(store, run_id: int | None = None, unverified: bool | None = False,
              relaxed: bool | None = False) -> set[frozenset]:
    return {frozenset((r["src_id"], r["dst_id"])) for r in _rels(store, "isomorphic-to", run_id, unverified, relaxed)}


def skeleton_hashes(store, run_id: int | None = None, unverified: bool | None = False) -> dict[str, str]:
    return {r["src_id"]: r["dst_id"] for r in _rels(store, "skeleton-hash", run_id, unverified)}


def weak_truth(store) -> set[frozenset]:
    out = set()
    for aid in store.argument_ids():
        for b in store.get_argument(aid).get("weak_isomorphic_to", []):
            out.add(frozenset((aid, b)))
    return out


def same_hash_pairs(store, run_id: int | None = None) -> set[frozenset]:
    hs = skeleton_hashes(store, run_id)
    return {frozenset((a, b)) for a, b in itertools.combinations(sorted(hs), 2) if hs[a] == hs[b]}


def weak_iso_pairs(store, run_id: int | None = None, unverified: bool | None = False,
                   relaxed: bool | None = False) -> set[frozenset]:
    return {frozenset((r["src_id"], r["dst_id"])) for r in _rels(store, "weak-isomorphic", run_id, unverified, relaxed)}


def iso_eval(store, run_id: int | None = None) -> dict:
    """precision/recall of confirmed (rich) pairs vs iso_truth over SELECTED formalizations only; false_friends =
    same-hash pairs that are not truth. `weak_found` = confirmed but too bare (`weak-isomorphic`, "shape-only"): never
    FP when graded in the human `weak_isomorphic_to` list (`weak_correct`); not counted in precision/recall.
    `unverified*` = pairs involving an `open` argument's top-ranked candidate (candidate not selected); the *_all keys
    give a second precision/recall line that includes them, and (round 3) the relaxed-pass matches (`relaxed*`)."""
    found, truth = iso_pairs(store, run_id), store.iso_truth()
    wf, wt = weak_iso_pairs(store, run_id), weak_truth(store)
    tp = found & truth
    unv = iso_pairs(store, run_id, True, None)
    unv_weak = weak_iso_pairs(store, run_id, True, None)
    rel = iso_pairs(store, run_id, None, True)          # round 3: relaxed-pass matches (selected or unverified)
    rel_weak = weak_iso_pairs(store, run_id, None, True)
    found_all = found | unv | rel
    tp_all = found_all & truth
    return {"found": found, "truth": truth, "tp": tp, "fp": found - truth, "fn": truth - found,
            "precision": len(tp) / len(found) if found else None,
            "recall": len(tp) / len(truth) if truth else None,
            "false_friends": same_hash_pairs(store, run_id) - truth, "weak": wt,
            "weak_found": wf, "weak_correct": wf & wt, "weak_other": wf - wt,
            "unverified": unv, "unverified_tp": unv & truth, "unverified_fp": unv - truth,
            "unverified_weak": unv_weak, "unverified_weak_correct": unv_weak & wt,
            "relaxed": rel, "relaxed_tp": rel & truth, "relaxed_fp": rel - truth,
            "relaxed_weak": rel_weak, "relaxed_weak_correct": rel_weak & wt,
            "tp_all": tp_all, "fp_all": found_all - truth, "fn_all": truth - found_all,
            "precision_all": len(tp_all) / len(found_all) if found_all else None,
            "recall_all": len(tp_all) / len(truth) if truth else None}
