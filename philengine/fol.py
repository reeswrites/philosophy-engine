"""Formalization JSON -> validated AST -> z3 terms; plus rename/normalize helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import z3

from . import sexpr as sx
from .schemas import FormalizationJSON

PRED_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
# ids that collide with the solver's internal assertion names (see checks.py); premise ids may not use them
TRACKER_PREFIX = "__trk_"
RESERVED_IDS = frozenset({"C", "NEG_C", "NEG_P"})


def reserved_id(pid: str) -> bool:
    return pid in RESERVED_IDS or pid.startswith(TRACKER_PREFIX)


@dataclass
class Parsed:
    """Validated formalization: ordered {premise_id: AST} plus conclusion AST."""
    formalization: FormalizationJSON
    premises: dict  # id -> AST (insertion order = premise order)
    conclusion: object  # AST for "C"
    errors: list = field(default_factory=list)

    @property
    def formulas(self) -> dict:
        d = dict(self.premises)
        d["C"] = self.conclusion
        return d


# ---------------------------------------------------------------- validation
def _check_decls(f: FormalizationJSON, errs: list[str]):
    sorts = {}
    for s in f.sorts:
        if not sx.IDENT.match(s.name) or s.name in sx.RESERVED:
            errs.append(f"invalid sort name {s.name!r}")
        if s.name in sorts:
            errs.append(f"duplicate sort {s.name!r}")
        sorts[s.name] = True
    preds = {}
    for p in f.predicates:
        if not PRED_NAME.match(p.name) or p.name in sx.RESERVED:
            errs.append(f"invalid predicate name {p.name!r} (must match [a-z][a-z0-9_]* and not be a reserved word)")
        if p.name in preds:
            errs.append(f"duplicate predicate {p.name!r}")
        for a in p.arg_sorts:
            if a not in sorts:
                errs.append(f"predicate {p.name!r}: undeclared sort {a!r}")
        if not p.gloss.strip():
            errs.append(f"predicate {p.name!r}: gloss is required")
        preds[p.name] = p
    consts = {}
    for c in f.constants:
        if not PRED_NAME.match(c.name) or c.name in sx.RESERVED:
            errs.append(f"invalid constant name {c.name!r} (must match [a-z][a-z0-9_]* and not be a reserved word)")
        if c.name in consts:
            errs.append(f"duplicate constant {c.name!r}")
        if c.name in preds:
            errs.append(f"name {c.name!r} declared as both predicate and constant")
        if c.sort not in sorts:
            errs.append(f"constant {c.name!r}: undeclared sort {c.sort!r}")
        consts[c.name] = c
    return sorts, preds, consts


def _check_formula(a, preds, consts, bound, sorts, errs, where):
    def term_sort(t, bound):
        n = t.name
        if n in bound:
            return bound[n]
        if n in consts:
            return consts[n].sort
        if n in preds:
            errs.append(f"{where}: predicate {n!r} used as a term")
        else:
            errs.append(f"{where}: undeclared symbol or free variable {n!r}")
        return None

    def go(x, bound):
        if isinstance(x, sx.Sym):
            p = preds.get(x.name)
            if p is None:
                errs.append(f"{where}: undeclared propositional symbol {x.name!r}")
            elif p.arg_sorts:
                errs.append(f"{where}: predicate {x.name!r} has arity {len(p.arg_sorts)} but is used with 0 arguments")
        elif isinstance(x, sx.App):
            p = preds.get(x.pred)
            if p is None:
                errs.append(f"{where}: undeclared predicate {x.pred!r}")
                for t in x.args:
                    term_sort(t, bound)
            else:
                if len(p.arg_sorts) != len(x.args):
                    errs.append(f"{where}: predicate {x.pred!r} has arity {len(p.arg_sorts)}, got {len(x.args)} argument(s)")
                for t, want in zip(x.args, p.arg_sorts):
                    got = term_sort(t, bound)
                    if got is not None and got != want:
                        errs.append(f"{where}: argument {t.name!r} of {x.pred!r} has sort {got}, expected {want}")
        elif isinstance(x, sx.Eq):
            a_, b_ = term_sort(x.left, bound), term_sort(x.right, bound)
            if a_ and b_ and a_ != b_:
                errs.append(f"{where}: equality between different sorts {a_} and {b_}")
        elif isinstance(x, sx.Not):
            go(x.arg, bound)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y, bound)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left, bound)
            go(x.right, bound)
        elif isinstance(x, sx.Quant):
            nb = dict(bound)
            for v, s in x.vars:
                if s not in sorts:
                    errs.append(f"{where}: undeclared sort {s!r} for variable {v!r}")
                if v in preds or v in consts:
                    errs.append(f"{where}: bound variable {v!r} shadows a declared predicate/constant")
                nb[v] = s
            go(x.body, nb)

    go(a, bound)


def validate(f: FormalizationJSON, reconstruction_ids: list[str] | None = None) -> tuple[Parsed | None, list[str]]:
    """Parse + validate. Returns (Parsed, []) or (None, errors). Errors are
    human-readable strings suitable for feeding back to the LLM for a retry."""
    errs: list[str] = []
    sorts, preds, consts = _check_decls(f, errs)
    ids = [p.premise_id for p in f.premises]
    if len(set(ids)) != len(ids):
        errs.append(f"duplicate premise ids in {ids}")
    if "C" in ids:
        errs.append("premise id 'C' is reserved for the conclusion")
    for i in ids:
        if i != "C" and reserved_id(i):
            errs.append(f"premise id {i!r} is reserved (internal solver name); use P1, P2, ...")
    if f.conclusion.premise_id != "C":
        errs.append(f"conclusion premise_id must be 'C', got {f.conclusion.premise_id!r}")
    if reconstruction_ids is not None and sorted(ids) != sorted(reconstruction_ids):
        errs.append(f"premise ids {ids} do not match reconstruction ids {list(reconstruction_ids)}")
    premises: dict = {}
    concl = None
    for item in [*f.premises, f.conclusion]:
        label = item.premise_id if item is not f.conclusion else "C"
        try:
            ast = sx.parse(item.sexpr)
        except sx.ParseError as e:
            errs.append(f"{label}: parse error: {e}")
            continue
        _check_formula(ast, preds, consts, {}, sorts, errs, label)
        if item is f.conclusion:
            concl = ast
        else:
            premises[label] = ast
    if errs:
        return None, errs
    return Parsed(f, premises, concl), []


# ------------------------------------------------------------------- lowering
@dataclass
class Env:
    sorts: dict
    preds: dict
    consts: dict


def build_env(f: FormalizationJSON) -> Env:
    sorts = {s.name: z3.DeclareSort(s.name) for s in f.sorts}
    preds = {
        p.name: (z3.Function(p.name, *[sorts[a] for a in p.arg_sorts], z3.BoolSort()) if p.arg_sorts else z3.Bool(p.name))
        for p in f.predicates
    }
    consts = {c.name: z3.Const(c.name, sorts[c.sort]) for c in f.constants}
    return Env(sorts, preds, consts)


def lower(ast, env: Env, bound: dict | None = None):
    """AST -> z3 expression. Assumes `validate` passed."""
    bound = bound or {}

    def term(t):
        return bound[t.name] if t.name in bound else env.consts[t.name]

    if isinstance(ast, sx.Sym):
        return env.preds[ast.name]
    if isinstance(ast, sx.App):
        return env.preds[ast.pred](*[term(t) for t in ast.args])
    if isinstance(ast, sx.Not):
        return z3.Not(lower(ast.arg, env, bound))
    if isinstance(ast, sx.And):
        xs = [lower(a, env, bound) for a in ast.args]
        return xs[0] if len(xs) == 1 else z3.And(*xs)
    if isinstance(ast, sx.Or):
        xs = [lower(a, env, bound) for a in ast.args]
        return xs[0] if len(xs) == 1 else z3.Or(*xs)
    if isinstance(ast, sx.Implies):
        return z3.Implies(lower(ast.left, env, bound), lower(ast.right, env, bound))
    if isinstance(ast, sx.Iff):
        return lower(ast.left, env, bound) == lower(ast.right, env, bound)
    if isinstance(ast, sx.Eq):
        return term(ast.left) == term(ast.right)
    if isinstance(ast, sx.Quant):
        nb = dict(bound)
        vs = []
        for v, s in ast.vars:
            c = z3.Const(v, env.sorts[s])
            nb[v] = c
            vs.append(c)
        body = lower(ast.body, env, nb)
        return z3.ForAll(vs, body) if ast.kind == "forall" else z3.Exists(vs, body)
    raise TypeError(f"not an AST node: {ast!r}")


# ------------------------------------------------------- rename / normalize
def rename(ast, mapping: dict, sorts: dict | None = None):
    """Rename predicates and constants (free symbols) via mapping; bound vars untouched.
    `sorts` (optional) renames the sorts of quantified variables. Names absent from a mapping are kept."""
    sorts = sorts or {}

    def go(x, bound):
        if isinstance(x, sx.Sym):
            if x.name in bound:
                return x
            return sx.Sym(mapping.get(x.name, x.name))
        if isinstance(x, sx.App):
            return sx.App(mapping.get(x.pred, x.pred), tuple(go(t, bound) for t in x.args))
        if isinstance(x, sx.Not):
            return sx.Not(go(x.arg, bound))
        if isinstance(x, sx.And):
            return sx.And(tuple(go(a, bound) for a in x.args))
        if isinstance(x, sx.Or):
            return sx.Or(tuple(go(a, bound) for a in x.args))
        if isinstance(x, sx.Implies):
            return sx.Implies(go(x.left, bound), go(x.right, bound))
        if isinstance(x, sx.Iff):
            return sx.Iff(go(x.left, bound), go(x.right, bound))
        if isinstance(x, sx.Eq):
            return sx.Eq(go(x.left, bound), go(x.right, bound))
        if isinstance(x, sx.Quant):
            return sx.Quant(x.kind, tuple((v, sorts.get(t, t)) for v, t in x.vars), go(x.body, bound | {v for v, _ in x.vars}))
        raise TypeError(x)

    return go(ast, frozenset())


def symbols(ast) -> tuple[set, set]:
    """(predicate names used, free constant names used)."""
    preds, consts = set(), set()

    def go(x, bound):
        if isinstance(x, sx.Sym):
            if x.name in bound:
                return
            consts.add(x.name)  # may be a propositional const; caller splits using decls
        elif isinstance(x, sx.App):
            preds.add(x.pred)
            for t in x.args:
                go(t, bound)
        elif isinstance(x, sx.Not):
            go(x.arg, bound)
        elif isinstance(x, (sx.And, sx.Or)):
            for a in x.args:
                go(a, bound)
        elif isinstance(x, (sx.Implies, sx.Iff, sx.Eq)):
            go(x.left, bound)
            go(x.right, bound)
        elif isinstance(x, sx.Quant):
            go(x.body, bound | {v for v, _ in x.vars})

    go(ast, frozenset())
    return preds, consts


def predicates_used(ast, f: FormalizationJSON) -> set:
    """All declared predicate names occurring in ast (including propositional constants)."""
    p, c = symbols(ast)
    declared = {d.name for d in f.predicates}
    return p | (c & declared)


def normalize(ast):
    """Normal form: =>/iff eliminated, negation pushed to atoms (NNF), and/or flattened,
    bound variables alpha-renamed by quantifier depth (v1, v2, ...), commutative children sorted."""

    def nnf(x, neg):
        if isinstance(x, (sx.Sym, sx.App, sx.Eq)):
            return sx.Not(x) if neg else x
        if isinstance(x, sx.Not):
            return nnf(x.arg, not neg)
        if isinstance(x, sx.And):
            ch = tuple(nnf(a, neg) for a in x.args)
            return sx.Or(ch) if neg else sx.And(ch)
        if isinstance(x, sx.Or):
            ch = tuple(nnf(a, neg) for a in x.args)
            return sx.And(ch) if neg else sx.Or(ch)
        if isinstance(x, sx.Implies):
            return nnf(sx.Or((sx.Not(x.left), x.right)), neg)
        if isinstance(x, sx.Iff):
            return nnf(sx.And((sx.Implies(x.left, x.right), sx.Implies(x.right, x.left))), neg)
        if isinstance(x, sx.Quant):
            kind = x.kind
            if neg:
                kind = "exists" if kind == "forall" else "forall"
            return sx.Quant(kind, x.vars, nnf(x.body, neg))
        raise TypeError(x)

    def flat(x, ty):
        out = []
        for a in x.args:
            a = canon(a)
            if isinstance(a, ty):
                out.extend(a.args)
            else:
                out.append(a)
        return out

    def canon(x):
        if isinstance(x, (sx.And, sx.Or)):
            ty = type(x)
            ch = sorted(set(flat(x, ty)), key=sx.to_sexpr)
            return ch[0] if len(ch) == 1 else ty(tuple(ch))
        if isinstance(x, sx.Not):
            return sx.Not(canon(x.arg))
        if isinstance(x, sx.Eq):
            a, b = sorted([x.left, x.right], key=sx.to_sexpr)
            return sx.Eq(a, b)
        if isinstance(x, sx.Quant):
            return sx.Quant(x.kind, x.vars, canon(x.body))
        return x

    def alpha(x, env, depth):
        if isinstance(x, sx.Sym):
            return sx.Sym(env.get(x.name, x.name))
        if isinstance(x, sx.App):
            return sx.App(x.pred, tuple(alpha(t, env, depth) for t in x.args))
        if isinstance(x, sx.Not):
            return sx.Not(alpha(x.arg, env, depth))
        if isinstance(x, (sx.And, sx.Or)):
            return type(x)(tuple(alpha(a, env, depth) for a in x.args))
        if isinstance(x, sx.Eq):
            return sx.Eq(alpha(x.left, env, depth), alpha(x.right, env, depth))
        if isinstance(x, sx.Quant):
            ne, vs = dict(env), []
            for i, (v, s) in enumerate(x.vars):
                nm = f"v{depth + 1}_{i + 1}"
                ne[v] = nm
                vs.append((nm, s))
            return sx.Quant(x.kind, tuple(vs), alpha(x.body, ne, depth + 1))
        raise TypeError(x)

    # alpha-rename first (so sorting sees canonical names), canonicalize, then sort again.
    return canon(alpha(canon(nnf(ast, False)), {}, 0))


def normalized_text(ast) -> str:
    return sx.to_sexpr(normalize(ast))


def conjuncts(ast) -> list:
    """Top-level conjuncts of the normalized formula (itself if not a conjunction)."""
    n = normalize(ast)
    return list(n.args) if isinstance(n, sx.And) else [n]
