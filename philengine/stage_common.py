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


def fingerprint(f) -> str:
    """Content identity of a formalization: sorted normalized premise formulas, the normalized conclusion, and the
    declared (name, arity) pairs. Two candidates with equal fingerprints would get byte-identical judge prompts."""
    import hashlib
    from . import fol
    from . import sexpr as sx
    parts = []
    for it in f.premises:
        try:
            parts.append(f"{it.premise_id}={fol.normalized_text(sx.parse(it.sexpr))}")
        except Exception:
            parts.append(f"{it.premise_id}={it.sexpr.strip()}")
    try:
        parts.append(f"C={fol.normalized_text(sx.parse(f.conclusion.sexpr))}")
    except Exception:
        parts.append(f"C={f.conclusion.sexpr.strip()}")
    parts = sorted(parts) + sorted(f"{p.name}/{len(p.arg_sorts)}" for p in f.predicates)
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def pred_set(f) -> frozenset:
    return frozenset((p.name, len(p.arg_sorts)) for p in f.predicates)


def diversity(forms) -> dict:
    """Round-3 diversity metric over an argument's parsed candidates: distinct fingerprints and distinct predicate
    sets out of n. ratio = distinct / n (1.0 = every candidate different; 1/n = all byte-identical)."""
    fs = [f.formalization for f in forms if f.formalization is not None]
    n = len(fs)
    d = len({fingerprint(f) for f in fs})
    return {"n": n, "distinct": d, "distinct_pred_sets": len({pred_set(f) for f in fs}),
            "ratio": round(d / n, 3) if n else None}


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
