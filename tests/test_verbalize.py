import pytest

from philengine import sexpr as sx
from philengine.models_ext import FormalizationX
from philengine.verbalize import VerbalizeError, verbalization_text, verbalize, verbalize_formula


def fx(preds, consts, prem, concl, sorts=("Obj",)):
    return FormalizationX.model_validate({
        "sorts": [{"name": s} for s in sorts],
        "predicates": [{"name": n, "arg_sorts": ["Obj"] * a, "gloss": g, "sense": "t"} for n, a, g in preds],
        "constants": [{"name": n, "sort": "Obj", "gloss": g, "sense": "t"} for n, g in consts],
        "premises": [{"premise_id": f"P{i + 1}", "sexpr": s} for i, s in enumerate(prem)],
        "conclusion": {"premise_id": "C", "sexpr": concl}})


F = fx([("man", 1, "{0} is a man"), ("mortal", 1, "{0} is mortal"), ("causes", 2, "{0} causes {1}"),
        ("rains", 0, "it rains"), ("wet", 0, "the ground is wet")],
       [("socrates", "Socrates"), ("god", "God")],
       ["x"], "x")


def v(s):
    return verbalize_formula(sx.parse(s), F)


def test_forall_implies():
    assert v("(forall ((x Obj)) (=> (man x) (mortal x)))") == "For every Obj x: if x is a man then x is mortal"


def test_exists_and_constants():
    assert v("(exists ((y Obj)) (and (man y) (causes y socrates)))") == \
        "There is some Obj y such that y is a man and y causes Socrates"


def test_nested_quantifiers():
    s = "(forall ((x Obj)) (exists ((y Obj)) (causes y x)))"
    assert v(s) == "For every Obj x: There is some Obj y such that y causes x"
    s2 = "(exists ((x Obj)) (forall ((y Obj)) (not (causes y x))))"
    assert v(s2) == "There is some Obj x such that For every Obj y: it is not the case that y causes x"


def test_iff_not_or_propositional():
    assert v("(iff rains wet)") == "it rains if and only if the ground is wet"
    assert v("(not (or rains wet))") == "it is not the case that (it rains or the ground is wet)"
    assert v("(=> (and rains (not wet)) (man god))") == \
        "if (it rains and it is not the case that the ground is wet) then God is a man"


def test_equality_and_multivar():
    assert v("(forall ((x Obj) (y Obj)) (=> (causes x y) (not (= x y))))") == \
        "For every Obj x, Obj y: if x causes y then it is not the case that x is y"
    assert v("(exists ((x Obj) (y Obj)) (= x y))") == "There is some Obj x and some Obj y such that x is y"


def test_scope_is_parenthesised():
    assert v("(and (forall ((x Obj)) (man x)) rains)") == "(For every Obj x: x is a man) and it rains"


def test_verbalization_text_format_and_determinism():
    f = fx([("man", 1, "{0} is a man"), ("mortal", 1, "{0} is mortal")], [("socrates", "Socrates")],
           ["(forall ((x Obj)) (=> (man x) (mortal x)))", "(man socrates)"], "(mortal socrates)")
    t = verbalization_text(f)
    assert t == ("[P1] For every Obj x: if x is a man then x is mortal\n[P2] Socrates is a man\n"
                 "[C] Socrates is mortal")
    assert verbalize(f)["C"] == "Socrates is mortal" and verbalization_text(f) == t


def test_gloss_slot_mismatch_raises():
    bad = fx([("man", 1, "{0} is a man of {1}")], [("s", "S")], ["(man s)"], "(man s)")
    with pytest.raises(VerbalizeError, match="gloss"):
        verbalize(bad)
    bad2 = fx([("rains", 0, "it rains on {0}")], [], ["rains"], "rains")
    with pytest.raises(VerbalizeError):
        verbalize(bad2)
