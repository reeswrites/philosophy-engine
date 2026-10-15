import pytest

from philengine import fol
from philengine import sexpr as sx
from philengine.schemas import FormalizationJSON

from .helpers import load


def f_with(sexprs, preds=("p:1", "q:1", "r:2"), consts=("a",), concl="(p a)"):
    return FormalizationJSON.model_validate({
        "predicates": [{"name": n.split(":")[0], "arg_sorts": ["Obj"] * int(n.split(":")[1]), "gloss": "g"} for n in preds],
        "constants": [{"name": c, "sort": "Obj", "gloss": c} for c in consts],
        "premises": [{"premise_id": f"P{i+1}", "sexpr": s} for i, s in enumerate(sexprs)],
        "conclusion": {"premise_id": "C", "sexpr": concl},
    })


@pytest.mark.parametrize("s", [
    "(forall ((x Obj)) (=> (p x) (q x)))",
    "(exists ((x Obj) (y Obj)) (and (r x y) (not (= x y))))",
    "(iff (p a) (or (q a) (p a)))",
    "rains",
])
def test_roundtrip(s):
    a = sx.parse(s)
    assert sx.parse(sx.to_sexpr(a)) == a


@pytest.mark.parametrize("s,frag", [
    ("(ite (p a) (q a) (p a))", "not allowed"),
    ("(+ a a)", "not allowed"),
    ("(let ((x a)) (p x))", "not allowed"),
    ("(and (p a)", "missing"),
    ("(p a))", "trailing"),
    ("(not (p a) (q a))", "exactly 1"),
    ("(forall (x) (p x))", "binder"),
    ("()", "not a formula"),
    ("(p)", "no arguments"),
])
def test_parse_rejects(s, frag):
    with pytest.raises(sx.ParseError, match=frag):
        sx.parse(s)


def test_no_eval_of_python():
    with pytest.raises(sx.ParseError):
        sx.parse("(p __import__('os'))")


@pytest.mark.parametrize("sexprs,frag", [
    (["(zzz a)"], "undeclared predicate"),
    (["(p a a)"], "arity"),
    (["(r a)"], "arity"),
    (["(p b)"], "undeclared symbol or free variable 'b'"),
    (["(forall ((x Obj)) (p y))"], "free variable 'y'"),
    (["(forall ((x Nope)) (p x))"], "undeclared sort"),
    (["(p p)"], "predicate 'p' used as a term"),
])
def test_validate_rejects(sexprs, frag):
    parsed, errs = fol.validate(f_with(sexprs))
    assert parsed is None
    assert any(frag in e for e in errs), errs


def test_validate_id_mismatch():
    parsed, errs = fol.validate(f_with(["(p a)"]), ["P1", "P2"])
    assert parsed is None and "do not match" in errs[0]


def test_validate_ok_and_lower():
    f = load("barbara")
    parsed, errs = fol.validate(f, ["P1", "P2"])
    assert not errs and list(parsed.formulas) == ["P1", "P2", "C"]
    env = fol.build_env(f)
    z = fol.lower(parsed.premises["P1"], env)
    assert "ForAll" in str(z)


def test_rename_keeps_bound_vars():
    a = sx.parse("(forall ((x Obj)) (=> (man x) (mortal socrates)))")
    r = fol.rename(a, {"man": "human", "mortal": "dies", "socrates": "s", "x": "ZZ"})
    assert sx.to_sexpr(r) == "(forall ((x Obj)) (=> (human x) (dies s)))"


def test_normalize_alpha_commutative_implication():
    n = fol.normalized_text
    assert n(sx.parse("(forall ((x Obj)) (p x))")) == n(sx.parse("(forall ((y Obj)) (p y))"))
    assert n(sx.parse("(and (p a) (q a))")) == n(sx.parse("(and (q a) (p a))"))
    assert n(sx.parse("(=> (p a) (q a))")) == n(sx.parse("(or (q a) (not (p a)))"))
    assert n(sx.parse("(not (and (p a) (q a)))")) == n(sx.parse("(or (not (q a)) (not (p a)))"))
    assert n(sx.parse("(and (p a) (and (q a) (p a)))")) == "(and (p a) (q a))"
    assert n(sx.parse("(not (forall ((x Obj)) (p x)))")) == "(exists ((v1_1 Obj)) (not (p v1_1)))"
    assert n(sx.parse("(p a)")) != n(sx.parse("(q a)"))
