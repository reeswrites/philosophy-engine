"""Stage: select. Z3-side hard filters first (judge can never rescue a trivial candidate), then weighted score."""
from __future__ import annotations

from . import checks, config
from .models_ext import SelectionResultX
from .runner import Ctx, Unit, register
from .stage_common import latest_by_candidate, pick_reconstruction


def _n_preds(form) -> int:
    return len(form.formalization.predicates) if form.formalization else 0


def reject_reasons(form) -> tuple[list[str], bool]:
    """-> (reasons, rejected_as_trivial)."""
    r: list[str] = []
    triv = False
    chk, j = form.check, form.judge
    if form.status == "parse_fail" or form.formalization is None or chk is None or not chk.parse_ok:
        return ["parse_fail" + (f": {chk.parse_errors[:2]}" if chk and chk.parse_errors else "")], False
    if chk.nontrivial is False:
        r.append("trivial: " + "; ".join(chk.trivial_reasons)); triv = True
    if chk.vacuous:
        r.append("vacuous"); triv = True
    if j is None:
        r.append("no judge report")
        return r, triv
    flags = getattr(j, "hard_reject", False)
    if flags:
        r.append(f"judge hard reject: {[x for x in j.flags]}")
        if chk.valid == "valid":
            triv = True
    if j.min_score < config.JUDGE_MIN_SCORE:
        r.append(f"judge min_score {j.min_score:.2f} < {config.JUDGE_MIN_SCORE}")
    if j.mean_score < config.JUDGE_MEAN_SCORE:
        r.append(f"judge mean_score {j.mean_score:.2f} < {config.JUDGE_MEAN_SCORE}")
    if j.conclusion_score < config.JUDGE_CONCLUSION_SCORE:
        r.append(f"judge conclusion_score {j.conclusion_score:.2f} < {config.JUDGE_CONCLUSION_SCORE}")
    return r, triv


def score(form, max_preds: int) -> float:
    w, j, chk = config.SELECT_WEIGHTS, form.judge, form.check
    return (w["mean"] * j.mean_score + w["min"] * j.min_score
            + w["minimal"] * (1.0 if chk.minimal else 0.0)
            + w["simplicity"] * (1 - _n_preds(form) / max_preds)
            + w["decided"] * (1.0 if chk.valid in ("valid", "refuted") else 0.0))


def select_for(store, recon_id: int, run_id: int | None = None) -> SelectionResultX:
    forms = latest_by_candidate(store.list_formalizations(recon_id))
    max_preds = max([_n_preds(f) for f in forms] + [1])
    ranking, survivors, rejected_trivial = [], [], 0
    for f in forms:
        reasons, triv = reject_reasons(f)
        rejected_trivial += triv
        entry = {"formalization_id": f.id, "candidate_idx": f.candidate_idx,
                 "verdict": checks.verdict_of(f.check) if f.check and f.check.parse_ok else None,
                 "rejected_reasons": reasons, "score": None}
        if not reasons:
            entry["score"] = round(score(f, max_preds), 6)
            survivors.append((f, entry))
        ranking.append(entry)
    ranking.sort(key=lambda e: (e["score"] is None, -(e["score"] or 0), e["candidate_idx"]))
    chosen = None
    contested = False
    if survivors:
        survivors.sort(key=lambda t: (-t[1]["score"], len(t[0].check.redundant_premises), t[0].candidate_idx))
        chosen = survivors[0][0]
        contested = len({e["verdict"] for _, e in survivors}) > 1
        verdict = checks.verdict_of(chosen.check)
    else:
        verdict = "open"
        if not forms:
            ranking = [{"formalization_id": None, "rejected_reasons": ["no candidates"], "score": None}]
    sel = SelectionResultX(reconstruction_id=recon_id, chosen_formalization_id=chosen.id if chosen else None,
                           verdict=verdict, ranking=ranking, rejected_trivial=rejected_trivial, contested=contested)
    store.insert_selection(sel, run_id)
    if contested:
        store.insert_review("selection", str(recon_id), "contested: surviving candidates disagree on verdict")
    return sel


@register("select")
def select(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    select_for(ctx.store, rec_row.id, ctx.run_id)
