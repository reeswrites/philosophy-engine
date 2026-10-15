"""LLM layer: LLMClient (Anthropic, forced tool-use JSON) and MockLLMClient (same interface).

Every call is written to `llm_call` before it returns (also on error). The real client has a response
cache keyed by (prompt_hash, model, sample_idx, temperature): a hit returns the earlier response and
writes NO new row (so row count == real calls). Mock calls are always logged, never cached.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .models_ext import FormalizationX, ReconstructionX
from .store import Store

MOCK_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mock_llm"
TOOL_NAME = "emit"


@dataclass
class LLMResult:
    data: dict | None  # parsed structured output (None if the model produced none / invalid)
    text: str  # raw response text (JSON for tool-use)
    call_id: int  # llm_call.id (the original row for cache hits)
    model: str
    cached: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


def prompt_hash(system: str, user: str, schema: dict | None = None) -> str:
    h = hashlib.sha256()
    for part in (system, user, json.dumps(schema, sort_keys=True) if schema else ""):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


def cache_key(phash: str, model: str, sample_idx: int, temperature: float) -> str:
    return hashlib.sha256(f"{phash}|{model}|{sample_idx}|{temperature}".encode()).hexdigest()


def default_model(stage: str) -> str:
    return config.MODEL_JUDGE if stage == "judge" else config.MODEL_REASON


class _Base:
    def __init__(self, store: Store, run_id: int | None = None):
        self.store = store
        self.run_id = run_id

    def call(self, *, stage: str, system: str, user: str, schema: dict | None = None,
             argument_id: str | None = None, candidate_idx: int | None = None, sample_idx: int = 0,
             temperature: float = 0.0, model: str | None = None, prompt_name: str | None = None,
             max_tokens: int = 8192) -> LLMResult:
        model = model or self.model_for(stage)
        phash = prompt_hash(system, user, schema)
        key = cache_key(phash, model, sample_idx, temperature)
        meta = dict(run_id=self.run_id, stage=stage, argument_id=argument_id, candidate_idx=candidate_idx,
                    sample_idx=sample_idx, model=model, temperature=temperature, prompt_name=prompt_name,
                    prompt_hash=phash, cache_key=key,
                    prompt=json.dumps({"system": system, "user": user, "schema": schema}))
        if self.use_cache:
            hit = self.store.find_cached_call(key)
            if hit:
                text = hit["response"]
                return LLMResult(_loads(text), text, hit["id"], model, cached=True,
                                 input_tokens=hit["input_tokens"], output_tokens=hit["output_tokens"],
                                 latency_ms=hit["latency_ms"] or 0)
        t0 = time.monotonic()
        try:
            out = self._complete(stage=stage, system=system, user=user, schema=schema, model=model,
                                             temperature=temperature, sample_idx=sample_idx,
                                             argument_id=argument_id, max_tokens=max_tokens)
            text, tin, tout = out[:3]
            stop = out[3] if len(out) > 3 else None
        except Exception as e:
            self.store.insert_llm_call(**meta, error=f"{type(e).__name__}: {e}",
                                       latency_ms=int((time.monotonic() - t0) * 1000))
            raise
        ms = int((time.monotonic() - t0) * 1000)
        cid = self.store.insert_llm_call(**meta, response=text, input_tokens=tin, output_tokens=tout, latency_ms=ms,
                                      stop_reason=stop)
        return LLMResult(_loads(text), text, cid, model, False, tin, tout, ms)

    use_cache = False

    def model_for(self, stage: str) -> str:
        return default_model(stage)

    def _complete(self, **kw):  # -> (text, in_tokens, out_tokens[, stop_reason])
        raise NotImplementedError


def _loads(text: str | None) -> dict | None:
    try:
        v = json.loads(text) if text else None
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


def _closed_schema(schema: dict) -> dict | None:
    """Deep-copy a pydantic JSON schema and set additionalProperties=false on every object node
    (required by the structured-outputs API). Returns None if the schema has an open dict field
    (additionalProperties given as a sub-schema), which structured outputs cannot express."""
    import copy

    class _Open(Exception):
        pass

    def walk(n):
        if isinstance(n, dict):
            if isinstance(n.get("additionalProperties"), dict):
                raise _Open()
            if n.get("type") == "object" or "properties" in n:
                n.setdefault("additionalProperties", False)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    out = copy.deepcopy(schema)
    try:
        walk(out)
    except _Open:
        return None
    return out


class LLMClient(_Base):
    """Anthropic SDK; structured output via output_config.format (json_schema = `schema`)."""
    use_cache = True

    def __init__(self, store: Store, run_id: int | None = None, api_key: str | None = None):
        super().__init__(store, run_id)
        config.load_env()
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise config.ConfigError("ANTHROPIC_API_KEY not set (put it in .env or export it); use MockLLMClient / --mock")
        import anthropic
        self._client = anthropic.Anthropic(api_key=key, max_retries=3)

    def _complete(self, *, system, user, schema, model, temperature, max_tokens, **_):
        # anthropic>=1.0 removed the `temperature` kwarg (and Sonnet/Haiku 5.5 reject non-default values),
        # and Sonnet 5.5 returns 400 for forced tool_choice; structured outputs (output_config.format) are
        # the documented replacement for "forced tool just to get JSON". `temperature` is still recorded
        # in the llm_call row / cache key for provenance but is not sent.
        kw: dict = dict(model=model, max_tokens=max_tokens, system=system,
                        messages=[{"role": "user", "content": user}])
        if schema:
            closed = _closed_schema(schema)
            if closed is not None:
                kw["output_config"] = {"format": {"type": "json_schema", "schema": closed}}
            else:
                # open dict fields (e.g. JudgeOut.scores) cannot be expressed as structured output;
                # fall back to a forced tool (accepted by Haiku 5.5, which the judge uses).
                kw["tools"] = [{"name": TOOL_NAME, "description": "Emit the structured answer.",
                                "input_schema": schema}]
                kw["tool_choice"] = {"type": "tool", "name": TOOL_NAME}
        r = self._client.messages.create(**kw)
        text = ""
        for b in r.content:
            if b.type == "tool_use":
                text = json.dumps(b.input)
                break
            if b.type == "text":
                text += b.text
        return text, r.usage.input_tokens, r.usage.output_tokens, getattr(r, "stop_reason", None)


# ------------------------------------------------------------------ mock
_LINE_ID = re.compile(r"^\[(P\d+|C)\]", re.M)


class MockLLMClient(_Base):
    """Canned responses from tests/fixtures/mock_llm/<stage>/<argument_id>.json (a JSON list of samples,
    indexed by sample_idx modulo length). Missing file => synthesize from the human reconstruction in
    arguments.json (reconstruct: the human one; formalize: one propositional atom per premise, so
    mostly `refuted`; judge: 0.9 everywhere, ids read from `[P1]`-style lines in the user prompt)."""

    def __init__(self, store: Store | None = None, run_id: int | None = None, fixtures_dir: Path | None = None):
        super().__init__(store or Store(":memory:"), run_id)
        self.dir = fixtures_dir or MOCK_DIR
        self.calls = 0

    def model_for(self, stage: str) -> str:
        return "mock"

    def _complete(self, *, stage, user, sample_idx, argument_id, **_):
        self.calls += 1
        data = self._canned(stage, argument_id, sample_idx)
        if data is None:
            data = self._synthesize(stage, argument_id, user)
        return json.dumps(data), 0, 0

    def _canned(self, stage, argument_id, sample_idx):
        p = self.dir / stage / f"{argument_id}.json"
        if argument_id and p.is_file():
            samples = json.loads(p.read_text())
            return samples[sample_idx % len(samples)]
        return None

    def _human(self, argument_id) -> dict:
        row = self.store.one("SELECT json FROM argument WHERE id=?", (argument_id,))
        if row:
            return json.loads(row["json"])["reconstruction"]
        for a in json.loads((config.data_dir() / "phase0" / "arguments.json").read_text()):
            if a["id"] == argument_id:
                return a["reconstruction"]
        raise KeyError(f"mock: no human reconstruction for {argument_id!r}")

    def _synthesize(self, stage, argument_id, user):
        if stage == "reconstruct":
            r = ReconstructionX.model_validate(self._human(argument_id))
            return {**r.model_dump(), "notes": "mock: human reconstruction echoed"}
        if stage == "formalize":
            r = self._human(argument_id)
            preds = [{"name": f"p{i}", "arg_sorts": [], "gloss": p["text"], "sense": f"mock:p{i}"}
                     for i, p in enumerate(r["premises"], 1)]
            preds.append({"name": "c", "arg_sorts": [], "gloss": r["conclusion"], "sense": "mock:c"})
            f = FormalizationX(
                predicates=preds,
                premises=[{"premise_id": p["id"], "sexpr": f"p{i}"} for i, p in enumerate(r["premises"], 1)],
                conclusion={"premise_id": "C", "sexpr": "c"},
                notes="mock: each claim as an opaque proposition")
            return f.model_dump()
        if stage == "judge":
            ids = _LINE_ID.findall(user) or ["C"]
            return {"scores": {i: 0.9 for i in ids if i != "C"}, "conclusion_score": 0.9, "flags": [],
                    "per_item_comments": {}}
        raise KeyError(f"mock: no synthesizer for stage {stage!r}")
