"""Stage: select. Z3-side hard filters first (judge can never rescue a trivial candidate), then weighted score."""
from __future__ import annotations

from . import checks, config
from .models_ext import SelectionResultX, hard_rejects
from .runner import Ctx, Unit, register
from .stage_common import diversity, latest_by_candidate, pick_reconstruction


def _n_preds(form) -> int:
    return len(form.formalization.predicates) if form.formalization else 0


INCONSISTENT_REASON = "premises inconsistent"


def inconsistency_allowed(forms, expected: str | None) -> bool:
    """Inconsistent candidates are a finding, not vacuity, when the human reconstruction expects `inconsistent`
    or >= 2 candidates agree that the premises are unsat."""
    n = sum(1 for f in forms if f.check is not None and f.check.parse_ok and f.check.consistent == "unsat")
    return n >= 1 and (expected == "inconsistent" or n >= 2)


def reject_reasons(form, allow_inconsistent: bool = False, expected: str | None = None) -> tuple[list[str], bool]:
    """-> (reasons, rejected_as_trivial). The flag is derived from the CHECKER only (nontrivial is False /
    vacuous); judge hard rejects are reported in `reasons` and counted separately (rejected_judge).
    With allow_inconsistent, an unsat-premises candidate is not trivial/vacuous on that ground alone.
    When the human expected verdict is `inconsistent` and the candidate is unsat, a judge `conclusion_smuggled`
    flag is ignored (an inconsistent premise set entails everything; that is the finding, not smuggling).
    Judge min_score and mean_score below their thresholds are NOT filters (see judge_min_penalty / judge_mean_penalty);
    conclusion_score is the only judge score that filters (round 3)."""
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
    ignore = ("conclusion_smuggled",) if (expected == "inconsistent" and chk.consistent == "unsat") else ()
    if hard_rejects(j, ignore):
        r.append(f"judge hard reject: {[x for x in j.flags if x not in ignore]}")
    if j.conclusion_score < config.JUDGE_CONCLUSION_SCORE:
        r.append(f"judge conclusion_score {j.conclusion_score:.2f} < {config.JUDGE_CONCLUSION_SCORE}")
    return r, triv


def judge_min_penalty(j) -> tuple[float, list[str]]:
    """Soft replacement for the old min_score filter: JUDGE_MIN_PENALTY per premise scoring below JUDGE_MIN_SCORE,
    capped at JUDGE_MIN_PENALTY_CAP. -> (penalty, failing premise ids)."""
    bad = sorted(k for k, v in j.scores.items() if v < config.JUDGE_MIN_SCORE)
    return min(config.JUDGE_MIN_PENALTY * len(bad), config.JUDGE_MIN_PENALTY_CAP), bad


def judge_mean_penalty(j) -> float:
    """Round 3: mean_score below JUDGE_MEAN_SCORE is a flat select-score penalty (JUDGE_MEAN_PENALTY), not a filter.
    A Z3-decided candidate the judge finds weak is selected with status `judge-weak` instead of leaving the argument
    `open`."""
    return config.JUDGE_MEAN_PENALTY if j.mean_score < config.JUDGE_MEAN_SCORE else 0.0


def judge_weak(j) -> bool:
    return j is not None and j.mean_score < config.JUDGE_MEAN_SCORE


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
    sc -= judge_min_penalty(j)[0]
    sc -= judge_mean_penalty(j)
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
        reasons, triv = reject_reasons(f, allow_incons, row["e"] if row else None)
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
        if f.judge is not None:
            jp, bad = judge_min_penalty(f.judge)
            if bad:
                entry["notes"] = [*entry.get("notes", []), f"judge min_score penalty {jp:.2f} on {bad} (< {config.JUDGE_MIN_SCORE})"]
            if judge_weak(f.judge):
                entry["flags"] = [*entry.get("flags", []), "judge_weak"]
                entry["notes"] = [*entry.get("notes", []),
                                  f"judge mean_score penalty {judge_mean_penalty(f.judge):.2f} ({f.judge.mean_score:.2f} < {config.JUDGE_MEAN_SCORE})"]
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
    weak = bool(chosen and judge_weak(chosen.judge))
    status = selection_status(chosen, ranking, forms, weak)
    sel = SelectionResultX(reconstruction_id=recon_id, chosen_formalization_id=chosen.id if chosen else None,
                           verdict=verdict, ranking=ranking, rejected_trivial=rejected_trivial, rejected_judge=rejected_judge,
                           contested=contested, judge_weak=weak, status=status, diversity=diversity(forms))
    store.insert_selection(sel, run_id)
    if contested:
        store.insert_review("selection", str(recon_id), "contested: parsed candidates (survivors and rejected) disagree on verdict", run_id)
    if weak:
        store.insert_review("selection", str(recon_id),
                            f"judge-weak: chosen candidate {chosen.candidate_idx} is Z3-{verdict} but judge mean_score "
                            f"{chosen.judge.mean_score:.2f} < {config.JUDGE_MEAN_SCORE}", run_id)
    for idx, orph in orphan_reviews:
        store.insert_review("selection", str(recon_id),
                            f"orphan_conclusion_predicate: candidate {idx} {orph} appear in C but in no premise", run_id)
    for idx, pen in bic_reviews:
        store.insert_review("selection", str(recon_id),
                            f"conclusion via implicit/non-definitional biconditional: candidate {idx} {pen}", run_id)
    for idx, probes in unknown_cands:
        store.insert_review("selection", str(recon_id), f"unknown probe: candidate {idx} {probes or ['nontrivial']}", run_id)
    return sel


def selection_status(chosen, ranking, forms, weak: bool) -> str:
    """Round 3: one of models_ext.SELECTION_STATUSES. `judge-weak` = decided by Z3, selected, but judge mean below
    threshold; `open: decided candidates all rejected` = a Z3-decided (valid/refuted/inconsistent) candidate existed
    and every one was rejected (hard flag, triviality, parse) -- the row to look at when agreement is low."""
    if chosen is not None:
        return "judge-weak" if weak else "selected"
    if not forms:
        return "open: no candidates"
    if any(e.get("verdict") in ("valid", "refuted", "inconsistent") for e in ranking):
        return "open: decided candidates all rejected"
    return "open: no decided candidate"


@register("select")
def select(ctx: Ctx, unit: Unit) -> None:
    rec_row = pick_reconstruction(ctx, unit.argument_id)
    select_for(ctx.store, rec_row.id, ctx.run_id)
