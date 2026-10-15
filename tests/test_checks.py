import pytest

from philengine import checks
from philengine.schemas import CheckReport

from .helpers import load


def run(name, ids=None, **kw):
    return checks.run_all(load(name), ids, **kw)


def test_modus_ponens():
    r = run("modus_ponens", ["P1", "P2"])
    assert r.parse_ok and r.consistent == "sat" and r.valid == "valid"
    assert r.minimal is True and r.redundant_premises == []
    assert r.nontrivial is True and r.trivial_reasons == [] and not r.vacuous
    assert sorted(r.unsat_core) == ["P1", "P2"]
    assert checks.verdict_of(r) == "valid"
    assert r.z3_version and r.countermodel_text is None


def test_barbara_with_constant():
    r = run("barbara")
    assert r.valid == "valid" and r.minimal and r.nontrivial


def test_affirming_consequent_readable_countermodel():
    r = run("affirming_consequent")
    assert r.valid == "refuted" and checks.verdict_of(r) == "refuted"
    t = r.countermodel_text
    assert "rains" in t and "wet" in t and "it rains" in t
    assert "P1 is true" in t and "P2 is true" in t and "C is false" in t
    assert r.minimal is None


def test_affirming_consequent_fol_countermodel():
    r = run("affirming_consequent_fol")
    assert r.valid == "refuted"
    t = r.countermodel_text
    print(t)
    assert "socrates = obj0" in t or "socrates = obj" in t
    assert "mortal (is mortal): true for" in t and "man (is a man): true for nothing" in t
    assert "C is false" in t and "P1 is true" in t


def test_inconsistent_premises_vacuous():
    r = run("inconsistent")
    assert r.consistent == "unsat" and r.vacuous is True
    assert r.nontrivial is False
    assert any("inconsistent" in x for x in r.trivial_reasons)
    assert set(r.unsat_core) == {"P1", "P2"}


def test_redundant_premise():
    r = run("redundant_premise")
    assert r.valid == "valid" and r.redundant_premises == ["P3"] and r.minimal is False
    assert "P3" not in r.unsat_core


def test_tautological_conclusion():
    r = run("tautological_conclusion")
    assert r.nontrivial is False and r.vacuous is True
    assert any("tautology" in x for x in r.trivial_reasons)


def test_timeout_gives_unknown_and_open():
    # needs an infinite model: z3 cannot decide quickly
    r = run("infinite_only", timeout_ms=1, retry_unknown=False)
    assert r.valid == "unknown" and checks.verdict_of(r) == "open"
    assert r.unknown_reason
    assert r.countermodel_text is None


def test_parse_failure_reported():
    f = load("modus_ponens")
    f.premises[0].sexpr = "(=> rains (ite wet wet wet))"
    r = checks.run_all(f)
    assert not r.parse_ok and r.valid == "unknown" and r.parse_errors
    assert checks.verdict_of(r) == "open"


def test_orphan_conclusion_predicate():
    r = run("orphan_conclusion_predicate")
    assert r.nontrivial is False
    assert any("orphan" in x and "conclusion_holds" in x for x in r.trivial_reasons)


def test_report_is_schema_valid_json():
    r = run("modus_ponens")
    assert CheckReport.model_validate_json(r.model_dump_json()) == r
