"""Regression tests for fix round 3 (candidate diversity + dedupe, judge flag split, mean-score penalty +
judge-weak status, relaxed iso pass, unverified shared reliance)."""
import json

from philengine import checks, config, pipeline, report, stage_formalize, stage_iso as iso, stage_judge
from philengine.llm import MockLLMClient
from philengine.models_ext import (HARD_REJECT_FLAGS, FormalizationX, JudgeOut, JudgeReportX, SelectionResultX,
                                   hard_rejects)
from philengine.runner import Ctx
from philengine.stage_common import diversity, fingerprint
from philengine.stage_judge import build_report
from philengine.stage_select import reject_reasons, score, select_for
from philengine.store import Store

from . import test_fix_round as tfr
from .test_fix_round import fx, judge_ok
from .test_fix_round2 import _form, jr


def _two_premise_store(aid="a", expected="valid", shared=None):
    st = Store(":memory:")
    prem = [{"id": "P1", "text": "p holds.", "type": "empirical"}, {"id": "P2", "text": "if p then q.", "type": "empirical"}]
    if shared:
        prem[0]["shared_id"] = shared
    st.ingest_argument({"id": aid, "expected_verdict": expected, "reconstruction": {"premises": prem, "conclusion": "q holds."}})
    return st


# ---- 1. candidate diversity: banded hints, do-not-reuse, dedupe before judge, diversity metric
def test_hints_are_bands_and_differ_per_candidate():
    hs = [stage_formalize.strategy_hint(i, 3) for i in range(4)]
    assert len(set(hs)) == 4 and "{" not in "".join(hs)
    assert "at most 4 predicates" in hs[0] and "at least 5 predicates" in hs[1] and "between 3 and 6" in hs[2]
    assert stage_formalize.strategy_hint(0, 5) != stage_formalize.strategy_hint(0, 3)  # band follows premise count


def test_second_candidate_prompt_forbids_first_predicate_set():
    st = _two_premise_store()
    rec = st.latest_reconstruction("a", "human")
    f = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q").model_dump()
    prompts = {}

    class L(MockLLMClient):
        def _complete(self, *, user, sample_idx, **_):
            prompts[sample_idx] = user
            return json.dumps(f), 0, 0
    rid = st.new_run(mock=True)
    ctx = Ctx(store=st, llm=L(st, rid), run_id=rid, options={})
    stage_formalize.formalize_one(ctx, "a", rec, 0)
    stage_formalize.formalize_one(ctx, "a", rec, 1)
    assert "DO NOT REUSE" not in prompts[0]
    assert "DO NOT REUSE" in prompts[1] and "{p/0, q/0}" in prompts[1] and "candidate 0" in prompts[1]


def test_identical_candidates_judged_once_and_diversity_recorded():
    st = _two_premise_store()
    f = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q").model_dump()
    judge_calls = []

    class L(MockLLMClient):
        def _complete(self, *, stage, user, sample_idx, argument_id, **_):
            if stage == "formalize":
                return json.dumps(f), 0, 0
            judge_calls.append(sample_idx)
            return json.dumps(self._synthesize(stage, argument_id, user)), 0, 0
    rid = st.new_run(mock=True)
    pipeline.run_all(st, rid, L(st, rid), ["a"], stages=("formalize", "judge", "select"),
                     options={"n_candidates": 3, "from_human": True})
    rec = st.latest_reconstruction("a", "human")
    forms = {x.candidate_idx: x for x in st.list_formalizations(rec.id)}
    assert len(judge_calls) == config.JUDGE_SAMPLES  # candidates 1 and 2 copied candidate 0's report
    assert forms[0].judge.duplicate_of_candidate is None
    assert forms[1].judge.duplicate_of_candidate == 0 and forms[2].judge.duplicate_of_candidate == 0
    assert forms[1].judge.mean_score == forms[0].judge.mean_score and forms[1].judge.judge_call_ids == []
    sel = st.get_selection(rec.id)
    assert sel.diversity == {"n": 3, "distinct": 1, "distinct_pred_sets": 1, "ratio": 0.333}
    md = report.build_report(st, rid)
    assert "| 1/3 |" in md and "all candidates identical in: a" in md


def test_fingerprint_ignores_formatting_but_not_structure():
    a = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q")
    b = fx([("q", 0), ("p", 0)], ["p", "(=>   p   q)"], "q")
    c = fx([("p", 0), ("q", 0)], ["p", "(=> q p)"], "q")
    assert fingerprint(a) == fingerprint(b) != fingerprint(c)
    rec = type("R", (), {"formalization": a})
    assert diversity([rec, type("R", (), {"formalization": c})])["distinct"] == 2


# ---- 2. judge flag split
def test_reconstruction_gap_is_soft_and_omits_premise_is_hard():
    bt = {"P1": "x", "C": "y"}
    soft = build_report([JudgeOut(scores={"P1": 0.9}, conclusion_score=0.9, flags=["reconstruction_gap"]),
                         JudgeOut(scores={"P1": 0.9}, conclusion_score=0.9, flags=["reconstruction_gap"])], bt, "v")
    assert not soft.hard_reject and not hard_rejects(soft)
    assert not any("hard reject" in r for r in reject_reasons(_form(soft))[0])
    hard = build_report([JudgeOut(scores={"P1": 0.9}, conclusion_score=0.9, flags=["formalization_omits_premise"]),
                         JudgeOut(scores={"P1": 0.9}, conclusion_score=0.9, flags=["formalization_omits_premise"])], bt, "v")
    assert hard.hard_reject and any("hard reject" in r for r in reject_reasons(_form(hard))[0])
    assert "missing_implicit_premise" not in HARD_REJECT_FLAGS


def test_legacy_missing_implicit_premise_reports_are_reread_as_soft():
    # a report stored by the round-2 engine: hard_reject=True computed from the old flag set
    old = jr({"P1": 0.9}, concl=0.95, flags=["missing_implicit_premise"], hard=True,
             sample_flags=[["missing_implicit_premise"], ["missing_implicit_premise"]])
    assert not hard_rejects(old)
    reasons, _ = reject_reasons(_form(old))
    assert reasons == []  # fiction-beats-lies: Z3-valid, means 0.85-0.96, previously hard-rejected on this flag


def test_reconstruction_gap_routes_to_review_not_rejection():
    st = _two_premise_store()
    f = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q").model_dump()

    class L(MockLLMClient):
        def _complete(self, *, stage, user, sample_idx, argument_id, **_):
            if stage == "formalize":
                return json.dumps(f), 0, 0
            return json.dumps({"scores": {"P1": 0.9, "P2": 0.9}, "conclusion_score": 0.9,
                               "flags": ["reconstruction_gap"], "per_item_comments": {"P2": "needs an unstated bridge"}}), 0, 0
    rid = st.new_run(mock=True)
    pipeline.run_all(st, rid, L(st, rid), ["a"], stages=("formalize", "judge", "select"),
                     options={"n_candidates": 1, "from_human": True})
    rec = st.latest_reconstruction("a", "human")
    sel = st.get_selection(rec.id)
    assert sel.verdict == "valid" and sel.rejected_judge == 0 and sel.status == "selected"
    rows = [r for r in st.reviews(rid) if r["target_kind"] == "reconstruction"]
    assert len(rows) == 1 and rows[0]["target_id"] == "a" and "reconstruction_gap" in rows[0]["reason"] \
        and "unstated bridge" in rows[0]["reason"]


def test_judge_prompt_describes_split():
    t = (config.PROMPTS_DIR / "judge.v1.md").read_text()
    assert "formalization_omits_premise" in t and "reconstruction_gap" in t and "missing_implicit_premise" not in t


# ---- 3. mean_score is a penalty; judge-weak status
def test_mean_below_threshold_is_penalty_not_filter():
    weak = jr({"P1": 0.5, "P2": 0.6}, concl=0.95)  # mean 0.68
    assert weak.mean_score < config.JUDGE_MEAN_SCORE
    reasons, _ = reject_reasons(_form(weak))
    assert reasons == []
    ok = jr({"P1": 0.95, "P2": 0.95}, concl=0.95)
    assert score(_form(weak), 2) < score(_form(ok), 2)
    # conclusion_score is the only remaining score filter
    bad_c = jr({"P1": 0.95, "P2": 0.95}, concl=0.5)
    assert any("conclusion_score" in r for r in reject_reasons(_form(bad_c))[0])


def test_judge_weak_selection_has_status_and_review():
    st = _two_premise_store()
    rec = st.latest_reconstruction("a", "human")
    run = st.new_run()
    f = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q")
    st.insert_formalization(rec.id, 0, "ok", f, checks.run_all(f), jr({"P1": 0.5, "P2": 0.6}, concl=0.95), run_id=run)
    sel = select_for(st, rec.id, run)
    assert sel.verdict == "valid" and sel.judge_weak and sel.status == "judge-weak"
    assert "judge_weak" in sel.ranking[0]["flags"] and any("mean_score penalty" in n for n in sel.ranking[0]["notes"])
    assert any("judge-weak" in r["reason"] for r in st.reviews(run))
    st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rec.id))
    md = report.build_report(st, run)
    assert "| judge-weak |" in md and "Decided by Z3 but judge-weak" in md and "a" in md


def test_open_status_distinguishes_decided_but_rejected():
    st = _two_premise_store()
    rec = st.latest_reconstruction("a", "human")
    f = fx([("p", 0), ("q", 0)], ["p", "(=> p q)"], "q")
    hard = jr({"P1": 0.9, "P2": 0.9}, concl=0.9, flags=["sense_drift"], hard=True, sample_flags=[["sense_drift"], ["sense_drift"]])
    st.insert_formalization(rec.id, 0, "ok", f, checks.run_all(f), hard)
    sel = select_for(st, rec.id, 1)
    assert sel.verdict == "open" and sel.status == "open: decided candidates all rejected"
    st.execute("DELETE FROM formalization")
    assert select_for(st, rec.id, 1).status == "open: no candidates"
    assert report.selection_status(SelectionResultX(reconstruction_id=1, chosen_formalization_id=None, verdict="open",
                                                    ranking=[], rejected_trivial=0)) == "open: no decided candidate"


# ---- 4. relaxed isomorphism pass
def _pair_like_rees(side: str) -> FormalizationX:
    """Mimics the stored pair: side 'a' = commitment-reauthoring #34 (extra `author_of` guard in P2/P3, binder order
    (r a)); side 'b' = evaluator-drift #5 (explicit Agent/Rule sorts, binder order (l e), `evaluator_of e l`)."""
    if side == "a":
        return FormalizationX.model_validate({
            "predicates": [{"name": "self_authored", "arg_sorts": ["Obj"], "gloss": "{0} is self-authored", "sense": "s:1"},
                           {"name": "author_of", "arg_sorts": ["Obj", "Obj"], "gloss": "{0} authored {1}", "sense": "s:2"},
                           {"name": "controls", "arg_sorts": ["Obj", "Obj"], "gloss": "{0} controls {1}", "sense": "s:3"},
                           {"name": "constrains", "arg_sorts": ["Obj", "Obj"], "gloss": "{0} constrains {1}", "sense": "s:4"},
                           {"name": "costly_to_keep", "arg_sorts": ["Obj", "Obj"], "gloss": "{0} is costly for {1}", "sense": "s:5"}],
            "premises": [
                {"premise_id": "P1", "sexpr": "(forall ((r Obj) (a Obj)) (=> (and (self_authored r) (author_of a r)) (controls a r)))"},
                {"premise_id": "P2", "sexpr": "(forall ((r Obj) (a Obj)) (=> (and (author_of a r) (controls a r)) (=> (costly_to_keep r a) (not (constrains r a)))))"},
                {"premise_id": "P3", "sexpr": "(forall ((r Obj) (a Obj)) (=> (author_of a r) (=> (constrains r a) (costly_to_keep r a))))"}],
            "conclusion": {"premise_id": "C", "sexpr": "(forall ((r Obj) (a Obj)) (=> (and (self_authored r) (author_of a r)) (not (constrains r a))))"}})
    return FormalizationX.model_validate({
        "sorts": [{"name": "Agent"}, {"name": "Rule"}],
        "predicates": [{"name": "loop", "arg_sorts": ["Agent"], "gloss": "{0} is a loop", "sense": "s:1"},
                       {"name": "evaluator_of", "arg_sorts": ["Rule", "Agent"], "gloss": "{0} evaluates {1}", "sense": "s:2"},
                       {"name": "controls", "arg_sorts": ["Agent", "Rule"], "gloss": "{0} controls {1}", "sense": "s:3"},
                       {"name": "costly", "arg_sorts": ["Rule", "Agent"], "gloss": "{0} is costly for {1}", "sense": "s:5"},
                       {"name": "constrains", "arg_sorts": ["Rule", "Agent"], "gloss": "{0} constrains {1}", "sense": "s:4"}],
        "premises": [
            {"premise_id": "P1", "sexpr": "(forall ((l Agent) (e Rule)) (=> (and (loop l) (evaluator_of e l)) (controls l e)))"},
            {"premise_id": "P2", "sexpr": "(forall ((a Agent) (r Rule)) (=> (and (controls a r) (costly r a)) (not (constrains r a))))"},
            {"premise_id": "P3", "sexpr": "(forall ((a Agent) (r Rule)) (=> (constrains r a) (costly r a)))"}],
        "conclusion": {"premise_id": "C", "sexpr": "(forall ((l Agent) (e Rule)) (=> (and (loop l) (evaluator_of e l)) (not (constrains e l))))"}})


def test_relaxed_pass_matches_guard_sort_binder_and_flip_differences():
    a, b = iso.skeleton("cr", _pair_like_rees("a")), iso.skeleton("ed", _pair_like_rees("b"))
    assert iso.match(a, b) is None  # strict pass misses it (as in run 2)
    ra, rb = iso.relax_skeleton(a), iso.relax_skeleton(b)
    assert ra.abstractions == ("guard-dropped:author_of",) and rb.abstractions == ("sorts-erased:Agent,Rule",)
    ev = iso.match_relaxed(ra, rb)
    assert ev and ev["method"] == "relaxed" and ev["z3_verified"] and ev["relaxed"]
    assert ev["mapping"]["self_authored"] == "loop" and ev["mapping"]["author_of"] == "evaluator_of"
    assert "guard-dropped:author_of" in ev["abstractions"]["cr"]


def test_relaxed_pass_still_separates_modus_ponens_from_affirming_consequent():
    from .helpers import load
    mp = iso.skeleton("mp", FormalizationX.model_validate(load("modus_ponens").model_dump()))
    ac = iso.skeleton("ac", FormalizationX.model_validate(load("affirming_consequent").model_dump()))
    assert iso.match_relaxed(iso.relax_skeleton(mp), iso.relax_skeleton(ac)) is None


def test_relax_drops_redundant_premise_and_flattens_curry():
    f = fx([("p", 1), ("q", 1), ("r", 1)],
           ["(forall ((x Obj)) (=> (p x) (=> (q x) (r x))))", "(forall ((x Obj)) (p x))", "(forall ((x Obj)) (q x))",
            "(forall ((x Obj)) (r x))"], "(forall ((x Obj)) (r x))")
    chk = checks.run_all(f)
    f2, abs_ = iso.relax(f, chk.redundant_premises)
    assert all(f"redundant-dropped:{p}" in abs_ for p in chk.redundant_premises) and len(f2.premises) < 4
    assert iso.binder_canonical_text(iso.sx.parse("(forall ((x Obj) (y Obj)) (r x y))")) == \
        iso.binder_canonical_text(iso.sx.parse("(forall ((y Obj) (x Obj)) (r x y))"))


def test_iso_stage_stores_relaxed_match_and_eval_separates_it():
    st = Store(":memory:")
    for aid, other, f in (("cr", "ed", _pair_like_rees("a")), ("ed", "cr", _pair_like_rees("b"))):
        st.ingest_argument({"id": aid, "isomorphic_to": [other], "expected_verdict": "valid", "reconstruction": {
            "premises": [{"id": f"P{i}", "text": f"t{i}", "type": "empirical"} for i in (1, 2, 3)], "conclusion": "c"}})
        rid = st.latest_reconstruction(aid, "human").id
        st.insert_formalization(rid, 0, "ok", f, checks.run_all(f), judge_ok(f))
        select_for(st, rid, 1)
    pipeline.run_all(st, 1, None, None, ("iso",), {"from_human": True})
    (rel,) = st.relations("isomorphic-to")
    assert rel["evidence"]["relaxed"] and rel["evidence"]["method"] == "relaxed"
    ev = iso.iso_eval(st, 1)
    assert ev["found"] == set() and ev["recall"] == 0.0
    assert ev["relaxed"] == ev["relaxed_tp"] == {frozenset(("cr", "ed"))} and ev["recall_all"] == 1.0
    md = report.build_report(st, 1)
    assert "relaxed pass" in md and "cr~ed" in md


# ---- 5. shared reliance counts open arguments through their best candidate, tagged unverified
def test_shared_reliance_uses_unverified_candidate_for_open_arguments():
    st = Store(":memory:")
    for aid in ("a", "b"):
        st.ingest_argument({"id": aid, "expected_verdict": "valid", "reconstruction": {
            "premises": [{"id": "P1", "text": "p holds.", "type": "empirical", "shared_id": "SP1"},
                         {"id": "P2", "text": "q holds.", "type": "empirical"},
                         {"id": "P3", "text": "r holds.", "type": "empirical"}], "conclusion": "q holds"}})
    run = st.new_run()
    preds = [("p", 0), ("q", 0), ("r", 0)]
    f_idle = fx(preds, ["r", "p", "(=> p q)"], "q")  # P1 (SP1) redundant
    f_need = fx(preds, ["p", "(=> p q)", "r"], "q")  # P1 needed
    for aid, f, judge in (("a", f_idle, jr({"P1": 0.9, "P2": 0.9, "P3": 0.9}, concl=0.9, flags=["sense_drift"], hard=True,
                                           sample_flags=[["sense_drift"], ["sense_drift"]])),
                          ("b", f_need, judge_ok(f_need))):
        rid = st.latest_reconstruction(aid, "human").id
        st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rid))
        st.insert_formalization(rid, 0, "ok", f, checks.run_all(f), judge, run_id=run)
        select_for(st, rid, run)
    assert st.get_selection(st.latest_reconstruction("a", "human").id).verdict == "open"
    (d,) = report.shared_reliance(st, run)
    by = {x["argument"]: x for x in d["arguments"]}
    assert by["a"]["needed"] is False and by["a"]["unverified"] and by["a"]["candidate_verdict"] == "valid"
    assert by["b"]["needed"] is True and not by["b"]["unverified"]
    assert d["n_decided"] == 2 and d["n_unverified"] == 1 and d["n_needed"] == 1 and not d["idle"]
    md = report.build_report(st, run)
    assert "1/2 (of 2 citing; 1 unverified)" in md and "| a* |" in md
    # idle only through the unverified candidate -> starred
    st.execute("DELETE FROM formalization WHERE reconstruction_id=?", (st.latest_reconstruction("b", "human").id,))
    select_for(st, st.latest_reconstruction("b", "human").id, run)
    (d,) = report.shared_reliance(st, run)
    assert d["idle"] and not d["idle_verified"]
    assert "SP1*" in report.build_report(st, run)
