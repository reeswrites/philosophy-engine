"""Regression tests for the review-fix pass (one per fix)."""
import json
import sqlite3

import pytest

from philengine import checks, config, fol, stage_iso as iso, verbalize
from philengine.llm import MockLLMClient
from philengine.models_ext import FormalizationX, SelectionResultX
from philengine.schemas import CheckReport, FormalizationJSON
from philengine.stage_select import has_unknown_probe, score, select_for
from philengine.store import Store

from .test_select import run_cogito


def mk(preds, consts, prem, c, sorts=("S",), csort=None):
    return FormalizationX.model_validate(dict(
        sorts=[{"name": s} for s in sorts],
        predicates=[{"name": n, "arg_sorts": a, "gloss": "g {0}" if a else "g", "sense": "x"} for n, a in preds],
        constants=[{"name": n, "sort": csort or sorts[0], "gloss": "k", "sense": "x"} for n in consts],
        premises=[{"premise_id": f"P{i + 1}", "sexpr": s, "type": "empirical"} for i, s in enumerate(prem)],
        conclusion={"premise_id": "C", "sexpr": c, "type": "empirical"}))


def rep(f):
    return checks.run_all(f)


# 1 / 2
def test_conclusion_smuggled_via_biconditional():
    r = rep(mk([("c", []), ("d", [])], [], ["d", "(iff c d)"], "c"))
    assert r.valid == "valid" and r.nontrivial is True  # soft signal only
    assert r.suspect_biconditional == ["P2"]
    assert not any("biconditional" in t for t in r.trivial_reasons)


def test_single_premise_equivalent_to_conclusion_flagged():
    f = mk([("p", ["S"]), ("q", ["S"])], [], ["(forall ((x S)) (and (p x) (or (q x) (not (q x)))))"],
           "(forall ((x S)) (p x))")
    r = rep(f)
    assert r.nontrivial is False and any("equivalent to P1" in t for t in r.trivial_reasons)


def test_single_premise_strict_entailment_not_flagged():
    r = rep(mk([("p", []), ("q", []), ("r", [])], [], ["(and p q)"], "(or p q)"))
    assert r.valid == "valid" and r.nontrivial is True


# 3
def _unknown(monkeypatch, pred):
    orig = checks._check

    def fake(assertions, **kw):
        if pred(assertions):
            return checks._Res("unknown", None, [], "forced")
        return orig(assertions, **kw)
    monkeypatch.setattr(checks, "_check", fake)


def test_unknown_nontrivial_probe_fails_closed(monkeypatch):
    _unknown(monkeypatch, lambda a: any(n == "NEG_P" for n, _ in a))
    r = rep(mk([("p", []), ("q", [])], [], ["p", "(=> p q)"], "q"))
    assert r.nontrivial is None and r.unknown_probes and r.valid == "valid"


def test_unknown_minimality_probe_gives_none(monkeypatch):
    f = mk([("p", []), ("q", [])], [], ["p", "(=> p q)"], "q")
    parsed, _ = fol.validate(f)
    env, prem, concl = checks._lower_all(parsed)
    _unknown(monkeypatch, lambda a: True)
    unk: list = []
    assert checks.check_minimality(prem, concl, list(prem), unk) == []
    assert unk == ["minimality:P1", "minimality:P2"]


def test_unknown_consistency_with_unsat_entailment_is_open(monkeypatch):
    _unknown(monkeypatch, lambda a: [n for n, _ in a] == ["P1", "P2"])  # only the consistency probe
    r = rep(mk([("p", []), ("q", [])], [], ["p", "(=> p q)"], "q"))
    assert r.consistent == "unknown" and r.valid == "valid" and "consistency" in r.unknown_probes
    assert checks.verdict_of(r) == "open"


def test_select_penalizes_unknown_probe():
    st = run_cogito(1)
    rec = st.latest_reconstruction("cogito", "human")
    f = st.list_formalizations(rec.id)[0]
    f2 = f.model_copy(update={"check": f.check.model_copy(update={"unknown_probes": ["minimality:P1"]})})
    assert has_unknown_probe(f2.check) and not has_unknown_probe(f.check)
    assert score(f2, 2) == pytest.approx(score(f, 2) - config.UNKNOWN_PROBE_PENALTY)


def test_select_unknown_probe_not_rejected_and_reviewed():
    st = run_cogito(1)
    rec = st.latest_reconstruction("cogito", "human")
    f = st.list_formalizations(rec.id)[0]
    chk = f.check.model_copy(update={"unknown_probes": ["nontrivial:tautology:P1"], "nontrivial": None})
    st.execute("UPDATE formalization SET check_json=? WHERE id=?", (chk.model_dump_json(), f.id))
    sel = select_for(st, rec.id)
    assert sel.chosen_formalization_id == f.id
    assert any("unknown probe" in r["reason"] for r in st.query("SELECT reason FROM review"))


# 4
@pytest.mark.parametrize("pid", ["NEG_C", "NEG_P", "__trk_P1"])
def test_reserved_premise_ids_are_parse_errors(pid):
    f = FormalizationJSON.model_validate(mk([("c", []), ("d", [])], [], ["d"], "c").model_dump())
    f.premises[0].premise_id = pid
    r = checks.run_all(f)
    assert r.parse_ok is False and any("reserved" in e for e in r.parse_errors)


# 11
def test_constant_names_enforce_pattern():
    _, errs = fol.validate(mk([("p", ["S"])], ["Socrates"], ["(p Socrates)"], "(p Socrates)"))
    assert any("invalid constant name" in e for e in errs)


# 5
def test_propositional_skeleton_not_structured():
    assert not iso.skeleton("a", mk([("c", []), ("d", [])], [], ["d", "(=> d c)"], "c")).structured
    assert iso.skeleton("b", mk([("p", ["S"])], [], ["(forall ((x S)) (p x))"], "(forall ((y S)) (p y))")).structured


def test_selected_skeletons_only_valid_verdict():
    st = run_cogito(2)
    rec = st.latest_reconstruction("cogito", "human")
    skipped: list = []
    assert [s.argument_id for s in iso.selected_skeletons(st, ["cogito"], {"from_human": True}, skipped)] == ["cogito"]
    sel = st.get_selection(rec.id)
    st.insert_selection(SelectionResultX(**{**sel.model_dump(), "verdict": "refuted"}))
    assert iso.selected_skeletons(st, ["cogito"], {"from_human": True}, skipped) == []
    assert skipped and "refuted" in skipped[0][1]


def test_hash_equal_fast_path_survives_caps(monkeypatch):
    from .test_iso import sk
    a, b, f = sk("iso_a"), sk("iso_b"), sk("iso_false_friend")
    monkeypatch.setattr(config, "ISO_MAX_PREDS", 0)
    assert iso.match(a, b)["method"] == "hash"
    notes: list = []
    assert iso.match(a, f, notes=notes) is None and any("skipped" in n for n in notes)
    skipped: list = []
    iso.match_all([a, f], skipped=skipped)
    assert skipped and skipped[0][2].startswith("permutation search skipped")


# 6
def test_sort_names_do_not_block_isomorphism():
    a = mk([("p", ["Person", "Person"]), ("q", ["Person"])], ["a"],
           ["(forall ((x Person)) (p x a))", "(q a)"], "(exists ((y Person)) (q y))", sorts=("Person",))
    b = mk([("r", ["Obj", "Obj"]), ("t", ["Obj"])], ["k"],
           ["(forall ((z Obj)) (r z k))", "(t k)"], "(exists ((w Obj)) (t w))", sorts=("Obj",))
    sa, sb = iso.skeleton("A", a), iso.skeleton("B", b)
    assert sa.hash == sb.hash
    ev = iso.match(sa, sb)
    assert ev and ev["sort_mapping"] == {"Person": "Obj"}
    # permutation fallback path (hash forced apart) also works through the sort mapping
    sb.hash = "x"
    assert iso.match(sa, sb)["method"] == "permutation-fallback"


def test_sort_signature_distinguishes_structure():
    a = mk([("p", ["S", "T"])], [], ["(forall ((x S) (y T)) (p x y))"], "(exists ((x S) (y T)) (p x y))", sorts=("S", "T"))
    b = mk([("p", ["S", "S"])], [], ["(forall ((x S) (y S)) (p x y))"], "(exists ((x S) (y S)) (p x y))")
    assert iso.skeleton("A", a).hash != iso.skeleton("B", b).hash


def test_z3_confirm_logs_errors(monkeypatch):
    from .test_iso import sk
    a, b = sk("iso_a"), sk("iso_b")
    m = iso.find_mapping(a, b)[0]
    monkeypatch.setattr(iso.fol, "lower", lambda *x, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    log: list = []
    assert iso.z3_confirm(a, b, m, log=log) is False
    assert log and "RuntimeError: boom" in log[0]


# 7 / 8
def test_rejected_judge_counted_separately():
    st = run_cogito(1)
    rec = st.latest_reconstruction("cogito", "human")
    f = st.list_formalizations(rec.id)[0]
    j = f.judge.model_copy(update={"flags": ["sense_drift"], "hard_reject": True})
    st.execute("UPDATE formalization SET judge_json=? WHERE id=?", (j.model_dump_json(), f.id))
    sel = select_for(st, rec.id)
    assert sel.rejected_judge == 1 and sel.rejected_trivial == 0 and sel.chosen_formalization_id is None


def test_contested_over_all_parsed_candidates():
    st = run_cogito(2)  # candidate 1 (trivial, rejected) is also valid -> not contested
    rec = st.latest_reconstruction("cogito", "human")
    forms = {f.candidate_idx: f for f in st.list_formalizations(rec.id)}
    bad = forms[1].check.model_copy(update={"valid": "refuted", "countermodel_text": "x"})
    st.execute("UPDATE formalization SET check_json=? WHERE id=?", (bad.model_dump_json(), forms[1].id))
    sel = select_for(st, rec.id)
    assert sel.contested and sel.chosen_formalization_id == forms[0].id
    assert any("contested" in r["reason"] for r in st.query("SELECT reason FROM review"))


# 9
def test_cache_skips_empty_and_truncated(tmp_path):
    st = Store(tmp_path / "x.db")
    base = dict(stage="s", prompt_hash="h", model="m", error=None, sample_idx=0)
    st.insert_llm_call(**base, cache_key="k1", response="", stop_reason="end_turn")
    st.insert_llm_call(**base, cache_key="k2", response='{"a":1}', stop_reason="max_tokens")
    st.insert_llm_call(**base, cache_key="k3", response='{"a":1}', stop_reason="tool_use")
    assert st.find_cached_call("k1") is None and st.find_cached_call("k2") is None
    assert st.find_cached_call("k3")["stop_reason"] == "tool_use"


def test_stop_reason_migration(tmp_path):
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE llm_call(id INTEGER PRIMARY KEY, run_id INTEGER, stage TEXT, argument_id TEXT, "
              "candidate_idx INTEGER, sample_idx INTEGER NOT NULL DEFAULT 0, model TEXT, temperature REAL, "
              "prompt_name TEXT, prompt_hash TEXT NOT NULL, cache_key TEXT, prompt TEXT, response TEXT, "
              "input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER, error TEXT, created_at REAL)")
    c.commit(); c.close()
    st = Store(p)
    assert "stop_reason" in {r["name"] for r in st.query("PRAGMA table_info(llm_call)")}
    Store(p)  # idempotent


# 10
def test_atomic_operand_with_connective_gloss_is_parenthesized():
    f = FormalizationX.model_validate(dict(
        sorts=[{"name": "S"}],
        predicates=[{"name": "p", "arg_sorts": [], "gloss": "it rains or snows", "sense": "x"},
                    {"name": "q", "arg_sorts": [], "gloss": "it is cold", "sense": "x"}],
        constants=[], premises=[{"premise_id": "P1", "sexpr": "(=> p q)", "type": "empirical"}],
        conclusion={"premise_id": "C", "sexpr": "(and p q)", "type": "empirical"}))
    v = verbalize.verbalize(f)
    assert v["P1"] == "if (it rains or snows) then it is cold"
    assert v["C"] == "(it rains or snows) and it is cold"
    assert f.gloss_warnings()
