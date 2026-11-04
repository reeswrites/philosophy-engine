"""`phil rules ...`: bounded checks over data/institutions (registered from cli.py).

  phil rules check --inst ID [--k 6] [--prop NAME] [--init empty|free|declared] [--compliance strict|sanctioned]
                   [--step-mode one|many] [--trace]
  phil rules check-all [--k 6] [--init ...] [--compliance ...] [--step-mode ...]
  phil rules iso (--pair A B | --all) [--with-strands] [--cond exact|guard] [--json]
  phil rules gate [--k 6] [--init ...] [--compliance ...] [--step-mode ...] [--verbose] [--json]
--init defaults to "declared" for an institution with defaults/initial/initial_free, else "empty".
Prints a compact table: institution, property, check, expected, got, match, flags, k, init; `flags` is `vacuous`
when an invariant / persists result has an unreachable antecedent or no subject ever exists (review finding 6).
Inert must-be rules (nothing can break them within k) are listed after the table. Exit code 1 if any mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import rules_checks, rules_gate, rules_iso
from .schemas_rules import InstitutionJSON, Property, RuleCheckReport, RulesLoadError, default_paths, load_institutions, load_properties


def _load(a) -> tuple[list[InstitutionJSON], dict[str, Property]]:
    ip, pp = default_paths()
    try:
        return load_institutions(a.institutions or ip), load_properties(a.properties or pp)
    except RulesLoadError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)


def _rows(inst: InstitutionJSON, rep: RuleCheckReport) -> list[tuple]:
    rows = []
    for r in rep.results:
        exp = inst.expected_properties.get(r.property)
        exp_n = rules_checks.normalize_expected(exp) if exp else None
        match = "-" if exp_n is None else ("yes" if exp_n == r.verdict else "NO")
        flags = []
        if r.vacuous:
            flags.append("vacuous")
            if r.antecedent_reachable is False:
                flags.append("antecedent-unreachable")
            if r.subject_exists is False:
                flags.append("no-subject")
        rows.append((inst.id, r.property, r.check, exp or "-", r.verdict, match, ",".join(flags) or "-", rep.bound_k, rep.init))
    return rows


def _print_table(rows: list[tuple], warnings: list[str], reports: list[RuleCheckReport]):
    hdr = ("institution", "property", "check", "expected", "got", "match", "flags", "k", "init")
    widths = [max(len(str(x[i])) for x in [hdr, *rows]) for i in range(len(hdr))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*hdr))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*[str(x) for x in r]))
    scored = [r for r in rows if r[5] != "-"]
    ok = sum(1 for r in scored if r[5] == "yes")
    if scored:
        print(f"\nagreement: {ok}/{len(scored)} = {ok / len(scored):.0%}")
    for rep in reports:
        if rep.consistent != "sat":
            print(f"{rep.institution}: consistent={rep.consistent}")
        if rep.conflicts:
            print(f"{rep.institution}: deontic conflicts {rep.conflicts}")
        for st in rep.rule_status:
            if st.kind == "inert":
                print(f"{rep.institution}: inert {st.rule}{' (load_bearing)' if st.load_bearing else ''}: {st.detail}")
    for w in dict.fromkeys(warnings):
        print(f"warning: {w}")
    if reports:
        inits = sorted({r.init for r in reports})
        print(f"z3 {reports[0].z3_version}, k={reports[0].bound_k}, init={','.join(inits)}, "
              f"compliance={reports[0].compliance}, step_mode={reports[0].step_mode}; "
              f"'open' means not reached within k, never 'safe'")


def _trace_text(rep: RuleCheckReport) -> str:
    out = []
    for r in rep.results:
        if r.trace:
            out.append(f"{r.property} [{r.check}] {r.verdict}: counterexample trace")
            for s in r.trace:
                out.append(f"  t={s.step} P={'T' if s.property_holds else 'F'}  fire: {', '.join(s.actions) or '-'}")
                out.append(f"       true: {', '.join(s.fluents) or '(nothing)'}")
        elif r.reason:
            out.append(f"{r.property} [{r.check}] {r.verdict}: {r.reason}")
    return "\n".join(out)


def cmd_check(a) -> int:
    insts, props = _load(a)
    by_id = {i.id: i for i in insts}
    if a.inst not in by_id:
        print(f"unknown institution {a.inst!r}; have {sorted(by_id)}", file=sys.stderr)
        return 2
    inst = by_id[a.inst]
    which = None
    if a.prop:
        if a.prop not in props:
            print(f"unknown property {a.prop!r}; have {sorted(props)}", file=sys.stderr)
            return 2
        exp = inst.expected_properties.get(a.prop)
        c = rules_checks.check_for_expected(exp) if exp else None
        which = {a.prop: [c] if c else list(rules_checks.CHECKS)}
    rep = rules_checks.run_all(inst, props, k=a.k, which=which, init=a.init, compliance=a.compliance, step_mode=a.step_mode)
    if a.json:
        print(rep.model_dump_json(indent=1))
        return 0
    rows = _rows(inst, rep)
    _print_table(rows, rep.warnings, [rep])
    if a.trace:
        print()
        print(_trace_text(rep))
    return 1 if any(r[5] == "NO" for r in rows) else 0


def cmd_check_all(a) -> int:
    insts, props = _load(a)
    rows, warns, reps = [], [], []
    for inst in insts:
        rep = rules_checks.run_all(inst, props, k=a.k, init=a.init, compliance=a.compliance, step_mode=a.step_mode)
        reps.append(rep)
        rows.extend(_rows(inst, rep))
        warns.extend(f"{inst.id}: {w}" for w in rep.warnings)
    if a.json:
        print(json.dumps([json.loads(r.model_dump_json()) for r in reps], indent=1))
        return 0
    _print_table(rows, warns, reps)
    return 1 if any(r[5] == "NO" for r in rows) else 0


def cmd_iso(a) -> int:
    insts, _props = _load(a)
    by = {i.id: i for i in insts}
    levels = [a.cond] if a.cond else ["exact"]
    strand_modes = [False, True] if a.with_strands else [False]
    if a.pair:
        x, y = a.pair
        for m in (x, y):
            if m not in by:
                print(f"unknown institution {m!r}; have {sorted(by)}", file=sys.stderr)
                return 2
        reps = [rules_iso.match(by[x], by[y], ws, lv) for lv in levels for ws in strand_modes]
        if a.json:
            print(json.dumps([r.to_dict() for r in reps], indent=1))
        else:
            for r in reps:
                print(rules_iso.format_pair(r))
                cc = rules_iso.care_control_subsignature(r, by[x], by[y])
                print("  " + rules_iso.format_care_control(cc, by[x], by[y]))
        return 0
    out = {}
    for lv in levels:
        for ws in strand_modes:
            reps = rules_iso.match_all(insts, ws, lv)
            out[(lv, ws)] = reps
            if not a.json:
                print(f"cond={lv} strands={'on' if ws else 'off'}  ({rules_iso.METHOD})")
                print(rules_iso.format_matrix(insts, reps))
                print()
    if a.json:
        print(json.dumps([{"cond": lv, "with_strands": ws, "pairs": [r.to_dict() for (p, q), r in reps.items() if p < q]}
                          for (lv, ws), reps in out.items()], indent=1))
    else:
        print("expectations (isomorphic_to at each claim's precommitted level; not_isomorphic_to at exact, strands off):")
        reps = out[(levels[0], False)]
        for i in insts:
            for claim in i.iso_claims():
                j = claim.id
                if j in by:
                    cond, ws = rules_iso.parse_level(claim.level)
                    r = rules_iso.match(by[i.id], by[j], ws, cond)
                    cc = rules_iso.care_control_subsignature(r, by[i.id], by[j])
                    st = "iso" if r.iso else "care+control" if cc else "NO"
                    print(f"  {i.id} iso {j} @{claim.level}: {st} (distance {r.rule_distance}, matched {len(r.matched_sub_signature)})")
            for j in i.not_isomorphic_to:
                if j in by:
                    r = reps[(i.id, j)]
                    print(f"  {i.id} not iso {j}: {'yes' if not r.iso else 'NO'} (distance {r.rule_distance})")
    return 0


def cmd_gate(a) -> int:
    insts, props = _load(a)
    rep = rules_gate.run_gate(insts, props, k=a.k, init=a.init, compliance=a.compliance, step_mode=a.step_mode)
    if a.json:
        print(json.dumps({"passed": rep.passed, "agreement": rep.agreement,
                          "criteria": [{"key": c.key, "status": c.status, "detail": c.detail, "lines": c.lines}
                                       for c in rep.criteria]}, indent=1))
    else:
        print(rules_gate.format_gate(rep, verbose=a.verbose))
    return 0 if rep.passed else 1


def register(sub) -> None:
    """Attach `rules` to the top-level `phil` subparsers."""
    p = sub.add_parser("rules", help="institutions family: bounded z3 checks over ADICO rules")
    rs = p.add_subparsers(dest="rules_cmd", required=True)

    def common(sp):
        sp.add_argument("--k", type=int, default=rules_checks.DEFAULT_K)
        sp.add_argument("--init", choices=["empty", "free", "declared"], default=None,
                        help="initial state: endogenous fluents false (empty), all free (free), or the institution's "
                             "defaults/initial/initial_free with everything else false (declared). Default: declared "
                             "when the institution has those fields, else empty")
        sp.add_argument("--compliance", choices=["strict", "sanctioned"], default="strict")
        sp.add_argument("--step-mode", choices=["one", "many"], default="one",
                        help="at most one action per step (one, default) or any set of enabled actions (many)")
        sp.add_argument("--institutions", default=None, help="path to institutions.json")
        sp.add_argument("--properties", default=None, help="path to properties.json")
        sp.add_argument("--json", action="store_true")

    s = rs.add_parser("check"); common(s)
    s.add_argument("--inst", required=True)
    s.add_argument("--prop", default=None)
    s.add_argument("--trace", action="store_true", help="print counterexample traces")
    s.set_defaults(fn=cmd_check)
    s = rs.add_parser("check-all"); common(s)
    s.set_defaults(fn=cmd_check_all)
    s = rs.add_parser("iso", help="rule-set isomorphism: bijection over roles, fluents, actions")
    s.add_argument("--pair", nargs=2, metavar=("A", "B"), default=None)
    s.add_argument("--all", action="store_true", help="matrix over every pair + the dataset's expectations")
    s.add_argument("--with-strands", action="store_true", help="also report with strand tags in the skeleton")
    s.add_argument("--cond", choices=list(rules_iso.COND_LEVELS), default=None,
                   help="condition level: exact (default) or guard (conditional vs unconditional only)")
    s.add_argument("--institutions", default=None); s.add_argument("--properties", default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_iso)
    s = rs.add_parser("gate", help="Phase 0 gate (a)-(f); exit 0 = PASS"); common(s)
    s.add_argument("--verbose", action="store_true", help="print the per-pair iso reports behind each criterion")
    s.set_defaults(fn=cmd_gate)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phil rules")
    register(p.add_subparsers(dest="cmd", required=True))
    return p
