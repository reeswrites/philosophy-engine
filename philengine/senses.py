"""Sense bookkeeping: mechanical guards against equivocation.

- gloss_collision_errors(f): two declared symbols, identical gloss text, different sense -> retry error.
- symbols_in_order(ast, f): declared symbols used by a formula, in order of first appearance (verbalize legend).
- mismatch_hints(f, reconstruction): SOFT heuristic. A premise uses symbol S, but its reconstruction text
  contains >= 2 content words of a competing sense (another declared symbol sharing a word with S but with a
  different sense, not itself used in that premise) and more of them than of S's own sense.
"""
from __future__ import annotations

import re

from . import sexpr as sx
from .models_ext import FormalizationX

STOP = frozenset("""a an the of in on at to is are was be been being it its that this these those and or not if then
for as by with from there some every any all no one has have had do does so such than which who what whether
about into onto""".split())


def norm_gloss(g: str) -> str:
    return re.sub(r"\s+", " ", g.strip().lower())


def content_words(*texts: str) -> set[str]:
    out = set()
    for t in texts:
        for w in re.findall(r"[a-z]+", re.sub(r"\{\d+\}", " ", t.lower().replace("_", " "))):
            if len(w) > 4 and w.endswith("s"):
                w = w[:-1]
            if len(w) > 1 and w not in STOP:
                out.add(w)
    return out


def _decls(f: FormalizationX):
    return [*f.predicates, *f.constants]


def gloss_collision_errors(f: FormalizationX) -> list[str]:
    errs, seen = [], {}
    for d in _decls(f):
        g = norm_gloss(d.gloss)
        o = seen.get(g)
        if o is not None and o.sense != d.sense:
            errs.append(f"sense_gloss_collision: {o.name} (sense {o.sense!r}) and {d.name} (sense {d.sense!r}) "
                        f"share the gloss {d.gloss!r}; two different senses must have different, specific glosses "
                        f"(e.g. \"{{0}} exists in reality\" vs \"{{0}} exists in the understanding\")")
        seen.setdefault(g, d)
    return errs


def symbols_in_order(ast, f: FormalizationX) -> list[str]:
    declared = {d.name for d in _decls(f)}
    out: list[str] = []

    def add(n):
        if n in declared and n not in out:
            out.append(n)

    def go(x):
        if isinstance(x, sx.Sym):
            add(x.name)
        elif isinstance(x, sx.App):
            add(x.pred)
            for t in x.args:
                go(t)
        elif isinstance(x, sx.Not):
            go(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for a in x.args:
                go(a)
        elif isinstance(x, (sx.Implies, sx.Iff, sx.Eq)):
            go(x.left)
            go(x.right)
        elif isinstance(x, sx.Quant):
            go(x.body)

    go(ast)
    return out


def mismatch_hints(f: FormalizationX, reconstruction) -> list[str]:
    """-> hint strings like `P1: uses exists_in_reality ... reads like exists_in_understanding`."""
    decl = {d.name: d for d in _decls(f)}
    words = {n: content_words(d.name, d.sense, d.gloss) for n, d in decl.items()}
    texts = {p.id: p.text for p in reconstruction.premises}
    hints = []
    for item in f.premises:
        text = texts.get(item.premise_id)
        if text is None:
            continue
        try:
            used = symbols_in_order(sx.parse(item.sexpr), f)
        except sx.ParseError:
            continue
        tw = content_words(text)
        for s in used:
            for t, d in decl.items():
                if t in used or d.sense == decl[s].sense or not (words[s] & words[t]):
                    continue
                theirs, own = len(words[t] & tw), len(words[s] & tw)
                if theirs >= 2 and theirs > own:
                    hints.append(f"{item.premise_id}: uses {s} (sense {decl[s].sense}) but the text reads like "
                                 f"{t} (sense {d.sense}): {sorted(words[t] & tw)}")
    return list(dict.fromkeys(hints))
