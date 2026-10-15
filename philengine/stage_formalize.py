"""Stage: formalize. N independent candidates per argument (unit.candidate_idx >= 0 = just that one)."""
from __future__ import annotations

from . import checks, config, fol, prompts, senses
from .models_ext import FormalizationX
from .runner import Ctx, Unit, register
from .stage_common import feedback, n_candidates, opt, pick_reconstruction, validation_errors


def strategy_hint(candidate_idx: int, n_premises: int = 3) -> str:
    """Deterministic per-candidate prompt hint (temperature is no longer sent, so this is what diversifies candidates).
    Round 3: hints are structural bands over the predicate count (filled from the premise count P), not stylistic
    preferences, so candidates cannot all satisfy every hint with the same formalization."""
    h = config.STRATEGY_HINTS
    P = max(1, int(n_premises))
    k = config.STRATEGY_BAND_SLACK
    return h[candidate_idx % len(h)].format(hi_lean=P + k - 1, lo_rich=P + k, lo_rel=P, hi_rel=P + k + 1)


def do_not_reuse_block(forms) -> str:
    """Round 3: the predicate sets (name/arity) and formula shapes earlier candidates of this argument already used,
    as a "do not reuse" instruction. '' when there is none. `forms` = earlier candidates (parsed)."""
    from .stage_common import pred_set
    seen, lines = set(), []
    for f in forms:
        if f.formalization is None:
            continue
        ps = pred_set(f.formalization)
        if ps in seen:
            continue
        seen.add(ps)
        names = ", ".join(f"{n}/{a}" for n, a in sorted(ps))
        lines.append(f"- candidate {f.candidate_idx}: {{{names}}}")
    if not lines:
        return ""
    return ("DO NOT REUSE: earlier candidates for this argument already used exactly these predicate sets "
            "(name/arity). Produce a materially different formalization: change at least one predicate's arity, "
            "split or merge at least one concept, or move a typing condition between a sort and a unary predicate. "
            "Do not return the same predicate set under new names.\n" + "\n".join(lines))


REGISTRY_INSTRUCTION = (
    "SENSE REGISTRY for this run (concepts already declared in other arguments: label | sense | gloss). "
    "Reuse an existing (label, sense, gloss) exactly when the meaning you need matches it. Only coin a new sense "
    "when the meaning genuinely differs, and then name it so it contrasts with the existing ones (same label family, "
    "different sense id and a different, specific gloss). Do not coin a near-duplicate under a new spelling.")


def sense_registry_block(st, run_id, limit: int | None = None) -> str:
    """Prompt block listing this run's (label, sense, gloss) entries so far, most-used first, capped (~60). '' if empty."""
    rows = st.sense_registry(run_id, int(limit or config.SENSE_REGISTRY_MAX))
    if not rows:
        return ""
    lines = [f"- {r['label']} | {r['sense']} | {senses.norm_gloss(r['gloss'] or '')}" for r in rows]
    return REGISTRY_INSTRUCTION + "\n" + "\n".join(lines)


def formalize_one(ctx: Ctx, argument_id: str, rec_row, candidate_idx: int) -> int:
    st = ctx.store
    ids = [p.id for p in rec_row.reconstruction.premises]
    from .stage_common import format_reconstruction
    prem_text, concl = format_reconstruction(rec_row.reconstruction)
    schema = FormalizationX.model_json_schema()
    model = opt(ctx, "model_reason", None)
    temp = opt(ctx, "temperature_formalize", config.TEMP_FORMALIZE)
    hint = strategy_hint(candidate_idx, len(ids))
    from .stage_common import latest_by_candidate
    earlier = [f for f in latest_by_candidate(st.list_formalizations(rec_row.id))
               if f.candidate_idx < candidate_idx and f.formalization is not None]
    avoid = do_not_reuse_block(earlier)
    call_ids: list[int] = []
    f, errs, retry = None, [], ""
    for attempt in range(2):
        system, user = prompts.load_split("formalize", "v1", reconstruction=prem_text, conclusion=concl,
                                          retry_feedback=retry)
        user = f"{user}\n\nStrategy hint for this candidate (a structural constraint; never override the rules above): {hint}"
        if avoid:
            user = f"{user}\n\n{avoid}"
        registry = sense_registry_block(st, ctx.run_id)
        if registry:
            user = f"{user}\n\n{registry}"
        res = ctx.llm.call(stage="formalize", system=system, user=user, schema=schema,
                           argument_id=argument_id, candidate_idx=candidate_idx, sample_idx=candidate_idx,
                           temperature=temp, model=model, prompt_name="formalize.v1")
        call_ids.append(res.call_id)
        f, errs = validation_errors(FormalizationX, res.data)
        if f is not None:
            errs = f.slot_errors()
            _, verrs = fol.validate(f, ids)
            errs = errs + verrs
            if not verrs:
                errs = errs + senses.gloss_collision_errors(f)
        if not errs:
            break
        retry = feedback(errs)
    if f is None:  # never parsed into the model
        return st.insert_formalization(rec_row.id, candidate_idx, "parse_fail", None, None, None, call_ids, ctx.run_id, hint)
    check = checks.run_all(f, ids, timeout_ms=opt(ctx, "z3_timeout_ms", config.Z3_TIMEOUT_MS))
    if errs:  # slot/validation problems survived the retry
        if check.parse_ok:  # slot-only problems: record them on the report
            check = check.model_copy(update={"parse_ok": False, "parse_errors": errs})
        return st.insert_formalization(rec_row.id, candidate_idx, "parse_fail", f, check, None, call_ids, ctx.run_id, hint)
    hints = senses.mismatch_hints(f, rec_row.reconstruction)
    if hints:
        check = check.model_copy(update={"sense_mismatch_hint": hints})
        for h in hints:
            st.insert_review("formalization", f"{argument_id}:{candidate_idx}", f"sense_mismatch_hint: {h}", ctx.run_id)
    for w in f.gloss_warnings():
        st.insert_review("formalization", f"{argument_id}:{candidate_idx}", f"gloss warning: {w}", ctx.run_id)
    for p in f.predicates:
        st.upsert_concept(label=p.name, gloss=p.gloss, sense=p.sense, first_seen=argument_id, run_id=ctx.run_id)
    return st.insert_formalization(rec_row.id, candidate_idx, "ok", f, check, None, call_ids, ctx.run_id, hint)


@register("formalize")
def formalize(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    idxs = [unit.candidate_idx] if unit.candidate_idx >= 0 else list(range(n_candidates(ctx)))
    for ci in idxs:
        formalize_one(ctx, unit.argument_id, rec_row, ci)
