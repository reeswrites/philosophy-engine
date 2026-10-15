"""Select stage: the Z3 signals reject a trivialized candidate even when the (mock) judge scores it 1.0."""
from philengine import config, pipeline
from philengine.llm import MockLLMClient
from philengine.models_ext import FormalizationX
from philengine.stage_select import reject_reasons
from philengine.store import Store


def run_cogito(n=2, options=None):
    st = Store(":memory:")
    st.ingest(config.DATA_DIR / "arguments.json")
    rid = st.new_run(mock=True)
    llm = MockLLMClient(st, rid)
    opts = {"n_candidates": n, "from_human": True, **(options or {})}
    pipeline.run_all(st, rid, llm, ["cogito"], options=opts)
    return st


def test_trivialized_candidate_rejected_and_good_selected():
    st = run_cogito(2)
    rec = st.latest_reconstruction("cogito", "human")
    forms = {f.candidate_idx: f for f in st.list_formalizations(rec.id)}
    # sample 1 is trivialized (C == P2) and the mock judge says 1.0 for it
    assert forms[1].judge.min_score == 1.0 and forms[1].judge.conclusion_score == 1.0
    assert forms[1].check.nontrivial is False
    sel = st.get_selection(rec.id)
    assert sel.chosen_formalization_id == forms[0].id
    assert sel.verdict == "valid" and not sel.contested
    assert sel.rejected_trivial == 1
    by = {e["candidate_idx"]: e for e in sel.ranking}
    assert by[1]["score"] is None and any(r.startswith("trivial") for r in by[1]["rejected_reasons"])
    assert by[0]["score"] is not None and by[0]["rejected_reasons"] == []


def test_good_candidate_got_concepts_registered():
    st = run_cogito(2)
    rows = st.query("SELECT label, sense FROM concept ORDER BY label")
    assert {(r["label"], r["sense"]) for r in rows} >= {("thinks", "think:occurrent"), ("exists_actual", "exists:actual")}


def test_same_label_different_sense_two_concepts():
    st = Store(":memory:")
    a = st.upsert_concept("exists", "{0} exists", "exists:actual")
    b = st.upsert_concept("exists", "{0} exists in thought", "exists:in-the-understanding")
    assert a != b and len(st.query("SELECT 1 FROM concept WHERE label='exists'")) == 2


def test_hard_reject_by_judge_flag_alone():
    st = run_cogito(1)
    rec = st.latest_reconstruction("cogito", "human")
    f = st.list_formalizations(rec.id)[0]
    j = f.judge.model_copy(update={"flags": ["sense_drift"], "hard_reject": True})
    f2 = f.model_copy(update={"judge": j})
    reasons, _ = reject_reasons(f2)
    assert any("hard reject" in r for r in reasons)


def test_no_survivor_gives_open():
    st = run_cogito(2)
    rec = st.latest_reconstruction("cogito", "human")
    # a pool where only the trivialized candidate exists: n=2 but drop candidate 0 via fresh recon id
    from philengine.stage_select import select_for
    st.execute("DELETE FROM formalization WHERE candidate_idx=0")
    sel = select_for(st, rec.id)
    assert sel.chosen_formalization_id is None and sel.verdict == "open" and sel.rejected_trivial == 1


def test_slot_error_retries_then_parse_fail():
    # synthesized formalization for other arguments has 0-ary atoms (no slots) => valid; craft bad via fixture dir
    import json, tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "formalize").mkdir()
    bad = json.loads((Path(__file__).parent / "fixtures/mock_llm/formalize/cogito.json").read_text())[0]
    bad["predicates"][0]["gloss"] = "{0} thinks about {1}"
    (d / "formalize" / "cogito.json").write_text(json.dumps([bad]))
    st = Store(":memory:")
    st.ingest(config.DATA_DIR / "arguments.json")
    rid = st.new_run(mock=True)
    llm = MockLLMClient(st, rid, fixtures_dir=d)
    pipeline.run_all(st, rid, llm, ["cogito"], stages=("formalize",), options={"n_candidates": 1, "from_human": True})
    rec = st.latest_reconstruction("cogito", "human")
    f = st.list_formalizations(rec.id)[0]
    assert f.status == "parse_fail" and len(f.llm_call_ids) == 2  # one retry
    assert any("gloss" in e for e in f.check.parse_errors)
