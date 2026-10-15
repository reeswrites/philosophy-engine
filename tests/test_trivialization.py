"""The trivialized fixtures MUST be rejected (nontrivial == False) by Z3-side signals alone.
(select-level filtering is added by builder step 3.)"""
import pytest

from philengine import checks

from .helpers import load

TRIVIAL = {
    "trivialized_a_same_as_premise": "syntactically equals P2",
    "trivialized_b_conjunct": "conjunct of P1",
    "trivialized_c_alpha_copy": "syntactically equals P1",
}


@pytest.mark.parametrize("name,frag", TRIVIAL.items())
def test_trivialized_rejected(name, frag):
    r = checks.run_all(load(name))
    assert r.parse_ok
    assert r.nontrivial is False, r
    assert any(frag in x for x in r.trivial_reasons), r.trivial_reasons
    # Z3 independently catches the same cases semantically (single-premise entailment)
    assert any("entailed by" in x for x in r.trivial_reasons), r.trivial_reasons


def test_trivialized_b_also_flags_redundancy():
    r = checks.run_all(load("trivialized_b_conjunct"))
    assert r.valid == "valid" and r.minimal is False and "P2" in r.redundant_premises


def test_good_formalization_not_flagged():
    assert checks.run_all(load("modus_ponens")).nontrivial is True
    assert checks.run_all(load("barbara")).nontrivial is True
