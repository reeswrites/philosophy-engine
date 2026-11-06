"""Pydantic models for the institutions family (plan: plans/institutions-phase0.md, "Rule format").

Additive to schemas.py (which stays frozen): nothing here is imported by the argument pipeline.

  InstitutionJSON   one institution: roles, fluents, actions (with effects), ADICO rules, expectations,
                    optional initial state (`defaults`, `initial`, `initial_free`)
  Rule              one ADICO statement (attribute, deontic, aim, conditions, or_else) + strand/implicit/source;
                    aim_kind "action" (must-do / may / must_not do) or "state" (must-be / must-not-be a fluent),
                    inferred from the aim's head when absent (ADR 0009)
  Property          a named state formula with the step variable `t` free (properties.json)
  TraceStep         one step of a counterexample trace (actions fired, fluents true)
  RuleCheckReport   verdicts per property + traces + bound + z3 version + deontic conflicts

Loaders: load_institutions(path), load_properties(path); validation failures raise RulesLoadError
with a readable message (one line per error).

Optional typing / initial-state fields (all additive; absent = the untyped, empty-init behaviour):
  FluentDecl.arg_roles   one role per argument position; a tuple outside the roles is constant false
  FluentDecl.derived     (ADR 0013) an S-expression defining the fluent from what the rules enable, over
                         `(enabled ACTION arg ...)`, `(obliged AIM arg ...)` and other fluents; `params` names the
                         argument positions. A derived fluent has no frame axiom and may not appear in effects, initial,
                         defaults, initial_free, or as a rule's aim (loader error). Grammar:
                           E := (enabled ACTION t ...) | (obliged AIM t ...) | (FLUENT t ...) | FLUENT
                              | (not E) | (and E ...) | (or E ...) | (=> E E) | (iff E E) | (= t t)
                              | (forall ((x agent) ...) E) | (exists ((x agent) ...) E)
                           t := a name in `params`, a role literal, or a quantified variable
                         (enabled a x y) holds at t iff (a x y) is an action instance and some may/must rule on
                         it has its condition true at t and no must_not disability (or_else null) on it does;
                         an action no may/must rule names counts as enabled (warning).
                         (obliged AIM x y) (ADR 0013 amendment 2026-11-06; plans/priority-slice2.md R3.2) holds at t
                         iff (AIM x y) is an instance (action instance, or fluent tuple inside arg_roles) and some
                         `must` rule instance on it has its condition true at t; AIM is a declared action or a
                         non-derived fluent; or_else, may, must_not, default_capacity and compliance play no part.
                         Neither pseudo-predicate is allowed in a property formula or a rule condition.
  Property.primary_measure  kind goods (R3.1): guaranteed | possible, with a one-line primary_measure_reason; the
                         ablation's primary column reads the good under it (rules_ablate)
  Rule.load_bearing      dataset marks the rules a headline claim rests on; gate (a) fails if one is inert
  ActionDecl.arg_roles   one role (or null) per parameter; `args` may also be given as [[name, role], ...]
  Rule.var_roles         {variable: role} for aim / condition variables (overrides the prefix heuristic)
  InstitutionJSON.defaults      {fluent: "true" | "false"} value at t=0 for every (typed) tuple
  InstitutionJSON.initial       fluent literals true at t=0 ("employed(worker)", "(employed worker)", "flag")
  InstitutionJSON.initial_free  fluents left unconstrained at t=0
  With any of the three present the default init mode is "declared": everything not listed is false at t=0.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator, model_validator

Deontic = Literal["must", "may", "must_not"]
AimKind = Literal["action", "state"]  # ADR 0009: an aim is an action (must-do) or a fluent (must-be)
Strand = Literal["rival", "superadditive", "tying"]
# Verdict names, exactly as the plan's Checks table spells them. "open" is never "safe".
PropertyVerdict = Literal["reachable", "open", "holds_to_k", "violated", "persists", "fails", "inconsistent", "error"]
CheckKind = Literal["reachable", "invariant", "persists"]


class RoleDecl(BaseModel):
    name: str
    gloss: str = ""


class FluentDecl(BaseModel):
    name: str
    arity: int
    gloss: str = ""
    arg_roles: list[str] | None = None  # one role per argument position; None = untyped (any agent)
    derived: str | None = None  # ADR 0013: S-expression over (enabled ACTION ...) and fluents; see module doc
    params: list[str] | None = None  # names of the argument positions used inside `derived` (len == arity)


class Effect(BaseModel):
    fluent: str
    args: list[str]  # names of the action's parameters (or literal role names)
    value: bool


class ActionDecl(BaseModel):
    name: str
    args: list[str]  # parameter names; a name equal to a role is a literal (fixed to that role's agent)
    arg_roles: list[str | None] | None = None  # one role (or null) per parameter; None = heuristic typing
    effects: list[Effect] = []
    gloss: str = ""
    default_capacity: bool = False  # ADR 0013 amendment 2026-11-05: (enabled a ...) is true unless a disability bars it

    @model_validator(mode="before")
    @classmethod
    def _typed_args(cls, data):
        """Accept `args: [["h", "husband"], "w", {"name": "c", "role": "child"}]`: split into args + arg_roles."""
        if not isinstance(data, dict) or not isinstance(data.get("args"), list):
            return data
        args = data["args"]
        if all(isinstance(a, str) for a in args):
            return data
        names, roles = [], list(data.get("arg_roles") or [None] * len(args))
        roles += [None] * (len(args) - len(roles))
        for i, a in enumerate(args):
            if isinstance(a, str):
                names.append(a)
            elif isinstance(a, (list, tuple)) and len(a) == 2 and all(isinstance(x, str) for x in a):
                names.append(a[0]); roles[i] = a[1]
            elif isinstance(a, dict) and isinstance(a.get("name"), str):
                names.append(a["name"]); roles[i] = a.get("role", roles[i])
            else:
                raise ValueError(f"args[{i}]: expected a name, [name, role] or {{name, role}}, got {a!r}")
        return {**data, "args": names, "arg_roles": roles}


class Rule(BaseModel):
    id: str
    attribute: str  # role it binds; binds the aim's first argument
    deontic: Deontic
    aim: str  # "(action v1 v2 ...)" or, for a state obligation, "(fluent v1 ...)" S-expression (ADR 0009)
    aim_kind: AimKind | None = None  # None = infer: "action" if the head is a declared action, "state" if a fluent
    conditions: str  # S-expression over fluents (step implicit), or bare "true"
    or_else: str | None = None  # sanction rule id; null on must_not = disability (hard constraint)
    # key required; null = untagged, outside the bundle (plans/priority-slice2.md R2.5: coverture-floor R20). `+strands`
    # iso levels treat null as its own tag; rules_ablate's strand agreement reads it as "untagged".
    strand: Strand | None
    implicit: bool = False
    source: str = ""
    var_roles: dict[str, str] = {}  # {variable: role} for aim/condition variables; overrides the prefix heuristic
    load_bearing: bool = False  # a headline claim rests on this rule: gate (a) fails if it is inert (must-be only)


class IsoClaim(BaseModel):
    """A precommitted isomorphism claim (ADR 0010): the level is fixed before the pair is run."""
    id: str
    level: str = "exact"  # "exact" | "guard" | "exact+strands" | "guard+strands"
    sub_signature: list[str] = []  # "Ra~Rb [aim~aim]" pairs the match must contain (care+control cluster)

    def cond_level(self) -> str:
        return self.level.split("+")[0]

    def with_strands(self) -> bool:
        return "strands" in self.level.split("+")[1:]

    def pairs(self) -> list[tuple[str, str]]:
        out = []
        for s in self.sub_signature:
            head = s.split()[0]
            if "~" not in head:
                raise ValueError(f"sub_signature entry {s!r}: expected 'Ra~Rb ...'")
            x, y = head.split("~", 1)
            out.append((x, y))
        return out


class MinimalPair(BaseModel):
    """`minimal_pair_of`: the other institution, the one rule that differs, and the preregistered property
    whose verdict the pair is expected to differ on (gate (c))."""
    id: str
    rule: str | None = None
    differs_on: str | None = None


class InstitutionJSON(BaseModel):
    id: str
    name: str = ""
    roles: list[RoleDecl]
    fluents: list[FluentDecl]
    actions: list[ActionDecl]
    rules: list[Rule]
    source_text: str = ""
    expected_properties: dict[str, str] = {}
    # a bare id, or {"id": other, "level": "guard+strands" | ..., "sub_signature": ["aim~aim", ...]} naming the
    # abstraction level at which the iso is expected and the rule pairs it should map (care+control cluster)
    isomorphic_to: list[str | dict] = []
    not_isomorphic_to: list[str] = []
    # negative controls (gate (b)): institutions that must NOT match this one's cluster at the precommitted level
    not_isomorphic_to_control: list[str] = []
    # {"id": other, "rule": "R3", "differs_on": "property"} or a bare id
    minimal_pair_of: str | dict | None = None
    notes: str = ""
    # initial state (all optional; absent = init "empty", the pre-existing behaviour)
    defaults: dict[str, Literal["true", "false"]] = {}  # fluent -> value at t=0 for every tuple (before `initial`)
    initial: list[str] | None = None  # fluent literals true at t=0: "employed(worker)" / "(employed worker)" / "flag"
    initial_free: list[str] = []  # fluents left unconstrained at t=0

    @field_validator("defaults", mode="before")
    @classmethod
    def _bool_defaults(cls, v):
        if isinstance(v, dict):
            return {k: ("true" if x is True else "false" if x is False else x) for k, x in v.items()}
        return v

    def iso_targets(self) -> list[str]:
        """Institution ids in isomorphic_to, whether given bare or as {"id": ..., "level": ..., ...}."""
        return [x if isinstance(x, str) else str(x.get("id", "")) for x in self.isomorphic_to]

    def iso_claims(self) -> list[IsoClaim]:
        """isomorphic_to as IsoClaim objects (a bare id is a claim at level "exact")."""
        return [IsoClaim(id=x) if isinstance(x, str) else IsoClaim.model_validate(x) for x in self.isomorphic_to]

    def minimal_pair(self) -> MinimalPair | None:
        if self.minimal_pair_of is None:
            return None
        if isinstance(self.minimal_pair_of, str):
            return MinimalPair(id=self.minimal_pair_of)
        return MinimalPair.model_validate(self.minimal_pair_of)

    def derived_fluents(self) -> list[FluentDecl]:
        return [f for f in self.fluents if f.derived is not None]

    def declares_init(self) -> bool:
        """True when any initial-state field is present (then the default init mode is "declared")."""
        return self.initial is not None or bool(self.defaults) or bool(self.initial_free)


PropertyKind = Literal["freedom", "goods", "structure", "failure_mode"]  # priority.md decision 1
PRIMARY_REASON_MAX = 200  # plans/priority-slice2.md R3.1: primary_measure_reason is one line of at most 200 characters


class ContestedAlternative(BaseModel):
    """A second encoder's formula for a goods property that is not logically equivalent to the primary `formal`
    (plans/priority-slice2.md section 2, merge step 5). Evaluated beside the primary in every ablation run, in its own
    columns; never pooled with, averaged into, or chosen over the primary. It inherits the property's
    `primary_measure` and may not carry its own (revision 3, R3.1: the measure is a value call about the good, not
    about a formula)."""
    encoder: str
    formal: str
    note: str = ""
    subject: str | None = None  # revision 2 (R2.1): its own bearer formula; None = the primary's `subject`

    @model_validator(mode="before")
    @classmethod
    def _no_own_measure(cls, data):
        if isinstance(data, dict):
            own = [k for k in ("primary_measure", "primary_measure_reason") if k in data]
            if own:
                raise ValueError(f"contested alternative of {data.get('encoder', '?')!r}: {', '.join(own)} is not "
                                 "allowed on an alternative; it inherits the property's primary_measure (R3.1)")
        return data


class Property(BaseModel):
    name: str
    kind: PropertyKind  # required: freedom / goods count toward ablation load; structure / failure_mode are listed
    gloss: str = ""
    formal: str  # state formula, `t` free; fluent applications carry t last
    scope: str | None = None
    check: CheckKind | None = None  # explicit check kind; when absent ablation falls back to expectations / majority vote / suffix
    family: str = ""  # ablation load counts one flip per family per rule; defaults to the property's own name
    # Required "unfreedom" on every kind: freedom property (plans/priority.md slice 1 revision 5): the encoder declares
    # that the property's HOLDING is bad for the subject, which is how rules_ablate signs a flip (freedom_up/down).
    # The shape is a reading of the formula z3 cannot decide, so it is an explicit declaration the loader enforces.
    # Required "good" on every kind: goods property (plans/priority-slice2.md section 6): its holding is good for the
    # named party; rules_ablate reads a goods state (stable / fragile / absent) from it.
    polarity: Literal["unfreedom", "good"] | None = None
    # kind goods only (slice 2): the encoders who wrote it (>= 2 distinct; the first wrote `formal`) and the
    # non-equivalent alternatives (an empty list = the encoders' formulas were logically equivalent). Required there.
    encoders: list[str] = []
    contested: list[ContestedAlternative] | None = None
    # Entries the property was written for (goods: plans/priority-slice2.md section 3 "entries"). In these entries the
    # property is applicable even when it names a fluent the entry does not declare (lowered as false, with a warning);
    # elsewhere the usual rule holds (every fluent declared). Slice-2 adaptation: section 6 does not name this field.
    entries: list[str] = []
    # kind goods only, required there (plans/priority-slice2.md revision 2, R2.1): a state formula, `t` its only free
    # variable, true at t exactly when some bearer of the good exists at t. The implication premise of `formal` must
    # imply it (rules_goods.premise_implies_subject, fluents uninterpreted); per entry it may name only declared
    # fluents (rules_ablate.goods_subject_errors). rules_checks.goods_queries reads the four goods states from it.
    subject: str | None = None
    # kind goods only, required there (plans/priority-slice2.md revision 3, R3.1; author decision 1, a value call):
    # the measure under which the good is read in the ablation's third column, `primary`. A one-line reason (no
    # newline, at most 200 characters). All goods in one family share it (load_properties); a contested alternative
    # inherits it. `measure_note` stays free text the engine ignores.
    primary_measure: Literal["guaranteed", "possible"] | None = None
    primary_measure_reason: str | None = None

    @model_validator(mode="after")
    def _family_default(self):
        if not self.family:
            self.family = self.name
        if self.kind == "freedom" and self.polarity != "unfreedom":
            raise ValueError(f"property {self.name!r}: kind freedom requires polarity: unfreedom (its holding is bad for "
                             "the subject; rules_ablate signs flips by it)")
        if self.polarity == "good" and self.kind != "goods":
            raise ValueError(f"property {self.name!r}: polarity: good is only for kind goods")
        if self.kind == "goods":
            if self.polarity != "good":
                raise ValueError(f"property {self.name!r}: kind goods requires polarity: good")
            if self.contested is None:
                raise ValueError(f"property {self.name!r}: kind goods requires a contested list ([] when the encoders' "
                                 "formulas were equivalent)")
            if len(set(self.encoders)) < 2:
                raise ValueError(f"property {self.name!r}: kind goods requires encoders naming at least two encoders")
            if self.check != "persists":
                raise ValueError(f"property {self.name!r}: kind goods requires check: persists")
            if not self.subject:
                raise ValueError(f"property {self.name!r}: kind goods requires a subject formula (some bearer exists at t)")
        elif self.subject is not None:
            raise ValueError(f"property {self.name!r}: subject is only for kind goods")
        if self.kind == "goods":
            from . import rules_goods, sexpr
            pairs = [("formal", self.formal, self.subject)] + [
                (f"contested formula of {a.encoder!r}", a.formal, a.subject or self.subject) for a in self.contested or ()]
            for what, f, subj in pairs:
                try:
                    sexpr.parse(subj)
                except Exception as e:  # noqa: BLE001 - any parse failure is a load error
                    raise ValueError(f"property {self.name!r}: subject (for {what}) does not parse: {e}")
                try:
                    sexpr.parse(f)
                except Exception:  # noqa: BLE001 - reported below for alternatives, by the engine for formal
                    continue
                try:
                    ok = rules_goods.premise_implies_subject(f, subj)
                except Exception as e:  # noqa: BLE001 - e.g. z3 Sort mismatch: a free step variable (t0) in subject
                    raise ValueError(f"property {self.name!r}: subject (for {what}) does not type-check against the "
                                     f"formula ({type(e).__name__}: {e}); only t may be free in a subject, and a step "
                                     "variable must be bound")
                if ok is not True:
                    raise ValueError(f"property {self.name!r}: the implication premise of the {what} does not imply "
                                     f"its subject ({'z3 unknown' if ok is None else 'counterexample exists'}; "
                                     "fluents uninterpreted)")
        if self.kind == "goods":
            if self.primary_measure is None:
                raise ValueError(f"property {self.name!r}: kind goods requires primary_measure (guaranteed | possible; "
                                 "plans/priority-slice2.md R3.1)")
            r = self.primary_measure_reason
            if r is None or not r.strip():
                raise ValueError(f"property {self.name!r}: kind goods requires a non-empty primary_measure_reason")
            if "\n" in r or "\r" in r:
                raise ValueError(f"property {self.name!r}: primary_measure_reason must be one line (no newline)")
            if len(r) > PRIMARY_REASON_MAX:
                raise ValueError(f"property {self.name!r}: primary_measure_reason has {len(r)} characters; at most "
                                 f"{PRIMARY_REASON_MAX}")
        else:
            own = [k for k in ("primary_measure", "primary_measure_reason") if getattr(self, k) is not None]
            if own:
                raise ValueError(f"property {self.name!r}: {', '.join(own)} is only for kind goods")
        if self.contested:
            from . import sexpr
            for alt in self.contested:
                try:
                    sexpr.parse(alt.formal)
                except Exception as e:  # noqa: BLE001 - any parse failure is a load error
                    raise ValueError(f"property {self.name!r}: contested formula of {alt.encoder!r} does not parse: {e}")
        return self


class TraceStep(BaseModel):
    step: int
    actions: list[str] = []  # "name(agent, agent)" fired at this step (effects land at step+1)
    fluents: list[str] = []  # "fluent(agent, ...)" true at this step
    property_holds: bool | None = None  # value of the checked property at this step (if applicable)


class PropertyResult(BaseModel):
    property: str
    check: CheckKind
    verdict: PropertyVerdict
    trace: list[TraceStep] | None = None
    reason: str | None = None  # z3 reason_unknown, lowering error, ...
    z3_ms: int = 0
    z3_unknown: bool = False  # verdict "open" because z3 gave no answer (timeout / unknown), not because the bounded search found nothing
    # vacuity (invariant / persists only): is the antecedent (the formula's implication premise, else the formula)
    # true at some step of some compliant trace, and does any `is_*` fluent ever hold? None = not applicable
    antecedent_reachable: bool | None = None
    subject_exists: bool | None = None
    vacuous: bool = False  # either flag is False
    # goods (kind goods, persists check; revision 2 R2.1, rules_checks.goods_queries): not_applicable | absent | fragile
    # | stable, or None with goods_reason (subject_unknown | no_witness_within_k | witness_unknown | possible_unknown
    # | guaranteed_unknown). goods_queries: the four query outcomes (sat / unsat / unknown; guaranteed: the
    # invariant verdict). The old vacuity flags are not computed for goods.
    goods_state: Literal["not_applicable", "absent", "fragile", "stable"] | None = None
    goods_reason: str | None = None
    goods_queries: dict[str, str] | None = None


class RuleStatus(BaseModel):
    """Per-rule finding from run_all. kind "inert": a must-be / must-not-be rule whose breach (C and not F, or
    C and F) no compliant trace of the other rules can reach within k: the rule constrains nothing."""
    rule: str
    kind: Literal["inert"]
    load_bearing: bool = False
    detail: str = ""


class QueryTiming(BaseModel):
    """One timed z3 query (or one cache hit, `cached` True with zero solve time). `phase`: ground | consistent |
    conflict | inert | check | vacuity | cached. build_ms = time spent building expressions / loading them into the
    solver since the previous query; solve_ms = time in solver.check (both attempts when `retries` is 1)."""
    institution: str
    phase: str
    property: str = ""
    check: str = ""
    build_ms: float = 0.0
    solve_ms: float = 0.0
    result: str = ""  # sat | unsat | unknown, or the cached verdict
    retries: int = 0
    k: int = 0
    step_mode: str = "one"
    init: str = "empty"
    z3_version: str | None = None
    cached: bool = False


class RuleCheckReport(BaseModel):
    institution: str
    bound_k: int
    consistent: Literal["sat", "unsat", "unknown"]
    conflicts: list[tuple[str, str]] = []  # (must rule id, must_not rule id) with overlapping conditions
    results: list[PropertyResult] = []
    inert: list[str] = []  # must-be rules nothing can break within k (RuleStatus details in rule_status)
    rule_status: list[RuleStatus] = []
    warnings: list[str] = []  # lowering caveats (undeclared fluents in a property, heuristic var typing, ...)
    z3_version: str | None = None
    z3_ms: int = 0
    init: str = "empty"  # resolved mode: empty | free | declared
    compliance: str = "strict"
    step_mode: str = "one"  # one action per step, or many
    timing: list[QueryTiming] = []  # per-query timings (additive; see QueryTiming)

    def verdict(self, prop: str) -> PropertyVerdict | None:
        for r in self.results:
            if r.property == prop:
                return r.verdict
        return None


class RulesLoadError(ValueError):
    pass


def _readable(e: ValidationError, where: str) -> str:
    lines = [f"{where}: {e.error_count()} validation error(s)"]
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def load_institutions(path: str | Path) -> list[InstitutionJSON]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise RulesLoadError(f"{path}: expected a JSON list of institutions")
    out: list[InstitutionJSON] = []
    errs: list[str] = []
    for i, item in enumerate(raw):
        try:
            out.append(InstitutionJSON.model_validate(item))
        except ValidationError as e:
            errs.append(_readable(e, f"{path}[{i}] ({item.get('id', '?') if isinstance(item, dict) else '?'})"))
    if errs:
        raise RulesLoadError("\n".join(errs))
    ids = [x.id for x in out]
    if len(set(ids)) != len(ids):
        raise RulesLoadError(f"{path}: duplicate institution ids in {ids}")
    return out


def load_properties(path: str | Path) -> dict[str, Property]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise RulesLoadError(f"{path}: expected a JSON list of properties")
    out: dict[str, Property] = {}
    errs: list[str] = []
    for i, item in enumerate(raw):
        try:
            p = Property.model_validate(item)
        except ValidationError as e:
            errs.append(_readable(e, f"{path}[{i}]"))
            continue
        if p.name in out:
            errs.append(f"{path}: duplicate property {p.name!r}")
        out[p.name] = p
    errs += family_measure_errors(out)
    if errs:
        raise RulesLoadError("\n".join(errs))
    return out


def family_measure_errors(props: dict[str, Property]) -> list[str]:
    """R3.1: all goods in one `family` share `primary_measure` (a load error otherwise)."""
    fam: dict[str, dict[str, list[str]]] = {}
    for p in props.values():
        if p.kind == "goods":
            fam.setdefault(p.family, {}).setdefault(str(p.primary_measure), []).append(p.name)
    return [f"goods family {f!r}: members differ in primary_measure ("
            + "; ".join(f"{m}: {', '.join(sorted(ns))}" for m, ns in sorted(by.items())) + ")"
            for f, by in sorted(fam.items()) if len(by) > 1]


def default_paths() -> tuple[Path, Path]:
    from . import config
    d = config.data_dir() / "institutions"
    return d / "institutions.json", d / "properties.json"
