"""Regression tests for fix round 4 (self-confessed bridges, control-redundancy surfacing, projected iso pass,
confessed-bridges report column)."""
import json

from philengine import checks, config, report, stage_iso as iso, stage_judge
from philengine.llm import MockLLMClient
from philengine.models_ext import BRIDGE_FLAG, HARD_REJECT_FLAGS, FormalizationX, JudgeOut
from philengine.runner import Ctx
from philengine.stage_select import (confessed_bridge, confession_in_judge, confession_in_notes, control_redundancy,
                                     select_for)
from philengine.store import Store

from .test_fix_round import fx
from .test_fix_round2 import _form, jr
from .test_iso import ISO, sk

CONFESSION = ("The reconstruction lists no bridge from persistence to not dying (the orphan rule requires the "
              "predicate in a premise). I therefore put the bridge (persisting means not dying) inside P2, which goes "
              "beyond the stated P2, and flag it here. P3 is translated as stated.")
HONEST = ("No premise says that persisting excludes dying, so the argument is invalid as formalized. The bridge is "
          "missing and was not added. A bridge such as 'whatever raises what matters should be pursued' is not added, "
          "because that would strengthen P3. I kept it that way rather than add a premise.")


def _store(expected="invalid", n=3):
    st = Store(":memory:")
    prem = [{"id": f"P{i + 1}", "text": f"claim {i + 1}.", "type": "empirical"} for i in range(n)]
    st.ingest_argument({"id": "ctl", "expected_verdict": expected,
                        "reconstruction": {"premises": prem, "conclusion": "the conclusion."}})
    rec = st.latest_reconstruction("ctl", "human")
    return st, rec.id, st.new_run()


def _valid(notes=""):
    """P1 a, P2 (=> a c), P3 b |- c : valid, P3 redundant."""
    f = fx([("a", 0), ("b", 0), ("c", 0)], ["a", "(=> a c)", "b"], "c")
    return f.model_copy(update={"notes": notes})


def _refuted(notes=""):
    f = fx([("a", 0), ("b", 0), ("c", 0)], ["a", "b", "(=> a b)"], "c")  # refuted (c is an orphan: a soft penalty)
    return f.model_copy(update={"notes": notes})


def _put(st, rid, idx, f, j, run):
    return st.insert_formalization(rid, idx, "ok", f, checks.run_all(f), j, run_id=run)


OK = lambda: jr({"P1": 0.9, "P2": 0.9, "P3": 0.9}, concl=0.9)  # noqa: E731


# ---- 1. the notes heuristic
def test_confession_heuristic_positive_and_negative():
    assert confession_in_notes("I put the bridge inside P2") == "I put the bridge inside P2"
    assert confession_in_notes(CONFESSION).startswith("I therefore put the bridge inside P2")
    assert confession_in_notes("P2 is strengthened relative to the stated premise so the proof goes through.")
    assert confession_in_notes("P2 adds a condition that the reconstruction does not state.")
    assert confession_in_notes("This goes beyond what the reconstruction says.")
    assert confession_in_notes(HONEST) is None
    assert confession_in_notes("Formalized as stated; the argument needs a bridge premise the reconstruction lacks.") is None
    assert confession_in_notes("'Never' is approximated by a tenseless claim; no bridge was supplied.") is None
    assert confession_in_notes("") is None


def test_judge_flag_counts_only_when_every_sample_agrees():
    both = jr({"P1": 0.9}, flags=[BRIDGE_FLAG], sample_flags=[[BRIDGE_FLAG], [BRIDGE_FLAG]])
    both.per_item_comments = {"P2": "the notes admit the bridge was written into P2"}
    assert confession_in_judge(both).startswith("judge P2:")
    one = jr({"P1": 0.9}, flags=[BRIDGE_FLAG], sample_flags=[[BRIDGE_FLAG], []])
    assert confession_in_judge(one) is None
    assert BRIDGE_FLAG not in HARD_REJECT_FLAGS  # a confession signal, not a hard reject
    assert confessed_bridge(_form(both, formal=_valid())).startswith("judge")
    assert confessed_bridge(_form(one, formal=_valid())) is None


# ---- 2. the bridge rule in selection
def test_confessed_candidate_never_selected_over_faithful_decided_sibling():
    st, rid, run = _store("invalid")
    _put(st, rid, 0, _refuted(HONEST), OK(), run)       # faithful, Z3-refuted, survives
    _put(st, rid, 1, _valid(CONFESSION), OK(), run)     # confessed bridge, Z3-valid, would otherwise win on `minimal`
    sel = select_for(st, rid, run)
    assert sel.verdict == "refuted" and sel.status == "selected" and sel.rejected_bridge == 1
    by = {e["candidate_idx"]: e for e in sel.ranking}
    assert BRIDGE_FLAG in by[1]["flags"] and any(r.startswith("confessed bridge") for r in by[1]["rejected_reasons"])
    assert by[1]["score"] is None and by[0]["score"] is not None
    assert sel.confessed == {"1": "I therefore put the bridge inside P2"}
    assert any(r["reason"].startswith("confessed bridge:") and r["target_id"] == "ctl:1" for r in st.reviews(run))


def test_never_die_shape_faithful_siblings_rejected_on_conclusion_score():
    """Run-3 shape: the two faithful candidates are Z3-refuted but rejected on conclusion_score; the confessing one is
    Z3-valid and survives the judge. It must still not become the verdict."""
    st, rid, run = _store("invalid")
    low = jr({"P1": 0.9, "P2": 0.9, "P3": 0.9}, concl=0.6)
    _put(st, rid, 0, _refuted(HONEST), low, run)
    _put(st, rid, 1, _refuted("Formalized as stated."), low, run)
    _put(st, rid, 2, _valid(CONFESSION), OK(), run)
    sel = select_for(st, rid, run)
    assert sel.verdict == "open" and sel.chosen_formalization_id is None
    assert sel.status == "open: decided candidates all rejected" and sel.rejected_bridge == 1


def test_all_candidates_confess_selects_best_but_withholds_verdict():
    st, rid, run = _store("valid")
    _put(st, rid, 0, _valid("I put the bridge inside P2."), OK(), run)
    _put(st, rid, 1, _valid("P2 is strengthened beyond the stated premise."), OK(), run)
    sel = select_for(st, rid, run)
    assert sel.chosen_formalization_id is not None and sel.verdict == "open"
    assert sel.status == "needs bridge: I put the bridge inside P2." and sel.rejected_bridge == 0
    assert any(r["reason"].startswith("needs bridge:") and r["target_kind"] == "reconstruction" for r in st.reviews(run))
    st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rid))
    rows = report.per_argument(st, run)
    assert rows[0]["selected"] == "open" and rows[0]["agree"] is False and rows[0]["status"].startswith("needs bridge")


def test_no_confession_leaves_selection_unchanged():
    st, rid, run = _store("valid")
    _put(st, rid, 0, _valid(HONEST), OK(), run)
    sel = select_for(st, rid, run)
    assert sel.verdict == "valid" and sel.status == "selected" and sel.confessed == {} and sel.rejected_bridge == 0


# ---- 3. control valid via redundancy
def test_control_valid_via_redundancy_is_surfaced():
    assert control_redundancy(_form(OK(), formal=_valid()), "invalid") == ["P3"]
    assert control_redundancy(_form(OK(), formal=_valid()), "valid") == []
    assert control_redundancy(_form(OK(), formal=_refuted()), "invalid") == []
    st, rid, run = _store("invalid")
    _put(st, rid, 0, _valid("Formalized as stated."), OK(), run)
    sel = select_for(st, rid, run)
    e = sel.ranking[0]
    assert "control_valid_via_redundancy" in e["flags"] and any("without ['P3']" in n for n in e["notes"])
    assert any(r["reason"].startswith("control valid via redundancy: candidate 0") for r in st.reviews(run))
    st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rid))
    row = report.per_argument(st, run)[0]
    assert row["bridges"][0]["kind"] == "control-redundancy" and "c0 control valid without ['P3']" in row["bridges_text"]


# ---- 4. report / dashboard column
def test_report_has_confessed_bridges_column(tmp_path):
    from philengine import dashboard
    st, rid, run = _store("invalid")
    _put(st, rid, 0, _refuted(HONEST), OK(), run)
    _put(st, rid, 1, _valid(CONFESSION), OK(), run)
    select_for(st, rid, run)
    st.execute("UPDATE reconstruction SET run_id=? WHERE id=?", (run, rid))
    md = report.build_report(st, run)
    assert "| confessed bridges |" in md and 'c1 confessed (rejected): "I therefore put the bridge inside P2"' in md
    assert "Confessed bridges (round 4): ctl" in md and "projected pass" in md
    html = dashboard.build_html(st, run)
    assert "confessed bridges" in html and "I therefore put the bridge inside P2" in html


# ---- 5. judge sees the formalizer notes and may raise the flag
def test_judge_prompt_carries_formalizer_notes():
    t = (config.PROMPTS_DIR / "judge.v1.md").read_text()
    assert "formalization_adds_bridge" in t and "{{formalizer_notes}}" in t
    st, rid, run = _store("invalid")
    rec = st.get_reconstruction(rid)
    fid = _put(st, rid, 0, _valid(CONFESSION), None, run)
    seen = {}

    class L(MockLLMClient):
        def _complete(self, *, user, **_):
            seen["user"] = user
            return json.dumps({"scores": {"P1": 1, "P2": 0.5, "P3": 1}, "conclusion_score": 0.9,
                               "flags": [BRIDGE_FLAG], "per_item_comments": {"P2": "notes admit a bridge in P2"}}), 0, 0
    ctx = Ctx(store=st, llm=L(st, run), run_id=run, options={"judge_samples": 2})
    stage_judge.judge_one(ctx, "ctl", rec, st.get_formalization(fid))
    assert "FORMALIZER NOTES" in seen["user"] and "put the bridge" in seen["user"]
    j = st.get_formalization(fid).judge
    assert j.sample_flags == [[BRIDGE_FLAG], [BRIDGE_FLAG]] and not j.hard_reject
    out = JudgeOut(scores={}, conclusion_score=1, flags=[BRIDGE_FLAG])  # schema accepts the new flag
    assert out.flags == [BRIDGE_FLAG]


# ---- 6. iso: projected pass
def test_projected_pair_missed_by_strict_and_relaxed_found_by_projection():
    a, b = sk("iso_projected_a"), sk("iso_projected_b")
    assert a.hash != b.hash and iso.match(a, b) is None
    ra, rb = iso.relax_skeleton(a), iso.relax_skeleton(b)
    assert iso.match_relaxed(ra, rb) is None  # arity 2 vs 1 and a two-atom antecedent: beyond the relaxed pass
    found = iso.match_all([a, b], diagnose={frozenset(("iso_projected_a", "iso_projected_b"))})
    assert len(found) == 1
    _, _, ev = found[0]
    assert ev["method"] == "projected" and ev["projected"] and ev["relaxed"] and ev["z3_verified"] and ev["flips"] == []
    assert ev["abstractions"]["iso_projected_a"] == ["sorts-erased:Loop,Rule", "cluster-collapsed:checks+inside",
                                                    "arity-projected:heavy_for/2->1@1"]
    assert ev["abstractions"]["iso_projected_b"] == []
    assert ev["mapping"] == {"checks__inside": "made_by", "guards": "guards", "holds_for": "holds_for", "heavy_for": "heavy"}
    assert iso.is_rich(a) and iso.is_rich(b)


def test_projected_pass_declines_with_a_reason_for_truth_pairs():
    a = sk("iso_projected_a")
    two = sk("iso_a")  # 3 premises but a different arity profile and constants
    skipped = []
    assert iso.match_all([a, two], skipped=skipped, diagnose={frozenset(("iso_projected_a", "iso_a"))}) == []
    assert any(r.startswith("projected: declined: ") and "constants" in r for _, _, r in skipped)
    assert iso.match_all([a, two], skipped=(s2 := []), diagnose=set()) == [] and not any("declined" in r for *_, r in s2)


def test_cluster_collapse_requires_cooccurrence_everywhere():
    from philengine import fol
    f = FormalizationX.model_validate(json.loads((ISO / "iso_projected_a.json").read_text()))
    parsed, _ = fol.validate(f)
    pdecl = {p.name: tuple(p.arg_sorts) for p in f.predicates}
    assert iso.find_clusters(dict(parsed.formulas), pdecl) == [frozenset({"checks", "inside"})]
    # `checks` alone somewhere else -> no longer a cluster
    d = json.loads((ISO / "iso_projected_a.json").read_text())
    d["premises"][2]["sexpr"] = "(forall ((l Loop) (r Rule)) (=> (and (guards r l) (checks r l)) (heavy_for r l)))"
    f2 = FormalizationX.model_validate(d)
    parsed2, _ = fol.validate(f2)
    assert iso.find_clusters(dict(parsed2.formulas), pdecl) == []


def test_projection_only_on_uniform_positions():
    from philengine import fol
    d = json.loads((ISO / "iso_projected_a.json").read_text())
    d["constants"] = [{"name": "k", "sort": "Loop", "gloss": "k", "sense": "c:k"}]
    d["premises"][2]["sexpr"] = "(forall ((l Loop) (r Rule)) (=> (guards r l) (heavy_for r k)))"
    f = FormalizationX.model_validate(d)
    parsed, _ = fol.validate(f)
    pdecl = {p.name: tuple(p.arg_sorts) for p in f.predicates}
    pos = iso.projectable_positions(dict(parsed.formulas), pdecl)
    assert ("heavy_for", 0) in pos and ("heavy_for", 1) not in pos  # position 1 mixes a bound var and a constant
    assert ("guards", 0) in pos and ("guards", 1) in pos


def test_iso_stage_stores_projected_relation_and_eval(tmp_path):
    st = Store(":memory:")
    for aid, name in (("pa", "iso_projected_a"), ("pb", "iso_projected_b")):
        st.ingest_argument({"id": aid, "expected_verdict": "valid", "isomorphic_to": ["pb" if aid == "pa" else "pa"],
                            "reconstruction": {"premises": [{"id": f"P{i}", "text": f"p{i}.", "type": "empirical"}
                                                            for i in (1, 2, 3)], "conclusion": "c."}})
        rec = st.latest_reconstruction(aid, "human")
        f = FormalizationX.model_validate(json.loads((ISO / f"{name}.json").read_text()))
        fid = st.insert_formalization(rec.id, 0, "ok", f, checks.run_all(f), OK())
        select_for(st, rec.id, None)
    run = st.new_run()
    from philengine.runner import Unit
    iso.iso(Ctx(store=st, llm=None, run_id=run, options={}), Unit(argument_id="*", candidate_idx=-1))
    ev = iso.iso_eval(st, run)
    assert ev["projected"] == {frozenset(("pa", "pb"))} == ev["projected_tp"] and ev["recall_all"] == 1.0 and ev["recall"] == 0.0
    md = report.build_report(st, run)
    assert "| projected pass (cluster-collapsed / arity-projected, Z3-confirmed) | pa~pb |" in md
