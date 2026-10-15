"""Mechanical, deterministic formula -> English. NOT a stage; a pure function.

The pipeline's faithfulness guarantee is: gloss templates (written once, per symbol, by the formalizer)
+ this fixed rendering. No LLM ever paraphrases a formula; the judge sees only this output.

Rules: (forall (x S) f) -> "For every S x: f"; exists -> "There is some S x such that f";
(=> A B) -> "if A then B"; (iff A B) -> "A if and only if B"; and/or plain; not -> "it is not the case that ...";
(= a b) -> "a is b"; constants render by gloss, bound variables by name. Compound operands are parenthesized
so scope is never ambiguous.
"""
from __future__ import annotations

import re

from . import sexpr as sx
from .models_ext import FormalizationX


class VerbalizeError(ValueError):
    pass


_SLOT = re.compile(r"\{(\d+)\}")
CONNECTIVE_WORDS = re.compile(r"\b(or|and|if|not)\b", re.I)


def _fill(gloss: str, args: list[str]) -> str:
    return _SLOT.sub(lambda m: args[int(m.group(1))], gloss)


def _gloss_errors(f: FormalizationX) -> list[str]:
    errs = [e for e in f.slot_errors() if "gloss" in e]
    for c in f.constants:
        if _SLOT.search(c.gloss):
            errs.append(f"constant {c.name}: gloss {c.gloss!r} must have no slots")
    return errs


def _atomic(a) -> bool:
    if isinstance(a, (sx.Sym, sx.App, sx.Eq)):
        return True
    return isinstance(a, sx.Not) and _atomic(a.arg)


def verbalize_formula(ast, f: FormalizationX) -> str:
    preds = {p.name: p for p in f.predicates}
    consts = {c.name: c for c in f.constants}

    def term(t, bound) -> str:
        if not isinstance(t, sx.Sym):
            raise VerbalizeError(f"unexpected term {t!r}")
        if t.name in bound:
            return t.name
        if t.name in consts:
            return consts[t.name].gloss
        raise VerbalizeError(f"unknown term {t.name!r}")

    def wrap(a, bound) -> str:
        s = go(a, bound)
        if isinstance(a, (sx.Sym, sx.App, sx.Eq)):  # atomic, but its gloss may itself contain a connective
            return f"({s})" if CONNECTIVE_WORDS.search(s) else s
        return s if _atomic(a) else f"({s})"

    def go(a, bound) -> str:
        if isinstance(a, sx.Sym):  # 0-ary predicate used as a proposition
            p = preds.get(a.name)
            if p is None or p.arg_sorts:
                raise VerbalizeError(f"{a.name!r} is not a 0-ary predicate")
            return p.gloss
        if isinstance(a, sx.App):
            p = preds.get(a.pred)
            if p is None:
                raise VerbalizeError(f"unknown predicate {a.pred!r}")
            if len(a.args) != len(p.arg_sorts):
                raise VerbalizeError(f"{a.pred}: applied to {len(a.args)} args, arity {len(p.arg_sorts)}")
            return _fill(p.gloss, [term(t, bound) for t in a.args])
        if isinstance(a, sx.Not):
            return "it is not the case that " + wrap(a.arg, bound)
        if isinstance(a, sx.And):
            return " and ".join(wrap(x, bound) for x in a.args)
        if isinstance(a, sx.Or):
            return " or ".join(wrap(x, bound) for x in a.args)
        if isinstance(a, sx.Implies):
            return f"if {wrap(a.left, bound)} then {wrap(a.right, bound)}"
        if isinstance(a, sx.Iff):
            return f"{wrap(a.left, bound)} if and only if {wrap(a.right, bound)}"
        if isinstance(a, sx.Eq):
            return f"{term(a.left, bound)} is {term(a.right, bound)}"
        if isinstance(a, sx.Quant):
            nb = bound | {v for v, _ in a.vars}
            body = go(a.body, nb)
            if a.kind == "forall":
                head = ", ".join(f"{s} {v}" for v, s in a.vars)
                return f"For every {head}: {body}"
            head = " and some ".join(f"{s} {v}" for v, s in a.vars)
            return f"There is some {head} such that {body}"
        raise VerbalizeError(f"not an AST node: {a!r}")

    return go(ast, frozenset())


def verbalize(f: FormalizationX) -> dict[str, str]:
    """{premise_id: english, ..., 'C': english}. Raises VerbalizeError on gloss/arity problems."""
    errs = _gloss_errors(f)
    if errs:
        raise VerbalizeError("; ".join(errs))
    out = {}
    for item in [*f.premises, f.conclusion]:
        label = "C" if item is f.conclusion else item.premise_id
        try:
            out[label] = verbalize_formula(sx.parse(item.sexpr), f)
        except sx.ParseError as e:
            raise VerbalizeError(f"{label}: {e}") from e
    return out


def symbol_legend(ast, f: FormalizationX) -> str:
    """`{name=sense, ...}` for the declared symbols a formula uses (order of first appearance); '' if none."""
    from .senses import symbols_in_order
    decl = {d.name: d for d in [*f.predicates, *f.constants]}
    names = symbols_in_order(ast, f)
    return "{" + ", ".join(f"{n}={decl[n].sense}" for n in names) + "}" if names else ""


def verbalization_text(f: FormalizationX, show_symbols: bool = False) -> str:
    """`[P1] ...` lines (premises in order, then `[C]`) exactly as judge.v1 expects. With show_symbols, each
    line gets `  {symbol=sense, ...}` appended (two spaces then `{`; consumers parsing `[P1] text` ignore it)."""
    v = verbalize(f)
    items = {("C" if it is f.conclusion else it.premise_id): it for it in [*f.premises, f.conclusion]}
    lines = []
    for k, text in v.items():
        leg = symbol_legend(sx.parse(items[k].sexpr), f) if show_symbols else ""
        lines.append(f"[{k}] {text}" + (f"  {leg}" if leg else ""))
    return "\n".join(lines)
