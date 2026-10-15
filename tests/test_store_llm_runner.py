import json
import os

import pytest

from philengine import checks, config, prompts
from philengine.llm import LLMClient, MockLLMClient, prompt_hash
from philengine.models_ext import FormalizationX, JudgeOut
from philengine.runner import Ctx, Runner
from philengine.store import Store

ARGS = config.DATA_DIR / "arguments.json"


@pytest.fixture
def store():
    s = Store(":memory:")
    s.ingest(ARGS)
    return s


def test_ingest_real_arguments(store):
    raw = json.loads(ARGS.read_text())
    assert len(store.argument_ids()) == 15
    n_obj = sum(len(a["objections"]) for a in raw)
    rels = store.relations("attacks")
    assert len(rels) == n_obj > 0
    assert all(r["dst_kind"] == "premise" for r in rels)
    assert store.ingest(ARGS) == 15  # idempotent
    assert len(store.relations("attacks")) == n_obj
    # metaphysical stored as-is
    row = store.one("SELECT type, type_ext FROM premise WHERE text='Whatever thinks exists.'")
    assert (row["type"], row["type_ext"]) == ("metaphysical", "metaphysical")
    rec = store.latest_reconstruction("cogito", "human")
    assert [p.id for p in rec.reconstruction.premises] == ["P1", "P2"]
    assert store.iso_truth() >= {frozenset(("sorites-heap", "ship-of-theseus-gradual"))}


def test_store_roundtrip(store):
    rid = store.latest_reconstruction("cogito", "human").id
    f = FormalizationX.model_validate(json.loads((config.ROOT / "tests/fixtures/mock_llm/formalize/cogito.json").read_text())[0])
    chk = checks.run_all(f, ["P1", "P2"])
    fid = store.insert_formalization(rid, 0, "ok", f, chk, llm_call_ids=[1, 2])
    rec = store.get_formalization(fid)
    assert rec.check.valid == "valid" and rec.llm_call_ids == [1, 2]
    assert rec.formalization.predicates[0].sense == "think:occurrent"
    assert store.list_formalizations(rid)[0].id == fid


def test_prompts_render():
    sys_, user = prompts.load_split("judge", "v1", reconstruction="[P1] a", verbalization="[C] b")
    assert "fidelity judge" in sys_ and "[C] b" in user
    with pytest.raises(KeyError):
        prompts.render("{{ nope }}")
    for n in ("reconstruct", "formalize", "judge"):
        assert prompts.split(prompts.load(n, "v1"))


def test_mock_returns_trivialized_sample(store):
    llm = MockLLMClient(store)
    good = llm.call(stage="formalize", system="s", user="u", argument_id="cogito", sample_idx=0).data
    triv = llm.call(stage="formalize", system="s", user="u", argument_id="cogito", sample_idx=1).data
    cg, ct = (checks.run_all(FormalizationX.model_validate(d), ["P1", "P2"]) for d in (good, triv))
    assert cg.nontrivial is True and ct.nontrivial is False
    assert not FormalizationX.model_validate(good).slot_errors()
    j = llm.call(stage="judge", system="s", user="u", argument_id="cogito", sample_idx=1).data
    assert JudgeOut.model_validate(j).conclusion_score == 1.0
    assert len(store.llm_calls("formalize")) == 2 and store.llm_calls()[0]["model"] == "mock"


def test_mock_synthesizes_for_every_argument(store):
    llm = MockLLMClient(store)
    for aid in store.argument_ids():
        rec = store.latest_reconstruction(aid, "human").reconstruction
        r = llm.call(stage="reconstruct", system="s", user="u", argument_id=aid).data
        assert len(r["premises"]) == len(rec.premises)
        f = FormalizationX.model_validate(llm.call(stage="formalize", system="s", user="u", argument_id=aid).data)
        if aid != "cogito":
            assert checks.run_all(f, [p.id for p in rec.premises]).parse_ok
    j = llm.call(stage="judge", system="s", user="[P1] x\n[P2] y\n[C] z", argument_id="kalam").data
    assert set(j["scores"]) == {"P1", "P2"}


def test_mock_works_with_key_unset(monkeypatch, store):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    MockLLMClient(store).call(stage="reconstruct", system="s", user="u", argument_id="kalam")
    with pytest.raises(config.ConfigError):
        monkeypatch.setattr(config, "load_env", lambda: None)
        LLMClient(store)


def test_cache_hit_is_free_and_logged_once(store, monkeypatch):
    calls = []

    class Fake(LLMClient):
        def __init__(self, store):  # no SDK / key needed
            self.store, self.run_id = store, None

        def _complete(self, **kw):
            calls.append(kw)
            return json.dumps({"ok": 1}), 10, 5

    c = Fake(store)
    a = c.call(stage="reconstruct", system="s", user="u", schema={"type": "object"}, argument_id="x", temperature=0.7, model="m")
    b = c.call(stage="reconstruct", system="s", user="u", schema={"type": "object"}, argument_id="x", temperature=0.7, model="m")
    assert len(calls) == 1 and not a.cached and b.cached and b.data == {"ok": 1} and a.call_id == b.call_id
    row = store.llm_calls()[0]
    assert row["prompt_hash"] == prompt_hash("s", "u", {"type": "object"}) and row["input_tokens"] == 10 and row["latency_ms"] is not None
    assert "system" in json.loads(row["prompt"]) and json.loads(row["response"]) == {"ok": 1}
    c.call(stage="reconstruct", system="s", user="u", schema={"type": "object"}, temperature=0.7, model="m", sample_idx=1)
    assert len(calls) == 2  # sample_idx is part of the key


def test_error_is_logged(store):
    class Boom(MockLLMClient):
        def _complete(self, **kw):
            raise RuntimeError("429")
    with pytest.raises(RuntimeError):
        Boom(store).call(stage="judge", system="s", user="u")
    assert store.llm_calls()[0]["error"].startswith("RuntimeError")


def test_runner_resume_resets_crashed_jobs(store):
    run = store.new_run(mock=True)
    seen = []
    state = {"crash_on": "b"}

    def stage(ctx, unit):
        if unit.argument_id == state["crash_on"]:
            raise KeyboardInterrupt  # simulated kill: BaseException leaves the job `running`
        if unit.argument_id == "bad":
            raise ValueError("boom")
        seen.append(unit.argument_id)

    r = Runner(store, run, stages={"s": stage})
    with pytest.raises(KeyboardInterrupt):
        r.run("s", ["a", "b", "bad", "c"])
    assert seen == ["a"]
    assert r.status() == {"done": 1, "running": 1}

    state["crash_on"] = None
    s = r.run("s", ["a", "b", "bad", "c"])
    assert s.reset == 1 and seen == ["a", "b", "c"]  # a not re-run
    assert (s.done, s.failed, s.skipped) == (2, 1, 1)
    bad = [j for j in store.jobs(run) if j["argument_id"] == "bad"][0]
    assert bad["status"] == "failed" and "boom" in bad["error"] and bad["finished_at"] and bad["started_at"]
    s2 = r.run("s", ["a", "b", "bad", "c"])
    assert (s2.done, s2.skipped) == (0, 4)  # failed not retried by default
    assert r.run("s", ["bad"], retry_failed=True).failed == 1
    assert r.run("s", ["a"], resume=False).done == 1 and seen.count("a") == 2


def test_runner_candidate_units(store):
    run = store.new_run()
    got = []
    Runner(store, run, stages={"f": lambda ctx, u: got.append((u.argument_id, u.candidate_idx))}).run(
        "f", ["x"], candidate_idxs=[0, 1, 2])
    assert got == [("x", 0), ("x", 1), ("x", 2)]
    with pytest.raises(KeyError):
        Runner(store, run, stages={}).run("nope", ["x"])


@pytest.mark.llm
def test_live_smoke(store):
    config.load_env()
    c = LLMClient(store)
    r = c.call(stage="judge", system="Reply via the tool.", user="Say ok.", argument_id="smoke",
               schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
    assert r.data is not None and r.call_id
