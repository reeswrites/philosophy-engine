"""Goods subjects (plans/priority-slice2.md revision 2, R2.1): the uninterpreted validity check a goods property's
`subject` must pass at load time.

  implication_shape(ast)                 the formula is (forall (...) (=> P Q)) (any number of leading foralls, or none)
  premise_implies_subject(formal, subj)  is Ant(t) -> Subj(t) valid with every fluent uninterpreted? (True / False /
                                         None = z3 unknown). Ant is rules_checks.antecedent: the implication premise,
                                         existentially closed over the stripped universal prefix. A formula without
                                         implication shape returns True (the check is skipped, R2.1).

Translation as computational-liberation scripts/goods_equiv.py: two sorts (agent, step), `t` a free step constant,
every fluent an uninterpreted predicate (named by name and arity), every other bare symbol an agent constant (a role).
"""
from __future__ import annotations

from . import sexpr as sx


def implication_shape(ast) -> bool:
    x = ast
    while isinstance(x, sx.Quant) and x.kind == "forall":
        x = x.body
    return isinstance(x, sx.Implies)


def _antecedent(ast):
    vs = []
    x = ast
    while isinstance(x, sx.Quant) and x.kind == "forall":
        vs.extend(x.vars)
        x = x.body
    if isinstance(x, sx.Implies):
        return sx.Quant("exists", tuple(vs), x.left) if vs else x.left
    return ast


def _translator():
    import z3
    agent, step = z3.DeclareSort("agent"), z3.DeclareSort("step")
    sorts = {"agent": agent, "step": step}
    fns: dict = {}

    def fl(name, args):
        key = (name, len(args))
        if key not in fns:
            fns[key] = z3.Function(name, *[a.sort() for a in args], z3.BoolSort())
        return fns[key](*args)

    def tr(e, env):
        if isinstance(e, sx.Sym):
            if e.name in env:
                return env[e.name]
            return z3.Const(e.name, agent)  # a role literal
        if isinstance(e, sx.Quant):
            vs = [z3.Const(n, sorts.get(srt, agent)) for n, srt in e.vars]
            env2 = dict(env)
            env2.update({n: v for (n, _), v in zip(e.vars, vs)})
            return (z3.ForAll if e.kind == "forall" else z3.Exists)(vs, tr(e.body, env2))
        if isinstance(e, sx.And):
            return z3.And(*[tr(x, env) for x in e.args])
        if isinstance(e, sx.Or):
            return z3.Or(*[tr(x, env) for x in e.args])
        if isinstance(e, sx.Not):
            return z3.Not(tr(e.arg, env))
        if isinstance(e, sx.Implies):
            return z3.Implies(tr(e.left, env), tr(e.right, env))
        if isinstance(e, (sx.Iff, sx.Eq)):
            return tr(e.left, env) == tr(e.right, env)
        if isinstance(e, sx.App):
            return fl(e.pred, [tr(x, env) for x in e.args])
        raise TypeError(type(e))

    return tr, z3.Const("t", step)


def premise_implies_subject(formal: str, subject: str) -> bool | None:
    import z3
    f = sx.parse(formal)
    if not implication_shape(f):
        return True
    tr, t = _translator()
    ant = tr(_antecedent(f), {"t": t})
    subj = tr(sx.parse(subject), {"t": t})
    s = z3.Solver()
    s.set("timeout", 10_000)
    s.add(z3.Not(z3.Implies(ant, subj)))
    r = s.check()
    return True if r == z3.unsat else False if r == z3.sat else None
