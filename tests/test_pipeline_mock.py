from philengine import config, pipeline
from philengine import stage_iso as iso
from philengine.llm import MockLLMClient
from philengine.store import Store


def test_mock_end_to_end_all_arguments():
    st = Store(":memory:")
    st.ingest(config.DATA_DIR / "arguments.json")
    rid = st.new_run(mock=True)
    llm = MockLLMClient(st, rid)
    out = pipeline.run_all(st, rid, llm)  # default: LLM reconstruct, N=3
    assert all(s.failed == 0 for s in out.values()), {k: (v.failed) for k, v in out.items()}
    ids = st.argument_ids()
    assert len(ids) == 15
    verdicts = {}
    for aid in ids:
        rec = st.latest_reconstruction(aid, "llm")
        assert rec is not None
        sel = st.get_selection(rec.id)
        assert sel is not None
        verdicts[aid] = sel.verdict
    assert verdicts["cogito"] == "valid"
    assert set(verdicts.values()) <= {"valid", "refuted", "open"}
    assert len(iso.skeleton_hashes(st, rid)) >= 1
    # rerun is a no-op (resume)
    again = pipeline.run_all(st, rid, llm)
    assert all(s.done == 0 for s in again.values())
