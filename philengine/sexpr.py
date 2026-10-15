"""Restricted S-expression parser/printer for first-order formulas.

Grammar (no eval, no arithmetic, no ite/let/lambda):
  F := (forall ((x Sort) ...) F) | (exists ((x Sort) ...) F)
     | (=> F F) | (iff F F) | (and F+) | (or F+) | (not F)
     | (= t t) | (P t ...) | atom
  t := atom (variable or constant)
Parsed into the frozen dataclasses below. Name resolution/arity/sorts are
checked in fol.py, not here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
OPERATORS = {"forall", "exists", "=>", "iff", "and", "or", "not", "="}
# Rejected outright with a precise message (SMT-LIB things we deliberately do not support).
FORBIDDEN = {
    "ite", "let", "lambda", "+", "-", "*", "/", "<", ">", "<=", ">=", "distinct",
    "xor", "define-fun", "declare-fun", "declare-const", "assert", "true", "false",
    "implies", "mod", "div", "select", "store", "match", "!",
}
RESERVED = OPERATORS | FORBIDDEN


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Sym:
    """Atom: a variable, constant, or propositional constant (resolved in fol)."""
    name: str


@dataclass(frozen=True)
class App:
    pred: str
    args: tuple


@dataclass(frozen=True)
class Not:
    arg: object


@dataclass(frozen=True)
class And:
    args: tuple


@dataclass(frozen=True)
class Or:
    args: tuple


@dataclass(frozen=True)
class Implies:
    left: object
    right: object


@dataclass(frozen=True)
class Iff:
    left: object
    right: object


@dataclass(frozen=True)
class Eq:
    left: object
    right: object


@dataclass(frozen=True)
class Quant:
    kind: str  # "forall" | "exists"
    vars: tuple  # tuple[(name, sort)]
    body: object


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            toks.append(c)
            i += 1
        elif c == ";":  # comment to end of line
            while i < n and text[i] != "\n":
                i += 1
        elif c in "\"|#'`,":
            raise ParseError(f"illegal character {c!r} at offset {i}")
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "();":
                j += 1
            toks.append(text[i:j])
            i = j
    return toks


def read_sexpr(text: str):
    """Text -> nested lists of strings."""
    toks = tokenize(text)
    if not toks:
        raise ParseError("empty formula")
    pos = 0

    def read():
        nonlocal pos
        if pos >= len(toks):
            raise ParseError("unexpected end of input (missing ')')")
        t = toks[pos]
        pos += 1
        if t == "(":
            items = []
            while True:
                if pos >= len(toks):
                    raise ParseError("unexpected end of input (missing ')')")
                if toks[pos] == ")":
                    pos += 1
                    return items
                items.append(read())
        if t == ")":
            raise ParseError("unexpected ')'")
        return t

    tree = read()
    if pos != len(toks):
        raise ParseError(f"trailing input after formula: {toks[pos]!r}")
    return tree


def _atom(x, what: str) -> str:
    if not isinstance(x, str):
        raise ParseError(f"expected a symbol for {what}, got a list")
    if x in FORBIDDEN:
        raise ParseError(f"{x!r} is not allowed in this grammar")
    if x in OPERATORS or not IDENT.match(x):
        raise ParseError(f"invalid symbol {x!r} for {what}")
    return x


def _term(x):
    return Sym(_atom(x, "term"))


def _formula(x):
    if isinstance(x, str):
        return Sym(_atom(x, "propositional constant"))
    if not x:
        raise ParseError("empty list '()' is not a formula")
    head, rest = x[0], x[1:]
    if not isinstance(head, str):
        raise ParseError("operator/predicate position must be a symbol")
    if head in FORBIDDEN:
        raise ParseError(f"operator {head!r} is not allowed in this grammar")
    if head in ("forall", "exists"):
        if len(rest) != 2:
            raise ParseError(f"({head} ((x Sort) ...) body) takes exactly 2 arguments")
        binders = rest[0]
        if not isinstance(binders, list) or not binders:
            raise ParseError(f"{head}: binder list must be a non-empty list of (var Sort)")
        vs = []
        for b in binders:
            if not (isinstance(b, list) and len(b) == 2):
                raise ParseError(f"{head}: each binder must be (var Sort), got {b!r}")
            v, s = _atom(b[0], "bound variable"), _atom(b[1], "sort")
            vs.append((v, s))
        if len({v for v, _ in vs}) != len(vs):
            raise ParseError(f"{head}: duplicate bound variable")
        return Quant(head, tuple(vs), _formula(rest[1]))
    if head in ("=>", "iff", "="):
        if len(rest) != 2:
            raise ParseError(f"({head} a b) takes exactly 2 arguments, got {len(rest)}")
        if head == "=":
            return Eq(_term(rest[0]), _term(rest[1]))
        a, b = _formula(rest[0]), _formula(rest[1])
        return Implies(a, b) if head == "=>" else Iff(a, b)
    if head == "not":
        if len(rest) != 1:
            raise ParseError("(not a) takes exactly 1 argument")
        return Not(_formula(rest[0]))
    if head in ("and", "or"):
        if len(rest) < 1:
            raise ParseError(f"({head} ...) needs at least 1 argument")
        args = tuple(_formula(r) for r in rest)
        return And(args) if head == "and" else Or(args)
    # predicate application
    _atom(head, "predicate")
    if not rest:
        raise ParseError(f"({head}) has no arguments; write a propositional constant as bare `{head}`")
    return App(head, tuple(_term(r) for r in rest))


def parse(text: str):
    """Parse one formula string into the AST. Raises ParseError."""
    return _formula(read_sexpr(text))


def to_sexpr(a) -> str:
    """AST -> canonical S-expression text (inverse of parse)."""
    if isinstance(a, Sym):
        return a.name
    if isinstance(a, App):
        return "(" + " ".join([a.pred, *(to_sexpr(t) for t in a.args)]) + ")"
    if isinstance(a, Not):
        return f"(not {to_sexpr(a.arg)})"
    if isinstance(a, And):
        return "(and " + " ".join(to_sexpr(x) for x in a.args) + ")"
    if isinstance(a, Or):
        return "(or " + " ".join(to_sexpr(x) for x in a.args) + ")"
    if isinstance(a, Implies):
        return f"(=> {to_sexpr(a.left)} {to_sexpr(a.right)})"
    if isinstance(a, Iff):
        return f"(iff {to_sexpr(a.left)} {to_sexpr(a.right)})"
    if isinstance(a, Eq):
        return f"(= {to_sexpr(a.left)} {to_sexpr(a.right)})"
    if isinstance(a, Quant):
        bs = " ".join(f"({v} {s})" for v, s in a.vars)
        return f"({a.kind} ({bs}) {to_sexpr(a.body)})"
    raise TypeError(f"not an AST node: {a!r}")
