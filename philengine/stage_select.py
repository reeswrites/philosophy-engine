"""Stage: select. Z3-side hard filters first (judge can never rescue a trivial candidate), then weighted score."""
from __future__ import annotations

from . import checks, config
from .models_ext import SelectionResultX
from .runner import Ctx, Unit, register
from .stage_common import latest_by_candidate, pick_reconstruction


def _n_preds(form) -> int:
    return len(form.formalization.predicates) if form.formalization else 0


INCONSISTENT_REASON = "premises inconsistent"


def inconsistency_allowed(forms, expected: str | None) -> bool:
    """Inconsistent candidates are a finding, not vacuity, when the human reconstruction expects `inconsistent`
    or >= 2 candidates agree that the premises are unsat."""
    n = sum(1 for f in forms if f.check is not None and f.check.parse_ok and f.check.consistent == "unsat")
    return n >= 1 and (expected == "inconsistent" or n >= 2)


def reject_reasons(form, allow_inconsistent: bool = False) -> tuple[list[str], bool]:
    """-> (reasons, rejected_as_trivial). The flag is derived from the CHECKER only (nontrivial is False /
    vacuous); judge hard rejects are reported in `reasons` and counted separately (rejected_judge).
    With allow_inconsistent, an unsat-premises candidate is not trivial/vacuous on that ground alone."""
    r: list[str] = []
    triv = False
    chk, j = form.check, form.judge
    if form.status == "parse_fail" or form.formalization is None or chk is None or not chk.parse_ok:
        return ["parse_fail" + (f": {chk.parse_errors[:2]}" if chk and chk.parse_errors else "")], False
    incons_ok = allow_inconsistent and chk.consistent == "unsat"
    reasons = [x for x in chk.trivial_reasons if not (incons_ok and x.startswith(INCONSISTENT_REASON))]
    if chk.nontrivial is False and reasons:
        r.append("trivial: " + "; ".join(reasons)); triv = True
    taut = any(x.startswith("C is a tautology") for x in chk.trivial_reasons)
    if chk.vacuous and not (incons_ok and not taut):
        r.append("vacuous"); triv = True
    if j is None:
        r.append("no judge report")
        return r, triv
    flags = getattr(j, "hard_reject", False)
    if flags:
        r.append(f"judge hard reject: {[x for x in j.flags]}")
    if j.min_score < config.JUDGE_MIN_SCORE:
        r.append(f"judge min_score {j.min_score:.2f} < {config.JUDGE_MIN_SCORE}")
    if j.mean_score < config.JUDGE_MEAN_SCORE:
        r.append(f"judge mean_score {j.mean_score:.2f} < {config.JUDGE_MEAN_SCORE}")
    if j.conclusion_score < config.JUDGE_CONCLUSION_SCORE:
        r.append(f"judge conclusion_score {j.conclusion_score:.2f} < {config.JUDGE_CONCLUSION_SCORE}")
    return r, triv


def has_unknown_probe(chk) -> bool:
    """True if any z3 probe returned unknown (minimal is also None for refuted candidates; that is NOT unknown)."""
    return bool(chk.unknown_probes) or chk.nontrivial is None


def biconditional_penalties(form, rec) -> tuple[list[str], list[str]]:
    """-> (penalized premise ids, notes). A suspect iff premise (check.suspect_biconditional) is penalized when it is
    implicit in the reconstruction OR not typed definitional; explicit + definitional only yields a note."""
    chk = form.check
    sus = list(chk.suspect_biconditional) if chk else []
    by_id = {p.id: p for p in rec.premises} if rec else {}
    pen, notes = [], []
    for pid in sus:
        p = by_id.get(pid)
        if p is None or p.implicit or p.type != "definitional":
            pen.append(pid)
        else:
            notes.append(f"{pid}: explicit definitional biconditional carries the conclusion (accepted as a definitional bridge)")
    return pen, notes


def score(form, max_preds: int, penalized: bool = False, orphan: bool = False) -> float:
    w, j, chk = config.SELECT_WEIGHTS, form.judge, form.check
    # NOTE bias: `minimal` is only ever True for valid candidates (None when refuted), so it mildly favours valid.
    # `decided` is symmetric: valid and refuted both count, open (z3 unknown / inconsistent-unknown) does not.
    sc = (w["mean"] * j.mean_score + w["min"] * j.min_score
          + w["minimal"] * (1.0 if chk.minimal else 0.0)
          + w["simplicity"] * (1 - _n_preds(form) / max_preds)
          + w["decided"] * (1.0 if checks.verdict_of(chk) in ("valid", "refuted", "inconsistent") else 0.0))
    sc -= config.UNKNOWN_PROBE_PENALTY if has_unknown_probe(chk) else 0.0
    sc -= config.ORPHAN_CONCLUSION_PENALTY if orphan else 0.0
    return sc - (config.SUSPECT_BICONDITIONAL_PENALTY if penalized else 0.0)


def select_for(store, recon_id: int, run_id: int | None = None) -> SelectionResultX:
    forms = latest_by_candidate(store.list_formalizations(recon_id))
    max_preds = max([_n_preds(f) for f in forms] + [1])
    ranking, survivors, rejected_trivial, rejected_judge = [], [], 0, 0
    unknown_cands = []
    rec = store.get_reconstruction(recon_id).reconstruction
    bic_reviews, orphan_reviews = [], []
    row = store.one("SELECT a.expected_verdict e FROM reconstruction r JOIN argument a ON a.id=r.argument_id WHERE r.id=?",
                    (recon_id,))
    allow_incons = inconsistency_allowed(forms, row["e"] if row else None)
    for f in forms:
        reasons, triv = reject_reasons(f, allow_incons)
        rejected_trivial += triv
        rejected_judge += any(r.startswith("judge hard reject") for r in reasons)
        if f.check is not None and f.check.parse_ok and has_unknown_probe(f.check):
            unknown_cands.append((f.candidate_idx, f.check.unknown_probes))
        entry = {"formalization_id": f.id, "candidate_idx": f.candidate_idx,
                 "verdict": checks.verdict_of(f.check) if f.check and f.check.parse_ok else None,
                 "rejected_reasons": reasons, "score": None}
        pen, notes = biconditional_penalties(f, rec)
        if notes:
            entry["notes"] = notes
        if pen:
            entry["notes"] = [*entry.get("notes", []), f"suspect biconditional penalty {config.SUSPECT_BICONDITIONAL_PENALTY} on {pen}"]
            bic_reviews.append((f.candidate_idx, pen))
        orph = list(f.check.orphan_conclusion_predicate) if f.check else []
        if orph:
            entry["flags"] = ["orphan_conclusion_predicate"]
            entry["notes"] = [*entry.get("notes", []), f"orphan_conclusion_predicate penalty {config.ORPHAN_CONCLUSION_PENALTY} on {orph}"]
            orphan_reviews.append((f.candidate_idx, orph))
        if not reasons:
            entry["score"] = round(score(f, max_preds, bool(pen), bool(orph)), 6)
            survivors.append((f, entry))
        ranking.append(entry)
    ranking.sort(key=lambda e: (e["score"] is None, -(e["score"] or 0), e["candidate_idx"]))
    chosen = None
    contested = False
    if survivors:
        survivors.sort(key=lambda t: (-t[1]["score"], len(t[0].check.redundant_premises), t[0].candidate_idx))
        chosen = survivors[0][0]
        verdict = checks.verdict_of(chosen.check)
    else:
        verdict = "open"
        if not forms:
            ranking = [{"formalization_id": None, "rejected_reasons": ["no candidates"], "score": None}]
    # contested over ALL parsed candidates (a rejected candidate with a different verdict still matters)
    contested = len({e["verdict"] for e in ranking if e.get("verdict")}) > 1
    sel = SelectionResultX(reconstruction_id=recon_id, chosen_formalization_id=chosen.id if chosen else None,
                           verdict=verdict, ranking=ranking, rejected_trivial=rejected_trivial, rejected_judge=rejected_judge, contested=contested)
    store.insert_selection(sel, run_id)
    if contested:
        store.insert_review("selection", str(recon_id), "contested: parsed candidates (survivors and rejected) disagree on verdict", run_id)
    for idx, orph in orphan_reviews:
        store.insert_review("selection", str(recon_id),
                            f"orphan_conclusion_predicate: candidate {idx} {orph} appear in C but in no premise", run_id)
    for idx, pen in bic_reviews:
        store.insert_review("selection", str(recon_id),
                            f"conclusion via implicit/non-definitional biconditional: candidate {idx} {pen}", run_id)
    for idx, probes in unknown_cands:
        store.insert_review("selection", str(recon_id), f"unknown probe: candidate {idx} {probes or ['nontrivial']}", run_id)
    return sel


@register("select")
def select(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    select_for(ctx.store, rec_row.id, ctx.run_id)
