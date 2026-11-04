"""Phase 0 gate for the institutions family (plan: plans/institutions-phase0.md, "Phase 0 gate" and the
Extension section's "Extra gate criterion (f)"; tightened after docs/reviews/2026-11-03-phase0-skeptical-review.md).
`phil rules gate`; exit 0 = PASS.

(a) all stages ran: every institution loads and its rules parse for iso + check (the LLM stages are not
    part of this gate yet: the dataset is `--from-human`); and no rule the dataset marks `load_bearing: true`
    is inert (a must-be nothing can break within k; review finding 3).
(b) cluster: for every `isomorphic_to` claim of coverture-household, police-crisis, cps, the pair is tested at
    exactly the claim's precommitted `level` (ADR 0010): full iso, or the care + control form
    (rules_iso.CareControl: care duty + rival may on the same subject + a must_not barring the subject's own
    action) whose pairs include the claim's `sub_signature`. A match found at any other level is printed under
    "findings" and does not count. crisis-team matches no cluster member at any level; and every institution in a
    cluster member's `not_isomorphic_to_control` (negative controls: a lease and one more) must not match it at
    the precommitted level either (review finding 4).
(c) minimal pair: paternity-quota / transferable-leave at rule_distance 1, the differing rule named, and the
    verdicts differ on exactly the preregistered property `minimal_pair_of.differs_on` (review finding 5a);
    other differences are findings.
(d) kibbutz-childrens-house: deferred until the institution is in the dataset.
(e) property-verdict agreement vs expected >= 60% (same numbers as `phil rules check-all`).
(f) cosmetic-reform detection: companion-guardian-renamed iso to companion-ownership as a pure rename;
    companion-guardianship not iso, distance exactly 1; and every human/non-human pair's report carries a
    matched sub-signature + unmatched list (a bare `iso: true` across that line fails).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rules_checks, rules_iso
from .schemas_rules import InstitutionJSON, IsoClaim, Property, RuleCheckReport

CLUSTER = ("coverture-household", "police-crisis", "cps")
UNBUNDLED = "crisis-team"
PAIR_C = ("paternity-quota", "transferable-leave")
KIBBUTZ = "kibbutz-childrens-house"
OWNERSHIP, GUARDIANSHIP, RENAMED = "companion-ownership", "companion-guardianship", "companion-guardian-renamed"
NON_HUMAN_PREFIXES = ("companion-", "industrial-dairy", "farmed-sanctuary", "habeas-personhood", "whaling-", "ai-")
AGREEMENT_MIN = 0.60


def is_non_human(inst_id: str) -> bool:
    return inst_id.startswith(NON_HUMAN_PREFIXES)


@dataclass
class Criterion:
    key: str
    status: str  # PASS | FAIL | deferred
    detail: str
    lines: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)  # true but not counted (wrong level, extra differences)


@dataclass
class GateReport:
    criteria: list[Criterion]
    agreement: float | None = None

    @property
    def passed(self) -> bool:
        return all(c.status != "FAIL" for c in self.criteria)


def _missing(by: dict, ids) -> list[str]:
    return [i for i in ids if i not in by]


def crit_a(insts: list[InstitutionJSON], reports: dict[str, RuleCheckReport] | None = None) -> Criterion:
    bad = []
    for i in insts:
        try:
            rules_iso.prepare(i)
        except Exception as e:  # parse errors in aims / conditions
            bad.append(f"{i.id}: {e}")
    lines, inert_lb = [], []
    for i in insts:
        rep = (reports or {}).get(i.id)
        if rep is None:
            continue
        for st in rep.rule_status:
            if st.kind != "inert":
                continue
            lines.append(f"  inert {i.id} {st.rule}{' (load_bearing)' if st.load_bearing else ''}: {st.detail}")
            if st.load_bearing:
                inert_lb.append(f"{i.id}:{st.rule}")
    if bad:
        return Criterion("a", "FAIL", f"{len(bad)} institution(s) failed to parse", bad + lines)
    if inert_lb:
        return Criterion("a", "FAIL", f"load-bearing rule(s) inert: {', '.join(inert_lb)}", lines)
    n_inert = sum(len(r.inert) for r in (reports or {}).values())
    return Criterion("a", "PASS", f"{len(insts)} institutions load and parse; {n_inert} inert must-be rule(s), none load-bearing "
                     f"(LLM stages not run: dataset is --from-human)", lines)


def _match_at(by: dict, a: str, b: str, level: str):
    """(IsoReport, CareControl | None) for the pair at the dataset's level spelling."""
    cond, strands = rules_iso.parse_level(level)
    r = rules_iso.match(by[a], by[b], strands, cond)
    return r, rules_iso.care_control_subsignature(r, by[a], by[b])


def _status(r, cc) -> str:
    return "iso" if r.iso else "partial(care+control)" if cc else "none"


def _claim_ok(r, cc, claim: IsoClaim) -> tuple[bool, str]:
    """Does the pair satisfy the claim at its own level? Full iso always does; otherwise the care+control form
    must be present and the matched sub-signature must contain every precommitted pair."""
    if r.iso:
        return True, "iso"
    if cc is None:
        return False, "no care+control form"
    want = claim.pairs()
    have = set(r.matched_sub_signature)
    miss = [f"{x}~{y}" for x, y in want if (x, y) not in have]
    if miss:
        return False, f"precommitted pairs not matched: {', '.join(miss)}"
    return True, "partial(care+control)"


def crit_b(by: dict) -> Criterion:
    miss = _missing(by, (*CLUSTER, UNBUNDLED))
    if miss:
        return Criterion("b", "FAIL", f"missing institutions {miss}")
    lines, findings, summary, ok = [], [], [], True
    claims_seen = 0
    for a in CLUSTER:
        for claim in by[a].iso_claims():
            b = claim.id
            if b not in CLUSTER or b not in by:
                continue
            claims_seen += 1
            try:
                r, cc = _match_at(by, a, b, claim.level)
            except ValueError as e:
                ok = False
                summary.append(f"{a}~{b}: {e}")
                continue
            good, why = _claim_ok(r, cc, claim)
            ok &= good
            summary.append(f"{a}~{b}@{claim.level}: {why}")
            lines.append(rules_iso.format_pair(r))
            lines.append("  " + rules_iso.format_care_control(cc, by[a], by[b]))
            for other in rules_iso.LEVELS:
                if other == claim.level:
                    continue
                r2, cc2 = _match_at(by, a, b, other)
                st = _status(r2, cc2)
                if st != "none" and not good:
                    findings.append(f"{a}~{b} matches at {other} ({st}) but the claim is at {claim.level}: not counted")
                elif st != "none" and other != claim.level and (r2.iso and not r.iso):
                    findings.append(f"{a}~{b} is fully iso at {other}; claim at {claim.level} is only {why}")
    if claims_seen == 0:
        ok = False
        summary.append("no isomorphic_to claims among the cluster")
    # the unbundled control matches nothing at any level
    for a in CLUSTER:
        for level in rules_iso.LEVELS:
            r, cc = _match_at(by, a, UNBUNDLED, level)
            st = _status(r, cc)
            if st != "none":
                ok = False
                summary.append(f"{a}~{UNBUNDLED}: {st}@{level}")
            if level == "guard+strands":
                lines.append(rules_iso.format_pair(r))
                lines.append("  " + rules_iso.format_care_control(cc, by[a], by[UNBUNDLED]))
        summary.append(f"{a}~{UNBUNDLED}: none at every level" if all(
            _status(*_match_at(by, a, UNBUNDLED, lv)) == "none" for lv in rules_iso.LEVELS) else f"{a}~{UNBUNDLED}: MATCH")
    # negative controls at the precommitted level(s) of the member's claims
    controls = 0
    for a in CLUSTER:
        levels = sorted({c.level for c in by[a].iso_claims()}) or ["guard+strands"]
        for ctl in by[a].not_isomorphic_to_control:
            if ctl not in by:
                ok = False
                summary.append(f"{a}: control {ctl!r} not in dataset")
                continue
            controls += 1
            for level in levels:
                r, cc = _match_at(by, a, ctl, level)
                st = _status(r, cc)
                lines.append(rules_iso.format_pair(r))
                lines.append("  " + rules_iso.format_care_control(cc, by[a], by[ctl]))
                if st != "none":
                    ok = False
                    summary.append(f"{a}~{ctl} (control): {st}@{level}")
                else:
                    summary.append(f"{a}~{ctl} (control): none@{level}")
    if controls == 0:
        ok = False
        summary.append("no negative controls (not_isomorphic_to_control) on any cluster member")
    return Criterion("b", "PASS" if ok else "FAIL", "; ".join(summary), lines, findings)


def crit_c(by: dict, reports: dict) -> Criterion:
    a, b = PAIR_C
    miss = _missing(by, PAIR_C)
    if miss:
        return Criterion("c", "FAIL", f"missing institutions {miss}")
    r = rules_iso.match(by[a], by[b])
    lines = [rules_iso.format_pair(r)]
    ok = r.rule_distance == 1 and not r.iso
    named = f"{a}:{','.join(r.unmatched_a) or '-'} vs {b}:{','.join(r.unmatched_b) or '-'}"
    pair = by[b].minimal_pair() or by[a].minimal_pair()
    prop = pair.differs_on if pair else None
    diff, findings = [], []
    if pair and pair.rule and pair.rule not in (r.unmatched_a + r.unmatched_b):
        findings.append(f"{a}~{b}: minimal_pair_of names rule {pair.rule}, the matcher left {named} unmatched "
                        f"(same skeleton; the distance is still {r.rule_distance})")
    ra, rb = reports.get(a), reports.get(b)
    if ra and rb:
        for p in sorted(set(by[a].expected_properties) | set(by[b].expected_properties)):
            va, vb = ra.verdict(p), rb.verdict(p)
            if va != vb:
                (diff if p == prop else findings).append(f"{p}: {va} vs {vb}")
    if prop is None:
        ok = False
        lines.append("  minimal_pair_of.differs_on is not set: the property the pair should differ on must be preregistered")
    else:
        ok &= bool(diff)
        lines.append(f"  preregistered property {prop}: " + (diff[0] if diff else "verdicts do NOT differ"))
    findings = [f if f.startswith(f"{a}~{b}:") else f"{a}~{b} also differ on {f} (not preregistered; not counted)" for f in findings]
    return Criterion("c", "PASS" if ok else "FAIL",
                     f"distance {r.rule_distance}, differing rule {named}; preregistered {prop or '?'}: "
                     f"{'differs' if diff else 'same'}; {len(findings)} other difference(s)", lines, findings)


def crit_d(by: dict) -> Criterion:
    if KIBBUTZ not in by:
        return Criterion("d", "deferred", f"{KIBBUTZ} not in dataset")
    return Criterion("d", "deferred", f"{KIBBUTZ} present but the persists + implicit-rule check is not wired yet")


def crit_e(insts: list[InstitutionJSON], reports: dict) -> tuple[Criterion, float | None]:
    scored = ok = 0
    for i in insts:
        rep = reports.get(i.id)
        if rep is None:
            continue
        for r in rep.results:
            exp = i.expected_properties.get(r.property)
            if not exp:
                continue
            scored += 1
            ok += rules_checks.normalize_expected(exp) == r.verdict
    if not scored:
        return Criterion("e", "FAIL", "no scored properties"), None
    agr = ok / scored
    st = "PASS" if agr >= AGREEMENT_MIN else "FAIL"
    return Criterion("e", st, f"agreement {ok}/{scored} = {agr:.0%} (min {AGREEMENT_MIN:.0%})"), agr


def crit_f(by: dict, insts: list[InstitutionJSON]) -> Criterion:
    miss = _missing(by, (OWNERSHIP, GUARDIANSHIP, RENAMED))
    if miss:
        return Criterion("f", "FAIL", f"missing institutions {miss}")
    lines, parts, ok = [], [], True
    r1 = rules_iso.match(by[OWNERSHIP], by[RENAMED])
    lines.append(rules_iso.format_pair(r1))
    good1 = r1.iso and r1.pure_rename
    parts.append(f"renamed~ownership iso={r1.iso} pure_rename={r1.pure_rename}")
    ok &= good1
    r2 = rules_iso.match(by[OWNERSHIP], by[GUARDIANSHIP])
    lines.append(rules_iso.format_pair(r2))
    good2 = (not r2.iso) and r2.rule_distance == 1
    parts.append(f"guardianship~ownership iso={r2.iso} distance={r2.rule_distance} "
                 f"({','.join(r2.unmatched_a)} vs {','.join(r2.unmatched_b)})")
    ok &= good2
    # every human / non-human pair: sub-signature printed, bare iso: true fails
    cross = 0
    for a in insts:
        for b in insts:
            if a.id >= b.id or is_non_human(a.id) == is_non_human(b.id):
                continue
            r = rules_iso.match(a, b)
            cross += 1
            lines.append(f"  cross {a.id} ~ {b.id}: iso={r.iso} matched={[f'{x}->{y}' for x, y in r.matched_sub_signature]} "
                         f"unmatched={r.unmatched_a}|{r.unmatched_b}")
            if r.iso and not r.matched_sub_signature:
                ok = False
                parts.append(f"bare iso across {a.id}~{b.id}")
            if r.iso:
                parts.append(f"iso across {a.id}~{b.id} (structural, sub-signature printed)")
    parts.append(f"{cross} human/non-human pairs printed with sub-signatures")
    return Criterion("f", "PASS" if ok else "FAIL", "; ".join(parts), lines)


def run_gate(insts: list[InstitutionJSON], props: dict[str, Property], k: int = rules_checks.DEFAULT_K,
             init: str | None = None, compliance: str = "strict", step_mode: str = "one") -> GateReport:
    by = {i.id: i for i in insts}
    reports = {}
    for i in insts:
        try:
            reports[i.id] = rules_checks.run_all(i, props, k=k, init=init, compliance=compliance, step_mode=step_mode)
        except Exception as e:  # keep the gate running; (e) scores what it can
            reports[i.id] = None
            print(f"warning: check failed for {i.id}: {e}")
    reports = {k_: v for k_, v in reports.items() if v is not None}
    crits = [crit_a(insts, reports), crit_b(by), crit_c(by, reports), crit_d(by)]
    ce, agr = crit_e(insts, reports)
    crits.append(ce)
    crits.append(crit_f(by, insts))
    return GateReport(crits, agr)


def format_gate(rep: GateReport, verbose: bool = False) -> str:
    rows = [("criterion", "status", "detail")]
    for c in rep.criteria:
        rows.append((c.key, c.status, c.detail))
    w0 = max(len(r[0]) for r in rows); w1 = max(len(r[1]) for r in rows)
    out = [f"{r[0]:<{w0}}  {r[1]:<{w1}}  {r[2]}" for r in rows]
    out.insert(1, "-" * (w0 + w1 + 4) + "-" * 40)
    out.append("")
    out.append(f"GATE {'PASS' if rep.passed else 'FAIL'}  (deferred criteria do not fail the gate)")
    findings = [(c.key, f) for c in rep.criteria for f in c.findings]
    if findings:
        out.append("")
        out.append("findings (true, not counted):")
        out.extend(f"  [{k}] {f}" for k, f in findings)
    if verbose:
        for c in rep.criteria:
            if c.lines:
                out.append("")
                out.append(f"[{c.key}]")
                out.extend(c.lines)
    return "\n".join(out)
