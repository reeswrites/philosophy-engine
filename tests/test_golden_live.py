"""Live golden check: LLM formalizes the human reconstructions; selected verdict should match expected."""
import pytest

from philengine import pipeline
from philengine.llm import LLMClient
from philengine.report import AGREE
from philengine.store import Store

ARGS = ["cogito", "epicurus-death", "mill-desirable", "induction-circular"]


@pytest.mark.llm
def test_golden_live_verdicts():
    st = Store(":memory:")
    st.ingest()
    rid = st.new_run({"from_human": True})
    out = pipeline.run_all(st, rid, LLMClient(st, rid), ARGS, ("formalize", "judge", "select"),
                           {"from_human": True, "n_candidates": 2})
    assert all(s.failed == 0 for s in out.values())
    ok, lines = 0, []
    for aid in ARGS:
        exp = st.get_argument(aid)["expected_verdict"]
        rec = st.latest_reconstruction(aid, "human")
        got = st.get_selection(rec.id).verdict
        hit = got == AGREE.get(exp, exp)
        ok += hit
        lines.append(f"{aid:20s} expected={exp:10s} selected={got:8s} {'OK' if hit else 'DIFF'}")
    print("\n" + "\n".join(lines))
    assert ok >= 3, "\n".join(lines)
