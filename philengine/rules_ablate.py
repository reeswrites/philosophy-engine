"""Rule ablation (plans/priority.md, slice 1): which rule carries which property verdict.

  ablate(inst, properties, k)            one RuleAblation per rule: delete the rule, rerun the checks the entry's
                                         expected_properties name (run_all default), record per property (before, after)
  ablate_multi_k(inst, properties, ks)   the same at each k (default 6 and 8) + the properties whose flip set differs by k

A *flip* is a change of verdict among the six real verdicts (reachable, open, holds_to_k, violated, persists, fails).
`error`, `inconsistent`, and an `open` that is a z3 unknown (not the bounded-search "not found within k") never count as
a flip. A deletion that leaves no compliant trace is reported as `inconsistent_after` (its own row, no flips).
Loads are counts per property FAMILY (Property.family, default the property id; one flip counted once per family per
rule) per kind (freedom / goods); structure and failure_mode flips are listed, not counted. Ranking is on
load_freedom_up (families only); load_freedom_down names a load-bearing protection, never a cut. Every `may` rule gets a
second row (variant "prohibited", id `<id>~prohibit`): replaced by a must_not with the same attribute, aim, conditions,
strand and implicit, or_else null. It is ranked and never deregulated. Loads are
never summed. The ablated institution is rebuilt through InstitutionJSON.model_validate, so derived power fluents
(ADR 0013) recompute exactly as for any institution.

ASSUMED (option (a) of docs/reviews/2026-11-05-ablation-slice1-review.md, chosen by the coordinator as the slice-1
reading; the author has not ratified it): a deleted may/must rule whose aim action keeps NO may/must rule leaves that
action unregulated (rules_lower.regulated_actions): always enabled, and every derived power over it zeroed. Such a
deletion is `deregulated`; its loads are computed and shown but it is NOT ranked (CLI: separate block; summary: excluded).
Only a `may` deletion that leaves the action regulated is labelled "permission removed".

Orphaned or_else: a rule whose `or_else` named the deleted rule would no longer validate; that reference is cleared and the
rule id listed in `orphaned_or_else`. Under compliance=strict an orphan is ignored (or_else is not read), so load is not
inflated. Under compliance=sanctioned the clearing hardens the rule (a soft must_not becomes a hard disability), which can
inflate load; read sanctioned runs only with the orphaned_or_else column.

Flip direction (freedom kind only): see POLARITY. load_freedom = load_freedom_up + load_freedom_down (+ unsigned for a
freedom property missing from the table).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import rules_checks
from .rules_lower import regulated_actions, validate_property, aim_kind, parse_aim
from .schemas_rules import InstitutionJSON, Property, RuleCheckReport

REAL = ("reachable", "open", "holds_to_k", "violated", "persists", "fails")

# HAND INPUT, to be replaced by a `polarity` field on Property in slice 2. Every current freedom property states an
# UNFREEDOM (its holding is bad for the subject), so a verdict moving from {reachable, holds_to_k, persists} (the
# unfreedom is present) toward {open, violated, fails} (it is not) is freedom_up; the reverse is freedom_down.
UNFREEDOM = frozenset({
    "dependent_cannot_exit", "subject_cannot_exit", "subject_cannot_exit_persists", "no_standing", "no_standing_persists",
    "financial_dependence", "financial_dependence_unpropertied", "cannot_contract", "worker_uninsured",
    "binding_practised", "marriage_requires_binding", "care_assigned_by_sex", "reproduction_controlled_by_owner",
    "offspring_owned", "female_parent_care_persists", "care_duty_on_women"})
_UNFREEDOM_PRESENT = ("reachable", "holds_to_k", "persists")
_UNFREEDOM_ABSENT = ("open", "violated", "fails")


def flip_direction(name: str, before: str, after: str) -> str:
    """freedom_up | freedom_down | unsigned (property not in UNFREEDOM)."""
    if name not in UNFREEDOM:
        return "unsigned"
    if before in _UNFREEDOM_PRESENT and after in _UNFREEDOM_ABSENT:
        return "freedom_up"
    if before in _UNFREEDOM_ABSENT and after in _UNFREEDOM_PRESENT:
        return "freedom_down"
    return "unsigned"


@dataclass
class RuleAblation:
    rule_id: str
    deontic: str
    strand: str
    implicit: bool
    permission_removed: bool
    variant: str = "deleted"  # deleted | prohibited
    load_freedom: int = 0  # families with any freedom flip (up, down or unsigned)
    load_freedom_up: int = 0
    load_freedom_down: int = 0
    load_freedom_unsigned: int = 0
    families_up: list[str] = field(default_factory=list)
    families_down: list[str] = field(default_factory=list)
    load_goods: int = 0
    deregulated: bool = False  # deleted may/must was the last regulator of its action: not ranked
    flip_directions: dict[str, str] = field(default_factory=dict)  # freedom flips: property -> freedom_up/down/unsigned
    check_kinds: dict[str, str] = field(default_factory=dict)  # property -> check kind actually run
    check_sources: dict[str, str] = field(default_factory=dict)  # property -> property | expected | majority | suffix | default
    structure_flips: list[str] = field(default_factory=list)
    failure_mode_flips: list[str] = field(default_factory=list)
    flips: list[tuple[str, str, str]] = field(default_factory=list)  # (property, before, after)
    inconsistent_after: bool = False
    uncounted: list[str] = field(default_factory=list)  # properties with error / z3-unknown on either side
    orphaned_or_else: list[str] = field(default_factory=list)
    k: int = 6
    applicable: int = 0  # properties evaluated for this entry
    not_applicable: list[str] = field(default_factory=list)  # properties naming a fluent the entry does not declare

    def to_dict(self) -> dict:
        return asdict(self)


def effective_verdict(res) -> str | None:
    """The verdict if it is one of the six real ones, else None (error, inconsistent, or z3 unknown)."""
    v = res.verdict
    if v not in REAL:
        return None
    if v == "open" and res.z3_unknown:
        return None  # z3 unknown (or consistency unknown): never a flip
    return v


def without_rule(inst: InstitutionJSON, rule_id: str) -> tuple[InstitutionJSON, list[str]]:
    """inst minus one rule, rebuilt through the loader path. Returns (institution, ids whose or_else was cleared)."""
    d = inst.model_dump()
    if rule_id not in {r["id"] for r in d["rules"]}:
        raise KeyError(rule_id)
    d["rules"] = [r for r in d["rules"] if r["id"] != rule_id]
    orphaned = []
    for r in d["rules"]:
        if r.get("or_else") == rule_id:
            r["or_else"] = None
            orphaned.append(r["id"])
    return InstitutionJSON.model_validate(d), orphaned


def prohibited(inst: InstitutionJSON, rule_id: str) -> tuple[InstitutionJSON, list[str]]:
    """inst with one `may` rule replaced by a must_not (id `<id>~prohibit`, or_else null), through the loader path."""
    d = inst.model_dump()
    new_id = rule_id + "~prohibit"
    orphaned = []
    found = False
    for r in d["rules"]:
        if r["id"] == rule_id:
            r.update(id=new_id, deontic="must_not", or_else=None)
            found = True
    if not found:
        raise KeyError(rule_id)
    for r in d["rules"]:
        if r.get("or_else") == rule_id:
            r["or_else"] = None
            orphaned.append(r["id"])
    return InstitutionJSON.model_validate(d), orphaned


def check_kinds(insts: list[InstitutionJSON]) -> dict[str, str]:
    """Check kind per property name, from the expectations across all entries (most common wins). Properties no entry
    expects fall back to `persists` for names ending _persists, else `reachable` (see check_for_property)."""
    votes: dict[str, dict[str, int]] = {}
    for i in insts:
        for n, e in i.expected_properties.items():
            c = rules_checks.check_for_expected(e)
            if c:
                votes.setdefault(n, {}).setdefault(c, 0)
                votes[n][c] += 1
    return {n: max(v.items(), key=lambda x: (x[1], x[0]))[0] for n, v in votes.items()}


def check_source(name: str, inst: InstitutionJSON, kinds: dict[str, str] | None,
                 properties: dict[str, Property] | None = None) -> tuple[str, str]:
    """(check kind, source): property (explicit `check` key) | expected (this entry) | majority (other entries) | suffix | default."""
    if properties and name in properties and properties[name].check:
        return properties[name].check, "property"
    c = rules_checks.check_for_expected(inst.expected_properties[name]) if name in inst.expected_properties else None
    if c:
        return c, "expected"
    if (kinds or {}).get(name):
        return kinds[name], "majority"
    return ("persists", "suffix") if name.endswith("_persists") else ("reachable", "default")


def check_for_property(name: str, inst: InstitutionJSON, kinds: dict[str, str] | None,
                       properties: dict[str, Property] | None = None) -> str:
    return check_source(name, inst, kinds, properties)[0]


def applicable_which(inst: InstitutionJSON, properties: dict[str, Property],
                     kinds: dict[str, str] | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """({property: [check]}, not_applicable). Applicable = every fluent the formula names is declared in the entry;
    anything in expected_properties is included regardless."""
    which, na = {}, []
    for n, p in properties.items():
        if n not in inst.expected_properties:
            errs, warns = validate_property(p, inst)
            if errs or any("undeclared fluent" in w for w in warns):
                na.append(n)
                continue
        which[n] = [check_for_property(n, inst, kinds, properties)]
    for n in inst.expected_properties:
        which.setdefault(n, [check_for_property(n, inst, kinds, properties)])
    return which, sorted(na)


def _verdicts(rep: RuleCheckReport) -> dict[str, object]:
    return {r.property: r for r in rep.results}


_BASE: dict[tuple, RuleCheckReport] = {}


def base_report(inst: InstitutionJSON, properties: dict[str, Property], k: int, which: dict[str, list[str]],
                **run_kw) -> RuleCheckReport:
    """run_all on the unablated entry, memoised per (entry content, k, run options, properties checked)."""
    key = (inst.model_dump_json(), k, tuple(sorted(run_kw.items(), key=lambda x: x[0])),
           tuple(sorted((n, properties[n].formal if n in properties else "", tuple(c)) for n, c in which.items())))
    if key not in _BASE:
        _BASE[key] = rules_checks.run_all(inst, properties, k=k, which=which, **run_kw)
    return _BASE[key]


def ablate(inst: InstitutionJSON, properties: dict[str, Property], k: int = 6,
           kinds: dict[str, str] | None = None, **run_kw) -> list[RuleAblation]:
    """Every applicable property in `properties` (not just the entry's expected_properties) is read before and after."""
    which, na = applicable_which(inst, properties, kinds)
    base = base_report(inst, properties, k, which, **run_kw)
    bv = _verdicts(base)
    out = []
    for rule in inst.rules:
        variants = [("deleted", rule.id)] + ([("prohibited", rule.id + "~prohibit")] if rule.deontic == "may" else [])
        for variant, rid in variants:
            ab = RuleAblation(rule_id=rid, deontic=rule.deontic if variant == "deleted" else "must_not", strand=rule.strand,
                              implicit=rule.implicit, permission_removed=False, variant=variant, k=k,
                              applicable=len(which), not_applicable=na, check_kinds={n: c[0] for n, c in which.items()},
                              check_sources={n: check_source(n, inst, kinds, properties)[1] for n in which})
            if variant == "deleted":
                inst2, ab.orphaned_or_else = without_rule(inst, rule.id)
                if rule.deontic in ("may", "must") and aim_kind(rule, inst) == "action":
                    ab.deregulated = parse_aim(rule.aim).pred not in regulated_actions(inst2)
                ab.permission_removed = rule.deontic == "may" and not ab.deregulated
            else:
                inst2, ab.orphaned_or_else = prohibited(inst, rule.id)
                ab.permission_removed = True
            _fill(ab, inst2, properties, k, which, base, bv, **run_kw)
            out.append(ab)
    return out


def _fill(ab, inst2, properties, k, which, base, bv, **run_kw) -> None:
    rep = rules_checks.run_all(inst2, properties, k=k, which=which, **run_kw)
    if rep.consistent == "unsat" and base.consistent != "unsat":
        ab.inconsistent_after = True
        return
    av = _verdicts(rep)
    fam_all, fam_up, fam_down, goods = set(), set(), set(), set()
    for name, b in bv.items():
        a = av.get(name)
        before, after = effective_verdict(b), (effective_verdict(a) if a else None)
        if before is None or after is None:
            ab.uncounted.append(name)
            continue
        if before == after:
            continue
        ab.flips.append((name, before, after))
        kind = properties[name].kind if name in properties else "structure"
        fam = (properties[name].family if name in properties else name)
        if kind == "freedom":
            fam_all.add(fam)
            d = ab.flip_directions[name] = flip_direction(name, before, after)
            if d == "freedom_up":
                fam_up.add(fam)
            elif d == "freedom_down":
                fam_down.add(fam)
        elif kind == "goods":
            goods.add(fam)
        elif kind == "structure":
            ab.structure_flips.append(name)
        else:
            ab.failure_mode_flips.append(name)
    ab.families_up, ab.families_down = sorted(fam_up), sorted(fam_down)
    ab.load_freedom, ab.load_freedom_up, ab.load_freedom_down = len(fam_all), len(fam_up), len(fam_down)
    ab.load_freedom_unsigned = len(fam_all - fam_up - fam_down)
    ab.load_goods = len(goods)


@dataclass
class MultiKAblation:
    rule_id: str
    by_k: dict[int, RuleAblation]
    k_disagreement: list[str]  # properties whose (before, after) pair, or whose flip status, differs across k

    @property
    def deontic(self) -> str:
        return next(iter(self.by_k.values())).deontic

    def loads(self) -> dict[int, tuple[int, int]]:
        return {k: (a.load_freedom, a.load_goods) for k, a in self.by_k.items()}

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "k_disagreement": self.k_disagreement,
                "loads": {str(k): {"load_freedom": a[0], "load_goods": a[1],
                                   "load_freedom_up": self.by_k[k].load_freedom_up, "load_freedom_down": self.by_k[k].load_freedom_down}
                          for k, a in self.loads().items()},
                "by_k": {str(k): a.to_dict() for k, a in self.by_k.items()}}


def ablate_multi_k(inst: InstitutionJSON, properties: dict[str, Property], ks: tuple[int, ...] = (6, 8),
                   kinds: dict[str, str] | None = None, **run_kw) -> list[MultiKAblation]:
    per_k = {k: {a.rule_id: a for a in ablate(inst, properties, k, kinds, **run_kw)} for k in ks}
    out = []
    for rid in per_k[ks[0]]:
        by_k = {k: per_k[k][rid] for k in ks}
        names = set()
        for a in by_k.values():
            names |= {f[0] for f in a.flips}
        dis = []
        for n in sorted(names):
            seen = {next(((f[1], f[2]) for f in a.flips if f[0] == n), None) for a in by_k.values()}
            if len(seen) > 1:
                dis.append(n)
        out.append(MultiKAblation(rid, by_k, dis))
    return out


def summarize(entries: dict[str, list[MultiKAblation]], ks: tuple[int, ...]) -> dict:
    """One row per entry: top ranked (non-deregulated, consistent) rules by load_freedom_up at ks[0], ties listed, plus counts
    of inconsistent_after and uncounted rows (any k)."""
    out = {}
    for eid, res in entries.items():
        k0 = ks[0]
        ranked = [m for m in res if not m.by_k[k0].deregulated and not m.by_k[k0].inconsistent_after]
        best = max((m.by_k[k0].load_freedom_up for m in ranked), default=0)
        out[eid] = {
            "k": k0, "top_load_freedom_up": best,
            "top_rules": sorted(m.rule_id for m in ranked if m.by_k[k0].load_freedom_up == best) if best > 0 else [],
            "deregulated_not_ranked": sorted(m.rule_id for m in res if m.by_k[k0].deregulated),
            "inconsistent_after": sum(a.inconsistent_after for m in res for a in m.by_k.values()),
            "uncounted": sum(len(a.uncounted) for m in res for a in m.by_k.values()),
        }
    return {"ks": list(ks), "entries": out,
            "totals": {"entries": len(out), "inconsistent_after": sum(e["inconsistent_after"] for e in out.values()),
                       "uncounted": sum(e["uncounted"] for e in out.values())}}
