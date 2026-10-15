"""Models that extend the FROZEN schemas.py without editing it.

- `metaphysical` is a 5th premise type (now also in schemas.Type); stored as-is.
- Predicates/constants carry `sense` (and a slot-template `gloss`); subclasses of the frozen
  models, so they pass straight into checks.run_all / fol.validate.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .schemas import ConstDecl, FormalizationJSON, PredDecl, PremiseIn, Reconstruction, Type

TypeX = Type


class PremiseX(PremiseIn):
    type: TypeX  # type: ignore[assignment]
    fol_hint: str = ""


class ReconstructionX(Reconstruction):
    premises: list[PremiseX]  # type: ignore[assignment]
    conclusion_type: TypeX | None = None  # type: ignore[assignment]

    def to_frozen(self) -> Reconstruction:
        ps = [PremiseIn(id=p.id, text=p.text, implicit=p.implicit, type=p.type,
                        rationale=p.rationale, shared_id=p.shared_id) for p in self.premises]
        ct = self.conclusion_type
        return Reconstruction(premises=ps, conclusion=self.conclusion, conclusion_type=ct, notes=self.notes)


class PredDeclX(PredDecl):
    sense: str = ""  # e.g. "exists:actual"; same word, two meanings => two symbols


class ConstDeclX(ConstDecl):
    sense: str = ""


class FormalizationX(FormalizationJSON):
    predicates: list[PredDeclX]  # type: ignore[assignment]
    constants: list[ConstDeclX] = []  # type: ignore[assignment]

    def slot_errors(self) -> list[str]:
        """Gloss/sense problems (empty list = ok); step 3 may feed these to the retry."""
        errs = []
        for p in self.predicates:
            n = len(p.arg_sorts)
            slots = {int(m) for m in re.findall(r"\{(\d+)\}", p.gloss)}
            if slots != set(range(n)):
                errs.append(f"predicate {p.name}: gloss {p.gloss!r} must contain exactly slots "
                            f"{{0}}..{{{n - 1}}}" if n else f"predicate {p.name}: gloss must have no slots")
            if not p.sense:
                errs.append(f"predicate {p.name}: missing sense")
        for c in self.constants:
            if not c.sense:
                errs.append(f"constant {c.name}: missing sense")
        return errs

    def gloss_warnings(self) -> list[str]:
        """Non-fatal: glosses containing connective words render ambiguously inside compound formulas
        (verbalize parenthesizes them, but the reader may still be confused)."""
        from .verbalize import CONNECTIVE_WORDS
        return [f"{kind} {x.name}: gloss {x.gloss!r} contains a connective word"
                for kind, xs in (("predicate", self.predicates), ("constant", self.constants))
                for x in xs if CONNECTIVE_WORDS.search(x.gloss)]


class JudgeOut(BaseModel):
    """What the judge LLM emits (step 3 turns this + verbalizations into schemas.JudgeReport)."""
    scores: dict[str, float]  # premise_id -> 0..1
    conclusion_score: float
    flags: list[Literal[
        "strengthened", "weakened", "dropped_content", "added_content", "scope_shift",
        "quantifier_error", "predicate_collapse",
        "conclusion_smuggled", "sense_drift", "formalization_omits_premise",
        "reconstruction_gap", "missing_implicit_premise",  # the last one is the pre-round-3 name (legacy, soft)
    ]] = []
    per_item_comments: dict[str, str] = {}


# Round 3: `missing_implicit_premise` was being raised for gaps in the RECONSTRUCTION (the formalizer faithfully
# rendered an argument that needs an unstated step), which must never reject a formalization. It is split:
#   reconstruction_gap          soft: review row on the reconstruction, no effect on selection
#   formalization_omits_premise hard: the formalization drops / misreads a premise the reconstruction states
# The legacy flag is still accepted (old judge reports, old prompts) and treated as the soft one.
HARD_REJECT_FLAGS = ("conclusion_smuggled", "sense_drift", "formalization_omits_premise")
SOFT_REVIEW_FLAGS = ("reconstruction_gap", "missing_implicit_premise")


def hard_rejects(j, ignore: tuple[str, ...] = ()) -> bool:
    """Judge hard reject: every sample raised a (live) hard flag. Recomputed from `sample_flags` when they were
    stored, so reports judged under an older flag set (e.g. `missing_implicit_premise` as hard) are re-read under
    the current HARD_REJECT_FLAGS; the stored `hard_reject` bool is the fallback."""
    live = tuple(x for x in HARD_REJECT_FLAGS if x not in ignore)
    sf = getattr(j, "sample_flags", None)
    if sf:
        return all(any(x in live for x in s) for s in sf)
    if not ignore:
        return bool(getattr(j, "hard_reject", False)) and any(x in HARD_REJECT_FLAGS for x in j.flags)
    return bool(getattr(j, "hard_reject", False)) and any(x in live for x in j.flags)


def soft_review_flags(j) -> list[str]:
    return [x for x in getattr(j, "flags", []) if x in SOFT_REVIEW_FLAGS]


# ---- step 3 extensions (schemas.py is frozen; these widen it without editing it) ----
from .schemas import JudgeReport, SelectionResult  # noqa: E402


class JudgeReportX(JudgeReport):
    """JudgeReport + the hard-reject flags, the mechanical verbalization the judge saw, and hard_reject."""
    flags: list[Literal[  # type: ignore[assignment]
        "strengthened", "weakened", "dropped_content", "added_content", "scope_shift",
        "quantifier_error", "predicate_collapse",
        "conclusion_smuggled", "sense_drift", "formalization_omits_premise",
        "reconstruction_gap", "missing_implicit_premise",
    ]] = []
    hard_reject: bool = False
    verbalization: str = ""
    n_samples: int = 1
    judge_call_ids: list[int] = []  # one llm_call id per judge sample used
    sample_flags: list[list[str]] = []  # each judge sample's own flags (hard_reject = every sample has a hard flag)
    duplicate_of_candidate: int | None = None  # round 3: report copied from an identical earlier candidate (no judge call)


SELECTION_STATUSES = ("selected", "judge-weak", "open: decided candidates all rejected", "open: no decided candidate",
                      "open: no candidates")


class SelectionResultX(SelectionResult):
    rejected_judge: int = 0  # judge hard rejects (rejected_trivial counts checker-derived triviality only)
    contested: bool = False
    # round 3
    judge_weak: bool = False  # chosen candidate's judge mean_score < JUDGE_MEAN_SCORE (penalized, not filtered)
    status: str = ""  # one of SELECTION_STATUSES ("" for selections stored before round 3)
    diversity: dict = {}  # {n, distinct, distinct_pred_sets, ratio}: how different the candidates actually were
