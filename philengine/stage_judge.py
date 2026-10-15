"""Stage: judge. Verbalize mechanically (verbalize.py), then one judge call; build a JudgeReportX."""
from __future__ import annotations

from . import config, prompts
from .models_ext import HARD_REJECT_FLAGS, JudgeOut, JudgeReportX, soft_review_flags
from .runner import Ctx, Unit, register
from .stage_common import (feedback, fingerprint, format_reconstruction, latest_by_candidate, n_candidates, opt,
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


def duplicate_report(st, rec_id: int, form) -> JudgeReportX | None:
    """Round 3 dedupe: if an EARLIER candidate (lower idx) of the same reconstruction is content-identical
    (stage_common.fingerprint) and already judged, return a copy of its report tagged duplicate_of_candidate."""
    fp = fingerprint(form.formalization)
    for other in latest_by_candidate(st.list_formalizations(rec_id)):
        if other.candidate_idx >= form.candidate_idx or other.formalization is None or other.judge is None:
            continue
        if fingerprint(other.formalization) == fp:
            j = JudgeReportX.model_validate(other.judge.model_dump())
            src = j.duplicate_of_candidate if j.duplicate_of_candidate is not None else other.candidate_idx
            return j.model_copy(update={"duplicate_of_candidate": src, "judge_call_ids": []})
    return None


def record_soft_flags(st, argument_id: str, form, report: JudgeReportX, run_id) -> None:
    """reconstruction_gap (and the legacy missing_implicit_premise) route to review on the RECONSTRUCTION; they never
    reject the formalization."""
    for flag in soft_review_flags(report):
        comment = "; ".join(f"{k}: {v}" for k, v in report.per_item_comments.items())[:300]
        st.insert_review("reconstruction", argument_id, f"{flag} (candidate {form.candidate_idx}): {comment or 'no comment'}", run_id)


def judge_one(ctx: Ctx, argument_id: str, rec_row, form) -> None:
    st = ctx.store
    if form.status != "ok" or form.formalization is None:
        return  # nothing to judge
    dup = duplicate_report(st, rec_row.id, form)
    if dup is not None:
        st.update_formalization(form.id, judge=dup)
        return
    try:
        bt = verbalize(form.formalization)
        vtext = verbalization_text(form.formalization, show_symbols=True)
    except VerbalizeError as e:
        st.update_formalization(form.id, status="judge_fail")
        raise
    prem_text, concl = format_reconstruction(rec_row.reconstruction)
    system, user = prompts.load_split("judge", "v1", reconstruction=f"{prem_text}\n[C] {concl}", verbalization=vtext,
                                      formalizer_notes=(form.formalization.notes or "").strip() or "(none)")
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
    report = build_report(outs, bt, vtext, judge_ids)
    st.update_formalization(form.id, judge=report, llm_call_ids=ids)
    record_soft_flags(st, argument_id, form, report, ctx.run_id)


@register("judge")
def judge(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    forms = latest_by_candidate(ctx.store.list_formalizations(rec_row.id))
    if unit.candidate_idx >= 0:
        forms = [f for f in forms if f.candidate_idx == unit.candidate_idx]
    for f in forms:
        judge_one(ctx, unit.argument_id, rec_row, f)
