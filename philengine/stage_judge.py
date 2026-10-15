"""Stage: judge. Verbalize mechanically (verbalize.py), then one judge call; build a JudgeReportX."""
from __future__ import annotations

from . import config, prompts
from .models_ext import HARD_REJECT_FLAGS, JudgeOut, JudgeReportX
from .runner import Ctx, Unit, register
from .stage_common import (feedback, format_reconstruction, latest_by_candidate, n_candidates, opt,
                           pick_reconstruction, validation_errors)
from .verbalize import VerbalizeError, verbalization_text, verbalize


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def build_report(out: JudgeOut, bt: dict[str, str], verbalization: str) -> JudgeReportX:
    """min/mean are over all items (premises + conclusion); a premise the judge skipped scores 0."""
    prem_ids = [k for k in bt if k != "C"]
    scores = {k: _clamp(out.scores.get(k, 0.0)) for k in prem_ids}
    concl = _clamp(out.conclusion_score)
    allv = [*scores.values(), concl]
    flags = list(dict.fromkeys(out.flags))
    return JudgeReportX(
        back_translations=bt, scores=scores, conclusion_score=concl,
        min_score=min(allv), mean_score=sum(allv) / len(allv), flags=flags,
        per_item_comments=out.per_item_comments,
        hard_reject=any(x in HARD_REJECT_FLAGS for x in flags), verbalization=verbalization)


def judge_one(ctx: Ctx, argument_id: str, rec_row, form) -> None:
    st = ctx.store
    if form.status != "ok" or form.formalization is None:
        return  # nothing to judge
    try:
        bt = verbalize(form.formalization)
        vtext = verbalization_text(form.formalization, show_symbols=True)
    except VerbalizeError as e:
        st.update_formalization(form.id, status="judge_fail")
        raise
    prem_text, concl = format_reconstruction(rec_row.reconstruction)
    system, user = prompts.load_split("judge", "v1", reconstruction=f"{prem_text}\n[C] {concl}", verbalization=vtext)
    schema = JudgeOut.model_json_schema()
    ids, errs, out = list(form.llm_call_ids), [], None
    for attempt in range(2):
        u = user if attempt == 0 else user + "\n\n" + feedback(errs)
        res = ctx.llm.call(stage="judge", system=system, user=u, schema=schema, argument_id=argument_id,
                           candidate_idx=form.candidate_idx, sample_idx=form.candidate_idx,
                           temperature=opt(ctx, "temperature_judge", config.TEMP_JUDGE),
                           model=opt(ctx, "model_judge", None), prompt_name="judge.v1")
        ids.append(res.call_id)
        out, errs = validation_errors(JudgeOut, res.data)
        if out is not None:
            break
    if out is None:
        st.update_formalization(form.id, status="judge_fail", llm_call_ids=ids)
        return
    st.update_formalization(form.id, judge=build_report(out, bt, vtext), llm_call_ids=ids)


@register("judge")
def judge(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    forms = latest_by_candidate(ctx.store.list_formalizations(rec_row.id))
    if unit.candidate_idx >= 0:
        forms = [f for f in forms if f.candidate_idx == unit.candidate_idx]
    for f in forms:
        judge_one(ctx, unit.argument_id, rec_row, f)
