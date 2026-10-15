"""Models that extend the FROZEN schemas.py without editing it.

- `metaphysical` is a 5th premise type in the human data and the reconstruct prompt;
  schemas.Type only has 4, so `to_frozen()` maps it (see `FROZEN_TYPE_MAP`) while the
  original value survives in `premise.type_ext` in the store and in raw JSON.
- Predicates/constants carry `sense` (and a slot-template `gloss`); subclasses of the frozen
  models, so they pass straight into checks.run_all / fol.validate.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .schemas import ConstDecl, FormalizationJSON, PredDecl, PremiseIn, Reconstruction

TypeX = Literal["logical", "definitional", "empirical", "normative", "metaphysical"]
FROZEN_TYPE_MAP = {"metaphysical": "empirical"}


def frozen_type(t: str) -> str:
    return FROZEN_TYPE_MAP.get(t, t)


class PremiseX(PremiseIn):
    type: TypeX  # type: ignore[assignment]
    fol_hint: str = ""


class ReconstructionX(Reconstruction):
    premises: list[PremiseX]  # type: ignore[assignment]
    conclusion_type: TypeX | None = None  # type: ignore[assignment]

    def to_frozen(self) -> Reconstruction:
        ps = [PremiseIn(id=p.id, text=p.text, implicit=p.implicit, type=frozen_type(p.type),
                        rationale=p.rationale) for p in self.premises]
        ct = frozen_type(self.conclusion_type) if self.conclusion_type else None
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


class JudgeOut(BaseModel):
    """What the judge LLM emits (step 3 turns this + verbalizations into schemas.JudgeReport)."""
    scores: dict[str, float]  # premise_id -> 0..1
    conclusion_score: float
    flags: list[Literal[
        "strengthened", "weakened", "dropped_content", "added_content", "scope_shift",
        "quantifier_error", "predicate_collapse",
        "conclusion_smuggled", "sense_drift", "missing_implicit_premise",
    ]] = []
    per_item_comments: dict[str, str] = {}


HARD_REJECT_FLAGS = ("conclusion_smuggled", "sense_drift", "missing_implicit_premise")
