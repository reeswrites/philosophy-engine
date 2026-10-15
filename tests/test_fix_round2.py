"""Regression tests for fix round 2."""
import json

from philengine import config, pipeline, report, senses, stage_formalize, stage_iso as iso
from philengine.llm import MockLLMClient
from philengine.models_ext import JudgeOut, JudgeReportX, ReconstructionX
from philengine.runner import Ctx
from philengine.stage_judge import build_report
from philengine.stage_select import judge_min_penalty, reject_reasons, score, select_for
from philengine.store import Store

from .test_fix_round import fx, store_with
from . import test_fix_round as tfr


def jr(scores, concl=0.9, flags=(), sample_flags=None, hard=False):
    allv = [*scores.values(), concl]
    return JudgeReportX(back_translations={}, scores=scores, conclusion_score=concl, min_score=min(allv),
                        mean_score=sum(allv) / len(allv), flags=list(flags), per_item_comments={},
                        hard_reject=hard, sample_flags=sample_flags or [])


def _form(judge, expected=None, premises=("p", "not p"), formal=None):
    from philengine import checks
    from philengine.schemas import FormalizationRecord
    f = formal or fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q")
    return FormalizationRecord(id=1, reconstruction_id=1, candidate_idx=0, formalization=f, check=checks.run_all(f),
                               judge=judge, status="ok", llm_call_ids=[])


# 1. gate
def test_gate_b_and_c():
    st = Store(":memory:")
    st.ingest()
    rid = st.new_run(mock=False)
    g = report.gate(st, rid)
    assert not g["b_ok"] and not g["c_ok"] and g["agreement"] == 0.0 and not g["passed"]
    st2 = Store(":memory:")
    st2.ingest()
    mid = st2.new_run(mock=True)
    g2 = report.gate(st2, mid)
    assert g2["b_ok"] and g2["c_ok"]


def test_gate_b_counts_judge_smuggled_rejects():
    sel = type("S", (), {"ranking": [{"rejected_reasons": ["judge hard reject: ['conclusion_smuggled']"]},
                                     {"rejected_reasons": ["judge hard reject: ['sense_drift']"]}]})()
    assert report.smuggled_rejects({"sel": sel}) == 1


# 2. min_score is a penalty
def test_min_score_penalty_not_filter():
    j = jr({"P1": 0.5, "P2": 0.5, "P3": 0.5, "P4": 0.95}, concl=0.95)
    pen, bad = judge_min_penalty(j)
    assert pen == config.JUDGE_MIN_PENALTY_CAP and bad == ["P1", "P2", "P3"]
    j1 = jr({"P1": 0.5, "P2": 0.95}, concl=0.95)
    assert judge_min_penalty(j1)[0] == config.JUDGE_MIN_PENALTY
    j1.mean_score = 0.9
    reasons, _ = reject_reasons(_form(j1))
    assert not any("min_score" in r for r in reasons)
    ok = jr({"P1": 0.95, "P2": 0.95}, concl=0.95)
    assert score(_form(j1), 2) < score(_form(ok), 2)


# 3. smuggled ignored for expected-inconsistent unsat
def test_smuggled_ignored_when_inconsistent_expected():
    f = fx([("p", 0), ("q", 0)], ["p", "(not p)"], "q")
    j = jr({"P1": 0.95, "P2": 0.95}, concl=0.95, flags=["conclusion_smuggled"], hard=True,
           sample_flags=[["conclusion_smuggled"], ["conclusion_smuggled"]])
    form = _form(j, formal=f)
    assert form.check.consistent == "unsat"
    assert any("hard reject" in r for r in reject_reasons(form, True, None)[0])
    assert not any("hard reject" in r for r in reject_reasons(form, True, "inconsistent")[0])
    j2 = jr({"P1": 0.95, "P2": 0.95}, concl=0.95, flags=["conclusion_smuggled", "sense_drift"], hard=True,
            sample_flags=[["conclusion_smuggled"], ["sense_drift"]])
    assert any("hard reject" in r for r in reject_reasons(_form(j2, formal=f), True, None)[0])
    assert not any("hard reject" in r for r in reject_reasons(_form(j2, formal=f), True, "inconsistent")[0])


def test_build_report_records_sample_flags():
    r = build_report([JudgeOut(scores={"P1": 1}, conclusion_score=1, flags=["conclusion_smuggled"]),
                      JudgeOut(scores={"P1": 1}, conclusion_score=1, flags=[])], {"P1": "x", "C": "y"}, "")
    assert r.sample_flags == [["conclusion_smuggled"], []] and not r.hard_reject


def test_judge_prompt_text():
    t = (config.PROMPTS_DIR / "judge.v1.md").read_text()
    assert "inconsistent premise set is NOT smuggling" in t and "idle" in t and "`strengthened`" in t


# 4. shared_id
def _shared_store():
    st = Store(":memory:")
    for aid in ("a", "b"):
        st.ingest_argument({"id": aid, "expected_verdict": "valid", "reconstruction": {
            "premises": [{"id": "P1", "text": "p holds.", "type": "empirical", "shared_id": "SP1"},
                         {"id": "P2", "text": "q holds.", "type": "empirical"},
                         {"id": "P3", "text": "r holds.", "type": "empirical"}], "conclusion": "q holds"}})
    return st


def test_shared_id_survives_and_reliance_table():
    st = _shared_store()
    assert st.latest_reconstruction("a", "human").reconstruction.premises[0].shared_id == "SP1"
    from philengine import checks
    run = st.new_run()
    preds = [("p", 0), ("q", 0), ("r", 0)]
    f_idle = fx(preds, ["r", "p", "(=> p q)"], "q")  # P1 redundant
    f_need = fx(preds, ["p", "(=> p q)", "r"], "q")  # P1 needed
    for aid, f in (("a", f_idle), ("b", f_need)):
        rid = st.latest_reconstruction(aid, "human").id
        st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rid))
        st.insert_formalization(rid, 0, "ok", f, checks.run_all(f), tfr.judge_ok(f), run_id=run)
        select_for(st, rid, run)
    (d,) = report.shared_reliance(st, run)
    assert d["shared_id"] == "SP1" and d["n_args"] == 2 and d["n_decided"] == 2 and d["n_needed"] == 1
    assert not d["idle"]
    md = report.build_report(st, run)
    assert "Shared premise reliance" in md and "SP1" in md


# 5. iso unverified
def test_iso_open_argument_uses_top_candidate_unverified():
    st = Store(":memory:")
    from philengine import checks
    f = tfr.BARE("a", "b", "k")
    for aid in ("x", "y"):
        st.ingest_argument({"id": aid, "expected_verdict": "valid", "reconstruction": {
            "premises": [{"id": "P1", "text": "u", "type": "empirical"}, {"id": "P2", "text": "v", "type": "empirical"}],
            "conclusion": "w"}})
    for aid in ("x", "y"):
        rid = st.latest_reconstruction(aid, "human").id
        st.insert_formalization(rid, 0, "ok", f, checks.run_all(f), tfr.judge_ok(f))
    # x selected normally; y forced open (all rejected)
    select_for(st, st.latest_reconstruction("x", "human").id, 1)
    yid = st.latest_reconstruction("y", "human").id
    from philengine.models_ext import SelectionResultX
    st.insert_selection(SelectionResultX(reconstruction_id=yid, chosen_formalization_id=None, verdict="open",
                                         ranking=[], rejected_trivial=0), 1)
    sk = iso.selected_skeletons(st, ["x", "y"], {"from_human": True})
    assert {s.argument_id: s.unverified for s in sk} == {"x": False, "y": True}
    pipeline.run_all(st, 1, None, None, ("iso",), {"from_human": True})
    ev = iso.iso_eval(st, 1)
    assert ev["found"] == set() and ev["unverified"] == set()  # bare shape -> weak
    assert ev["unverified_weak"] == {frozenset(("x", "y"))}
    assert ev["recall_all"] is None or ev["recall_all"] == 0.0


# 6. sense registry + normalization
def test_second_formalize_prompt_contains_first_predicates():
    st = Store(":memory:")
    for aid in ("a", "b"):
        st.ingest_argument({"id": aid, "reconstruction": {"premises": [{"id": "P1", "text": "p holds.", "type": "empirical"}],
                                                          "conclusion": "q holds."}})
    f = fx([("zorp", 0), ("q", 0)], ["zorp"], "q").model_dump()
    prompts = []

    class L(MockLLMClient):
        def _complete(self, *, user, **_):
            prompts.append(user)
            return json.dumps(f), 0, 0
    rid = st.new_run(mock=True)
    ctx = Ctx(store=st, llm=L(st, rid), run_id=rid, options={})
    stage_formalize.formalize_one(ctx, "a", st.latest_reconstruction("a", "human"), 0)
    stage_formalize.formalize_one(ctx, "b", st.latest_reconstruction("b", "human"), 0)
    assert "SENSE REGISTRY" not in prompts[0]
    assert "SENSE REGISTRY" in prompts[1] and "zorp | s:zorp" in prompts[1]


def test_registry_cap_and_order():
    st = Store(":memory:")
    for i in range(70):
        st.upsert_concept(f"c{i}", f"{{0}} c{i}", "s", run_id=1)
    for _ in range(3):
        st.upsert_concept("c69", "{0} c69", "s", run_id=1)
    rows = st.sense_registry(1, config.SENSE_REGISTRY_MAX)
    assert len(rows) == 60 and rows[0]["label"] == "c69"


def test_sense_normalization_folds_label_repeat():
    assert senses.normalize_sense("Feels-Good:Feels Good Hedonic", "feels_good") == "feels_good:hedonic"
    assert senses.normalize_sense("feels_good:feels_good", "feels_good") == "feels_good"
    assert senses.normalize_sense("a b:c!d") == "a_b:c_d"
    assert senses.normalize_sense("exists:actual", "exists_actual") == "exists:actual"


# 7. from_human: no reconstruct LLM call
def test_from_human_makes_no_reconstruct_call():
    st = Store(":memory:")
    st.ingest(config.data_dir() / "phase0" / "arguments.json")
    rid = st.new_run(mock=True)
    llm = MockLLMClient(st, rid)
    pipeline.run_all(st, rid, llm, ["cogito"], stages=("reconstruct",), options={"from_human": True})
    assert st.llm_calls("reconstruct") == []
    row = st.one("SELECT source FROM reconstruction WHERE argument_id='cogito' AND run_id=?", (rid,))
    assert row["source"] == "human"
    pipeline.run_all(st, rid, llm, ["cogito"], stages=("reconstruct",), options={"from_human": True})
    assert len(st.query("SELECT 1 FROM reconstruction WHERE argument_id='cogito' AND run_id=?", (rid,))) == 1
