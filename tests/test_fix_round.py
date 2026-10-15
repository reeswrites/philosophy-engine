"""Regression tests for the Phase 0 fix round (candidate diversity, soft orphan, inconsistent verdict,
iso richness, concept normalization + per-run registry, judge sampling)."""
import json
import sqlite3

import pytest

from philengine import checks, config, pipeline, report, senses, stage_iso as iso
from philengine.llm import MockLLMClient
from philengine.models_ext import FormalizationX, JudgeOut, JudgeReportX, PremiseX, ReconstructionX
from philengine.runner import Ctx
from philengine.stage_judge import build_report
from philengine.stage_select import inconsistency_allowed, reject_reasons, score, select_for
from philengine.store import Store


def fx(preds, premises, concl, consts=()):
    return FormalizationX.model_validate({
        "predicates": [{"name": n, "arg_sorts": ["Obj"] * a, "gloss": " ".join(["{%d}" % i for i in range(a)]) + f" {n}" if a else n,
                       "sense": f"s:{n}"} for n, a in preds],
        "constants": [{"name": n, "sort": "Obj", "gloss": n, "sense": f"c:{n}"} for n in consts],
        "premises": [{"premise_id": f"P{i + 1}", "sexpr": x} for i, x in enumerate(premises)],
        "conclusion": {"premise_id": "C", "sexpr": concl}})


def judge_ok(f, mean=0.9):
    return JudgeReportX(back_translations={}, scores={}, conclusion_score=mean, min_score=mean, mean_score=mean,
                        flags=[], per_item_comments={})


def store_with(premises, expected=None, concl="c"):
    st = Store(":memory:")
    a = {"id": "a", "reconstruction": {"premises": [{"id": f"P{i + 1}", "text": t, "type": "empirical"}
                                                    for i, t in enumerate(premises)], "conclusion": concl}}
    if expected:
        a["expected_verdict"] = expected
    st.ingest_argument(a)
    return st, st.latest_reconstruction("a", "human").id


# ---- 1. candidate diversity
def test_each_candidate_idx_gets_distinct_hint_in_prompt_and_row():
    from philengine import stage_formalize
    st = Store(":memory:")
    st.ingest_argument({"id": "a", "reconstruction": {"premises": [{"id": "P1", "text": "p holds.", "type": "empirical"}],
                                                      "conclusion": "q holds."}})
    rec = st.latest_reconstruction("a", "human")
    f = fx([("p", 0), ("q", 0)], ["p"], "q").model_dump()
    prompts = {}

    class L(MockLLMClient):
        def _complete(self, *, user, sample_idx, **_):
            prompts[sample_idx] = user
            return json.dumps(f), 0, 0
    rid = st.new_run(mock=True)
    ctx = Ctx(store=st, llm=L(st, rid), run_id=rid, options={})
    for i in range(4):
        stage_formalize.formalize_one(ctx, "a", rec, i)
    assert len(set(prompts.values())) == 4
    hints = [stage_formalize.strategy_hint(i, 1) for i in range(4)]
    for i, h in enumerate(hints):
        assert h in prompts[i]
    rows = {r.candidate_idx: r for r in st.list_formalizations(rec.id)}
    assert [rows[i].strategy_hint for i in range(4)] == hints
    assert stage_formalize.strategy_hint(0) == stage_formalize.strategy_hint(len(config.STRATEGY_HINTS))  # deterministic


# ---- 2. soft orphan
def orphan_form():
    return fx([("p", 0), ("q", 0), ("z", 0)], ["(=> p q)", "p"], "z")


def test_orphan_is_soft_flag_not_trivial():
    chk = checks.run_all(orphan_form())
    assert chk.orphan_conclusion_predicate == ["z"]
    assert chk.nontrivial is True and not any("orphan" in r for r in chk.trivial_reasons)


def test_orphan_with_tautological_conclusion_still_trivial():
    f = fx([("p", 0), ("z", 0)], ["p"], "(or z (not z))")
    chk = checks.run_all(f)
    assert chk.nontrivial is False and any("orphan" in r for r in chk.trivial_reasons)


def test_orphan_penalized_and_reviewed_not_rejected():
    st, rid = store_with(["p implies q.", "p."], concl="z")
    f = orphan_form()
    chk = checks.run_all(f)
    st.insert_formalization(rid, 0, "ok", f, chk, judge_ok(f))
    sel = select_for(st, rid, run_id=3)
    e = sel.ranking[0]
    assert sel.chosen_formalization_id is not None and e["rejected_reasons"] == []
    form = st.list_formalizations(rid)[0]
    assert e["score"] == round(score(form, 3) - config.ORPHAN_CONCLUSION_PENALTY, 6)
    assert e["flags"] == ["orphan_conclusion_predicate"]
    (rv,) = st.query("SELECT * FROM review WHERE reason LIKE 'orphan_conclusion_predicate%'")
    assert rv["run_id"] == 3


# ---- 3. inconsistent verdict
INCONS = lambda: fx([("p", 0), ("q", 0)], ["p", "(not p)"], "q")  # noqa: E731


def test_verdict_of_inconsistent():
    assert checks.verdict_of(checks.run_all(INCONS())) == "inconsistent"


def _incons_store(expected, n_incons=1, n_ok=1):
    st, rid = store_with(["p.", "not p."], expected=expected)
    ok = fx([("p", 0), ("q", 0)], ["(=> p q)", "p"], "q")
    for i in range(n_incons):
        f = INCONS()
        st.insert_formalization(rid, i, "ok", f, checks.run_all(f), judge_ok(f))
    for i in range(n_ok):
        st.insert_formalization(rid, n_incons + i, "ok", ok, checks.run_all(ok), judge_ok(ok))
    return st, rid


def test_inconsistent_kept_when_expected():
    st, rid = _incons_store("inconsistent")
    sel = select_for(st, rid)
    assert sel.rejected_trivial == 0
    by = {e["candidate_idx"]: e for e in sel.ranking}
    assert by[0]["rejected_reasons"] == [] and by[0]["score"] is not None


def test_inconsistent_kept_when_two_candidates_agree():
    st, rid = _incons_store("valid", n_incons=2, n_ok=0)
    sel = select_for(st, rid)
    assert sel.verdict == "inconsistent" and sel.rejected_trivial == 0 and sel.chosen_formalization_id is not None


def test_single_unexpected_inconsistent_still_vacuous():
    st, rid = _incons_store("valid")
    forms = st.list_formalizations(rid)
    assert not inconsistency_allowed(forms, "valid")
    sel = select_for(st, rid)
    assert sel.rejected_trivial == 1 and sel.verdict == "valid"
    by = {e["candidate_idx"]: e for e in sel.ranking}
    assert "vacuous" in by[0]["rejected_reasons"]


def test_report_scores_inconsistent_directly_and_gate_ignores_unsat_rejects():
    st, rid = _incons_store("inconsistent", n_ok=0)
    run = st.new_run()
    st.execute("UPDATE reconstruction SET run_id=?", (run,))
    select_for(st, rid, run)
    (row,) = report.per_argument(st, run)
    assert row["selected"] == "inconsistent" and row["agree"] is True and row["rejected_trivial"] == 0
    # a selection stored the old way (unsat candidate rejected as trivial/vacuous) is not counted by the gate either
    sel = st.get_selection(rid)
    sel.ranking[0]["rejected_reasons"] = ["trivial: premises inconsistent (argument vacuously valid)", "vacuous"]
    sel.rejected_trivial = 1
    st.insert_selection(sel, run)
    assert report.per_argument(st, run)[0]["rejected_trivial"] == 0


# ---- 4. iso richness
def _skel(aid, f):
    s = iso.skeleton(aid, f)
    assert s is not None
    return s


BARE = lambda a, b, c: fx([(a, 1), (b, 1)], [f"(forall ((x Obj)) (=> ({a} x) ({b} x)))", f"({a} {c})"], f"({b} {c})", [c])  # noqa: E731


def test_bare_modus_ponens_is_not_rich_but_rich_shapes_are():
    assert not iso.is_rich(_skel("x", BARE("a", "b", "k")))
    three = fx([("a", 1), ("b", 1)], ["(forall ((x Obj)) (=> (a x) (b x)))", "(a k)", "(a j)"], "(b k)", ["k", "j"])
    assert iso.is_rich(_skel("y", three))
    binary = fx([("a", 1), ("r", 2)], ["(forall ((x Obj)) (=> (a x) (exists ((y Obj)) (r x y))))", "(a k)"],
                "(exists ((y Obj)) (r k y))", ["k"])
    assert iso.is_rich(_skel("z", binary))
    one_pred = fx([("r", 2)], ["(forall ((x Obj)) (r x x))", "(r k k)"], "(r k k)", ["k"])
    assert not iso.is_rich(_skel("w", one_pred))


def test_bare_matches_recorded_as_weak_isomorphic_and_graded(tmp_path):
    st = Store(":memory:")
    for aid, other, f in (("cogito", "kalam", BARE("thinks", "exists_a", "i")), ("kalam", "cogito", BARE("begins", "caused", "u"))):
        st.ingest_argument({"id": aid, "weak_isomorphic_to": [other], "expected_verdict": "valid",
                            "reconstruction": {"premises": [{"id": "P1", "text": "x", "type": "empirical"},
                                                            {"id": "P2", "text": "y", "type": "empirical"}], "conclusion": "z"}})
        rid = st.latest_reconstruction(aid, "human").id
        st.insert_formalization(rid, 0, "ok", f, checks.run_all(f), judge_ok(f))
        select_for(st, rid, 1)
    pipeline.run_all(st, 1, None, None, ("iso",), {"from_human": True})
    assert st.relations("isomorphic-to") == []
    (w,) = st.relations("weak-isomorphic")
    assert {w["src_id"], w["dst_id"]} == {"cogito", "kalam"}
    ev = iso.iso_eval(st, 1)
    assert not ev["fp"] and ev["found"] == set()
    assert ev["weak_correct"] == {frozenset(("cogito", "kalam"))}


# ---- 5. normalization + per-run registry
def test_normalize_label_and_sense():
    assert senses.normalize_label("Exists-Actually") == senses.normalize_label("exists_actual") == "exists_actual"
    assert senses.normalize_label("a  b__c") == "a_b_c"
    assert senses.normalize_sense("person:moral") == senses.normalize_sense("Person:Moral-Person") == "person:moral"
    assert senses.normalize_sense("exists:actual") == senses.normalize_sense("exists:actually")
    assert senses.normalize_label("happy") == "happy"  # no stemming
    assert senses.normalize_label("persons") == "persons"


def test_spelling_variants_collapse_and_raw_label_kept():
    st = Store(":memory:")
    st.upsert_concept("exists_actual", "{0} exists", "exists:actual", "a1", run_id=1)
    st.upsert_concept("exists_actually", "{0} exists", "exists:actually", "a2", run_id=1)
    rows = st.concepts(1)
    assert len(rows) == 1 and rows[0]["label"] == "exists_actual" and rows[0]["raw_label"] == "exists_actual"
    assert not st.query("SELECT 1 FROM relation WHERE kind IN ('sense-split','sense-alias')")
    st.upsert_concept("Exists-Actually", "{0} exists differently", "exists:actual", "a3", run_id=1)
    assert {r["raw_label"] for r in st.concepts(1)} == {"exists_actual", "Exists-Actually"}


def test_registry_and_review_are_per_run():
    st = Store(":memory:")
    st.upsert_concept("p", "{0} p", "p:one", "a", run_id=1)
    st.upsert_concept("p", "{0} p", "p:one", "a", run_id=2)
    st.upsert_concept("p", "{0} p2", "p:two", "a", run_id=2)  # split only inside run 2
    assert len(st.concepts(1)) == 1 and len(st.concepts(2)) == 2
    assert [r["run_id"] for r in st.reviews()] == [2] and st.reviews(1) == []


def test_migration_adds_columns_and_backfills(tmp_path):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript("""
      CREATE TABLE run(id INTEGER PRIMARY KEY, started_at REAL, config_json TEXT, git_sha TEXT, z3_version TEXT, mock INTEGER DEFAULT 0);
      CREATE TABLE concept(id TEXT PRIMARY KEY, label TEXT, gloss TEXT, sense TEXT, first_seen TEXT);
      CREATE TABLE review(id INTEGER PRIMARY KEY, target_kind TEXT, target_id TEXT, reason TEXT, state TEXT DEFAULT 'open', note TEXT, created_at REAL);
      CREATE TABLE formalization(id INTEGER PRIMARY KEY, reconstruction_id INTEGER NOT NULL, candidate_idx INTEGER NOT NULL, run_id INTEGER,
        status TEXT NOT NULL, formalization_json TEXT, check_json TEXT, judge_json TEXT, llm_call_ids_json TEXT DEFAULT '[]');
      CREATE TABLE job(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, argument_id TEXT, stage TEXT, candidate_idx INTEGER DEFAULT -1,
        status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT, started_at REAL, finished_at REAL);
      INSERT INTO run(id) VALUES (6);
      INSERT INTO concept VALUES ('c1','exists_actually','{0} e','exists:actually','a');
      INSERT INTO formalization(reconstruction_id,candidate_idx,run_id,status,formalization_json)
        VALUES (1,0,6,'ok','{"predicates":[{"name":"exists_actually","sense":"exists:actually"}]}');
      INSERT INTO job(run_id,argument_id,stage,started_at,finished_at) VALUES (6,'a','formalize',100,200);
      INSERT INTO review(target_kind,target_id,reason,created_at) VALUES ('x','y','r',150);
    """)
    c.commit()
    c.close()
    st = Store(path)
    (row,) = st.concepts(6)
    assert row["label"] == "exists_actual" and row["raw_label"] == "exists_actually" and row["sense"] == "exists:actual"
    assert [r["run_id"] for r in st.reviews(6)] == [6]
    Store(path)  # idempotent


# ---- 6. judge sampling
def out(scores, concl=0.9, flags=()):
    return JudgeOut(scores=scores, conclusion_score=concl, flags=list(flags))


def test_judge_scores_averaged_and_hard_reject_needs_both():
    bt = {"P1": "a", "C": "b"}
    r = build_report([out({"P1": 0.4}, 0.8), out({"P1": 0.8}, 1.0)], bt, "v", [7, 8])
    assert r.scores["P1"] == pytest.approx(0.6) and r.conclusion_score == pytest.approx(0.9)
    assert r.min_score == pytest.approx(0.6) and r.n_samples == 2 and r.judge_call_ids == [7, 8]
    one = build_report([out({"P1": 0.9}, flags=["sense_drift"]), out({"P1": 0.9})], bt, "v")
    assert not one.hard_reject and "sense_drift" in one.flags
    both = build_report([out({"P1": 0.9}, flags=["sense_drift"]), out({"P1": 0.9}, flags=["formalization_omits_premise"])], bt, "v")
    assert both.hard_reject


def test_judge_stage_makes_two_calls_and_records_ids():
    st = Store(":memory:")
    st.ingest(config.data_dir() / "phase0" / "arguments.json")
    rid = st.new_run(mock=True)
    pipeline.run_all(st, rid, MockLLMClient(st, rid), ["cogito"], options={"n_candidates": 1, "from_human": True})
    rec = st.latest_reconstruction("cogito", "human")
    (f,) = st.list_formalizations(rec.id)
    assert f.judge.n_samples == config.JUDGE_SAMPLES == 2 and len(f.judge.judge_call_ids) == 2
    assert {c["sample_idx"] for c in st.llm_calls("judge")} == {0, 1}
    assert set(f.judge.judge_call_ids) <= set(f.llm_call_ids)
