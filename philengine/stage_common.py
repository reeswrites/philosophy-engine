"""Helpers shared by the stage modules."""
from __future__ import annotations

from . import config
from .runner import Ctx
from .schemas import FormalizationRecord, Reconstruction, ReconstructionRecord


def opt(ctx: Ctx, key: str, default):
    v = ctx.options.get(key)
    return default if v is None else v


def n_candidates(ctx: Ctx) -> int:
    return int(opt(ctx, "n_candidates", config.N_CANDIDATES))


def pick_reconstruction(ctx: Ctx, argument_id: str) -> ReconstructionRecord:
    """The reconstruction the formalize/judge/select stages work on: latest LLM one, unless
    options['from_human'] (or no LLM one exists), then the human one."""
    st = ctx.store
    rec = None
    if not ctx.options.get("from_human"):
        rec = st.latest_reconstruction(argument_id, "llm")
    rec = rec or st.latest_reconstruction(argument_id, "human")
    if rec is None:
        raise LookupError(f"no reconstruction for {argument_id!r}; run ingest/reconstruct first")
    return rec


def format_reconstruction(rec: Reconstruction) -> tuple[str, str]:
    """-> (numbered `[P1] text` lines with implicit marked, conclusion text)."""
    lines = [f"[{p.id}] {p.text}" + (" (implicit premise)" if p.implicit else "") for p in rec.premises]
    return "\n".join(lines), rec.conclusion


def latest_by_candidate(forms: list[FormalizationRecord]) -> list[FormalizationRecord]:
    best: dict[int, FormalizationRecord] = {}
    for f in forms:
        if f.candidate_idx not in best or f.id > best[f.candidate_idx].id:
            best[f.candidate_idx] = f
    return [best[k] for k in sorted(best)]


def validation_errors(model_cls, data) -> tuple[object | None, list[str]]:
    """Parse LLM structured output into model_cls -> (obj, errors)."""
    if data is None:
        return None, ["no valid JSON object returned; reply only by calling the tool"]
    try:
        return model_cls.model_validate(data), []
    except Exception as e:  # pydantic.ValidationError
        return None, [f"output does not match the schema: {e}"]


def feedback(errors: list[str]) -> str:
    return ("Your previous answer was rejected. Fix every problem below and answer again in full:\n"
            + "\n".join(f"- {e}" for e in errors))
