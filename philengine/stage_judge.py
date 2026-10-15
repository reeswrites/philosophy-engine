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


def build_report(outs: JudgeOut | list[JudgeOut], bt: dict[str, str], verbalization: str,
                 call_ids: list[int] | None = None) -> JudgeReportX:
    """Average each item's score over the judge samples, then min/mean over all items (premises + conclusion);
    a premise a sample skipped scores 0 in it. hard_reject only if EVERY sample raised a hard-reject flag."""
    outs = [outs] if isinstance(outs, JudgeOut) else list(outs)
    n = len(outs)
    prem_ids = [k for k in bt if k != "C"]
    scores = {k: sum(_clamp(o.scores.get(k, 0.0)) for o in outs) / n for k in prem_ids}
    concl = sum(_clamp(o.conclusion_score) for o in outs) / n
    allv = [*scores.values(), concl]
    flags = list(dict.fromkeys(x for o in outs for x in o.flags))
    comments: dict[str, str] = {}
    for o in outs:
        for k, v in o.per_item_comments.items():
            comments.setdefault(k, v)
    hard = all(any(x in HARD_REJECT_FLAGS for x in o.flags) for o in outs)
    return JudgeReportX(
        back_translations=bt, scores=scores, conclusion_score=concl,
        min_score=min(allv), mean_score=sum(allv) / len(allv), flags=flags,
        per_item_comments=comments, hard_reject=hard, verbalization=verbalization,
        n_samples=n, judge_call_ids=list(call_ids or []), sample_flags=[list(o.flags) for o in outs])


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
    ids, outs, judge_ids = list(form.llm_call_ids), [], []
    for sample in range(int(opt(ctx, "judge_samples", config.JUDGE_SAMPLES))):
        errs, out = [], None
        for attempt in range(2):
            u = user if attempt == 0 else user + "\n\n" + feedback(errs)
            res = ctx.llm.call(stage="judge", system=system, user=u, schema=schema, argument_id=argument_id,
                               candidate_idx=form.candidate_idx, sample_idx=sample,
                               temperature=opt(ctx, "temperature_judge", config.TEMP_JUDGE),
                               model=opt(ctx, "model_judge", None), prompt_name="judge.v1")
            ids.append(res.call_id)
            out, errs = validation_errors(JudgeOut, res.data)
            if out is not None:
                judge_ids.append(res.call_id)
                break
        if out is not None:
            outs.append(out)
    if not outs:
        st.update_formalization(form.id, status="judge_fail", llm_call_ids=ids)
        return
    st.update_formalization(form.id, judge=build_report(outs, bt, vtext, judge_ids), llm_call_ids=ids)


@register("judge")
def judge(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    forms = latest_by_candidate(ctx.store.list_formalizations(rec_row.id))
    if unit.candidate_idx >= 0:
        forms = [f for f in forms if f.candidate_idx == unit.candidate_idx]
    for f in forms:
        judge_one(ctx, unit.argument_id, rec_row, f)
