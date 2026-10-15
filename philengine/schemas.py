"""Pydantic v2 models for the whole pipeline. FROZEN after builder step 1:
later changes may only ADD fields/models (request via README "Schema changes")."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Type = Literal["logical", "definitional", "empirical", "normative", "metaphysical"]
Verdict = Literal["valid", "refuted", "open"]


# ---- Reconstruction (LLM emits this; also the human GT shape) ----
class PremiseIn(BaseModel):
    id: str  # "P1", "P2"...; implicit ones also numbered in sequence
    text: str  # plain English, one claim, no pronouns
    implicit: bool = False
    type: Type
    rationale: str = ""  # for implicit: why needed / where the text hints at it


class Reconstruction(BaseModel):
    premises: list[PremiseIn]  # 2..8 by convention (not enforced)
    conclusion: str
    conclusion_type: Type | None = None
    notes: str = ""  # LLM may flag interpretive choices


# ---- Formalization (LLM emits this) ----
class SortDecl(BaseModel):
    name: str  # "Obj" default; extra sorts allowed


class PredDecl(BaseModel):
    name: str  # snake_case ASCII, [a-z][a-z0-9_]*
    arg_sorts: list[str]  # arity = len; [] allowed = propositional constant
    gloss: str  # English meaning, REQUIRED


class ConstDecl(BaseModel):
    name: str
    sort: str
    gloss: str


class FormulaItem(BaseModel):
    premise_id: str  # matches PremiseIn.id, or "C" for conclusion
    sexpr: str  # e.g. "(forall ((x Obj)) (=> (man x) (mortal x)))"


class FormalizationJSON(BaseModel):
    sorts: list[SortDecl] = [SortDecl(name="Obj")]
    predicates: list[PredDecl]
    constants: list[ConstDecl] = []
    premises: list[FormulaItem]  # exactly one per reconstruction premise, same ids
    conclusion: FormulaItem  # premise_id == "C"
    notes: str = ""


# ---- Pipeline stage outputs (stored as JSON artifacts + DB rows) ----
class ReconstructionRecord(BaseModel):
    id: int
    argument_id: str
    source: Literal["human", "llm"]
    model: str | None
    reconstruction: Reconstruction
    llm_call_id: int | None


class CheckReport(BaseModel):
    parse_ok: bool
    parse_errors: list[str] = []
    consistent: Literal["sat", "unsat", "unknown"]  # premises alone
    valid: Literal["valid", "refuted", "unknown"]
    countermodel_text: str | None
    unsat_core: list[str] = []  # premise ids used (tracked asserts)
    minimal: bool | None
    redundant_premises: list[str] = []
    nontrivial: bool | None
    trivial_reasons: list[str] = []
    vacuous: bool
    z3_ms: int
    # additions (builder step 1, plan section 3 prose):
    unknown_reason: str | None = None
    z3_version: str | None = None


class JudgeReport(BaseModel):
    back_translations: dict[str, str]  # premise_id -> English
    scores: dict[str, float]  # premise_id -> faithfulness 0..1
    conclusion_score: float
    min_score: float
    mean_score: float
    flags: list[
        Literal[
            "strengthened",
            "weakened",
            "dropped_content",
            "added_content",
            "scope_shift",
            "quantifier_error",
            "predicate_collapse",
        ]
    ]
    per_item_comments: dict[str, str]


class FormalizationRecord(BaseModel):
    id: int
    reconstruction_id: int
    candidate_idx: int
    formalization: FormalizationJSON | None
    check: CheckReport | None
    judge: JudgeReport | None
    status: Literal["ok", "parse_fail", "check_fail", "judge_fail"]
    llm_call_ids: list[int]


class SelectionResult(BaseModel):
    reconstruction_id: int
    chosen_formalization_id: int | None
    verdict: Verdict  # derived from chosen
    ranking: list[dict]  # [{formalization_id, score, rejected_reasons:[...]}]
    rejected_trivial: int  # count: gate metric


class Skeleton(BaseModel):
    canonical: str  # canonical text of abstracted formulas
    hash: str  # sha256 of canonical
    pred_map: dict[str, str]  # original name -> P1..Pn
    pred_arity: dict[str, int]


class IsoResult(BaseModel):
    a_id: str
    b_id: str
    skeleton_match: bool
    mapping: dict[str, str] | None
    z3_verified: bool | None
    expected: bool | None
