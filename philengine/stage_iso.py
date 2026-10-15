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


def _canon_id(arity: int, n: int) -> str:
    return f"{ARITY_PREFIX.get(arity, f'N{arity}_')}{n}"


def skeleton(argument_id: str, f) -> Skel | None:
    parsed, errs = fol.validate(f)
    if parsed is None:
        return None
    pdecl = {p.name: tuple(p.arg_sorts) for p in f.predicates}
    cdecl = {c.name: c.sort for c in f.constants}
    norm = {k: fol.normalize(a) for k, a in parsed.formulas.items()}
    erase = {n: f"U{len(s)}" for n, s in pdecl.items()} | {n: "c" for n in cdecl}
    prem_ids = sorted(parsed.premises, key=lambda k: fol.normalized_text(fol.rename(norm[k], erase)))
    occ: list[str] = []
    for k in [*prem_ids, "C"]:
        _occurrences(norm[k], frozenset(), occ)
    to_canon, counts, nc = {}, {}, 0
    for name in occ:
        if name in to_canon:
            continue
        if name in pdecl:
            ar = len(pdecl[name])
            counts[ar] = counts.get(ar, 0) + 1
            to_canon[name] = _canon_id(ar, counts[ar])
        elif name in cdecl:
            nc += 1
            to_canon[name] = f"c{nc}"
    texts = sorted(fol.normalized_text(fol.rename(norm[k], to_canon)) for k in prem_ids)
    canonical = "\n".join(texts) + "\n|-\n" + fol.normalized_text(fol.rename(norm["C"], to_canon))
    return Skel(argument_id, f, parsed, canonical, hashlib.sha256(canonical.encode()).hexdigest(), to_canon,
                {n: pdecl[n] for n in to_canon if n in pdecl}, {n: cdecl[n] for n in to_canon if n in cdecl}, norm)


def _signature(s: Skel):
    return (len(s.parsed.premises), tuple(sorted(len(v) for v in s.preds.values())), len(s.consts))


def _texts(norm_by_id: dict, mapping: dict):
    prem = sorted(fol.normalized_text(fol.rename(a, mapping)) for k, a in norm_by_id.items() if k != "C")
    return prem, fol.normalized_text(fol.rename(norm_by_id["C"], mapping))


def _candidate_mappings(a: Skel, b: Skel):
    """Yield A->B name mappings: canonical-label bijection first, then bounded permutations."""
    if len(a.preds) > config.ISO_MAX_PREDS or len(b.preds) > config.ISO_MAX_PREDS:
        return
    ga: dict = {}
    gb: dict = {}
    for n, s in a.preds.items():
        ga.setdefault(("p", s), []).append(n)
    for n, s in b.preds.items():
        gb.setdefault(("p", s), []).append(n)
    for n, s in a.consts.items():
        ga.setdefault(("c", s), []).append(n)
    for n, s in b.consts.items():
        gb.setdefault(("c", s), []).append(n)
    if {k: len(v) for k, v in ga.items()} != {k: len(v) for k, v in gb.items()}:
        return
    if math.prod(math.factorial(len(v)) for v in ga.values()) > config.ISO_MAX_PERMS:
        return
    if a.hash == b.hash:
        inv = {v: k for k, v in b.to_canon.items()}
        yield {n: inv[c] for n, c in a.to_canon.items() if c in inv}
    keys = sorted(ga, key=str)
    for combo in itertools.product(*[itertools.permutations(sorted(gb[k])) for k in keys]):
        m = {}
        for k, perm in zip(keys, combo):
            m.update(dict(zip(sorted(ga[k]), perm)))
        yield m


def find_mapping(a: Skel, b: Skel) -> dict | None:
    target = _texts(b.norm, {})
    for m in _candidate_mappings(a, b):
        if _texts(a.norm, m) == target:
            return m
    return None


def z3_confirm(a: Skel, b: Skel, mapping: dict, timeout_ms: int = config.Z3_TIMEOUT_MS) -> bool:
    """renamed_A <=> B valid for every matched premise pair and for the conclusion."""
    env = fol.build_env(b.f)
    ra = {k: fol.normalize(fol.rename(v, mapping)) for k, v in a.norm.items()}
    pool = {k: fol.normalized_text(v) for k, v in ra.items() if k != "C"}
    pairs = [("C", "C")]
    used = set()
    for kb, bast in b.parsed.premises.items():
        t = fol.normalized_text(bast)
        ka = next((k for k, v in pool.items() if v == t and k not in used), None)
        if ka is None:
            return False
        used.add(ka)
        pairs.append((ka, kb))
    for ka, kb in pairs:
        bast = b.parsed.conclusion if kb == "C" else b.parsed.premises[kb]
        try:
            fa, fb = fol.lower(ra[ka], env), fol.lower(bast, env)
        except Exception:
            return False
        s = z3.Solver()
        s.set("timeout", timeout_ms)
        s.set("random_seed", config.Z3_SEED)
        s.add(z3.Not(fa == fb))
        if s.check() != z3.unsat:
            return False
    return True


def match(a: Skel, b: Skel, timeout_ms: int = config.Z3_TIMEOUT_MS) -> dict | None:
    """-> evidence dict if a and b are confirmed isomorphic, else None."""
    same_hash = a.hash == b.hash
    if not same_hash and _signature(a) != _signature(b):
        return None
    m = find_mapping(a, b)
    if m is None or not z3_confirm(a, b, m, timeout_ms):
        return None
    return {"mapping": m, "hash": a.hash, "method": "hash" if same_hash else "permutation-fallback",
            "z3_verified": True}


def match_all(skels: list[Skel], timeout_ms: int = config.Z3_TIMEOUT_MS) -> list[tuple[Skel, Skel, dict]]:
    out = []
    for a, b in itertools.combinations(sorted(skels, key=lambda s: s.argument_id), 2):
        ev = match(a, b, timeout_ms)
        if ev:
            out.append((a, b, ev))
    return out


def selected_skeletons(store, argument_ids: list[str], options: dict | None = None) -> list[Skel]:
    ctx = Ctx(store, 0, None, options or {})
    out = []
    for aid in argument_ids:
        try:
            rec = pick_reconstruction(ctx, aid)
        except LookupError:
            continue
        sel = store.get_selection(rec.id)
        if not sel or sel.chosen_formalization_id is None:
            continue
        form = store.get_formalization(sel.chosen_formalization_id)
        if form.formalization is None:
            continue
        sk = skeleton(aid, form.formalization)
        if sk:
            out.append(sk)
    return out


@register("iso")
def iso(ctx: Ctx, unit: Unit) -> None:
    """Whole-corpus stage: run via pipeline with the single pseudo-argument '*' (argument_id is ignored)."""
    st = ctx.store
    st.execute("DELETE FROM relation WHERE run_id=? AND kind IN ('isomorphic-to','skeleton-hash')", (ctx.run_id,))
    skels = selected_skeletons(st, st.argument_ids(), ctx.options)
    for s in skels:
        st.insert_relation("argument", s.argument_id, "skeleton", s.hash, "skeleton-hash",
                           {"canonical": s.canonical}, ctx.run_id)
    for a, b, ev in match_all(skels, ctx.options.get("z3_timeout_ms") or config.Z3_TIMEOUT_MS):
        st.insert_relation("argument", a.argument_id, "argument", b.argument_id, "isomorphic-to", ev, ctx.run_id)


# ---- query helpers for reports
def iso_pairs(store, run_id: int | None = None) -> set[frozenset]:
    rels = store.relations("isomorphic-to", **({"run_id": run_id} if run_id is not None else {}))
    return {frozenset((r["src_id"], r["dst_id"])) for r in rels}


def skeleton_hashes(store, run_id: int | None = None) -> dict[str, str]:
    rels = store.relations("skeleton-hash", **({"run_id": run_id} if run_id is not None else {}))
    return {r["src_id"]: r["dst_id"] for r in rels}


def weak_truth(store) -> set[frozenset]:
    out = set()
    for aid in store.argument_ids():
        for b in store.get_argument(aid).get("weak_isomorphic_to", []):
            out.add(frozenset((aid, b)))
    return out


def same_hash_pairs(store, run_id: int | None = None) -> set[frozenset]:
    hs = skeleton_hashes(store, run_id)
    return {frozenset((a, b)) for a, b in itertools.combinations(sorted(hs), 2) if hs[a] == hs[b]}


def iso_eval(store, run_id: int | None = None) -> dict:
    """precision/recall of confirmed pairs vs iso_truth; false_friends = same-hash pairs that are not truth."""
    found, truth = iso_pairs(store, run_id), store.iso_truth()
    tp = found & truth
    return {"found": found, "truth": truth, "tp": tp, "fp": found - truth, "fn": truth - found,
            "precision": len(tp) / len(found) if found else None,
            "recall": len(tp) / len(truth) if truth else None,
            "false_friends": same_hash_pairs(store, run_id) - truth, "weak": weak_truth(store)}
