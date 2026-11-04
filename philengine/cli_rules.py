"""`phil rules ...`: bounded checks over data/institutions (registered from cli.py).

  phil rules check --inst ID [--k 6] [--prop NAME] [--init empty|free|declared] [--compliance strict|sanctioned]
                   [--step-mode one|many] [--trace] [--no-cache] [--timing]
  phil rules check-all [--k 6] [--init ...] [--compliance ...] [--step-mode ...] [--no-cache] [--timing]
  phil rules verdicts --out FILE [--k ..] [--init ..] [--compliance ..] [--step-mode ..] [--no-cache]   write a golden-verdict baseline
  phil rules diff --baseline FILE [--k ..] [--no-cache] [--json OUT] [--scoreboard PATH]   exit 1 if any verdict changed / row removed
  (check-all and diff also take --scoreboard PATH: append one markdown table row per run, see scoreboard.py)
  phil rules cache (stats|clear)     the content-addressed result cache under runs/rules-cache/
  phil rules iso (--pair A B | --all) [--with-strands] [--cond exact|guard] [--json]
  phil rules ablate [--k 6,8] [--entry ID] [--json PATH] [--summary PATH] [--init ...] [--compliance ...] [--step-mode ...]
  phil rules gate [--k 6] [--init ...] [--compliance ...] [--step-mode ...] [--verbose] [--json]
--init defaults to "declared" for an institution with defaults/initial/initial_free, else "empty".
Prints a compact table: institution, property, check, expected, got, match, flags, k, init; `flags` is `vacuous`
when an invariant / persists result has an unreachable antecedent or no subject ever exists (review finding 6).
Results are cached by content (rules_cache.py); --no-cache bypasses it, --timing prints z3 timings and cache hits.
Inert must-be rules (nothing can break them within k) are listed after the table. Exit code 1 if any mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import rules_ablate, rules_cache, rules_checks, rules_gate, rules_iso, rules_verdicts, scoreboard
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


def _timing_summary(reports: list[RuleCheckReport], cache) -> str:
    """Total z3 time, per-institution totals and the 5 slowest checks (build + solve ms, vacuity included)."""
    groups: dict[tuple, list[float]] = {}  # (institution, property, check) or (institution, "[phase]", "") -> [build, solve, queries]
    per_inst: dict[str, float] = {}
    for rep in reports:
        for t in rep.timing:
            ms = t.build_ms + t.solve_ms
            per_inst[rep.institution] = per_inst.get(rep.institution, 0.0) + ms
            key = (rep.institution, t.property, t.check) if t.property else (rep.institution, f"[{t.phase}]", "")
            g = groups.setdefault(key, [0.0, 0.0, 0, 0])
            g[0] += t.build_ms
            g[1] += t.solve_ms
            g[2] += 0 if t.cached else 1
            g[3] += t.retries
    total = sum(per_inst.values())
    lines = [f"timing: {total:.0f} ms build+solve over {sum(len(r.timing) for r in reports)} record(s), "
             f"wall {sum(r.z3_ms for r in reports)} ms"]
    for inst_id, ms in sorted(per_inst.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {inst_id:<40} {ms:9.1f} ms")
    lines.append("slowest 5 checks (institution, property, check: build / solve ms, queries, retries):")
    for (i, pr, ck), (b, sv, n, rt) in sorted(groups.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:5]:
        lines.append(f"  {i} / {pr}{(' / ' + ck) if ck else ''}: {b:.1f} / {sv:.1f}  q={n} retries={rt}")
    if cache is not None:
        lines.append(cache.summary())
    else:
        lines.append("cache: off (--no-cache)")
    return "\n".join(lines)


def _make_cache(a):
    return None if getattr(a, "no_cache", False) else rules_cache.RuleCache()


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
    cache = _make_cache(a)
    rep = rules_checks.run_all(inst, props, k=a.k, which=which, init=a.init, compliance=a.compliance, step_mode=a.step_mode,
                               cache=cache)
    if a.json:
        print(rep.model_dump_json(indent=1))
        return 0
    rows = _rows(inst, rep)
    _print_table(rows, rep.warnings, [rep])
    if a.timing:
        print()
        print(_timing_summary([rep], cache))
    if a.trace:
        print()
        print(_trace_text(rep))
    return 1 if any(r[5] == "NO" for r in rows) else 0


def cmd_check_all(a) -> int:
    t0 = time.monotonic()
    insts, props = _load(a)
    rows, warns, reps = [], [], []
    cache = _make_cache(a)
    for inst in insts:
        rep = rules_checks.run_all(inst, props, k=a.k, init=a.init, compliance=a.compliance, step_mode=a.step_mode,
                                   cache=cache)
        reps.append(rep)
        rows.extend(_rows(inst, rep))
        warns.extend(f"{inst.id}: {w}" for w in rep.warnings)
    if getattr(a, "scoreboard", None):
        scoreboard.append_row(a.scoreboard, _scoreboard_row("rules check-all", reps, t0, None))
    if a.json:
        print(json.dumps([json.loads(r.model_dump_json()) for r in reps], indent=1))
        return 0
    _print_table(rows, warns, reps)
    if a.timing:
        print()
        print(_timing_summary(reps, cache))
    return 1 if any(r[5] == "NO" for r in rows) else 0


def _run_reports(a, insts, props, k, init, compliance, step_mode):
    cache = _make_cache(a)
    return [rules_checks.run_all(i, props, k=k, init=init, compliance=compliance, step_mode=step_mode, cache=cache)
            for i in insts]


def _scoreboard_row(command: str, reps, t0: float, changes) -> dict:
    return {"date": scoreboard.today(), "engine": scoreboard.engine_commit(), "command": command,
            "rows": sum(len(r.results) for r in reps), "verdict_changes": "-" if changes is None else changes,
            "z3_unknowns": sum(1 for r in reps for x in r.results if x.z3_unknown),
            "wall_s": f"{time.monotonic() - t0:.1f}",
            "inconsistent": ",".join(r.institution for r in reps if r.consistent == "unsat") or "-"}


def cmd_verdicts(a) -> int:
    insts, props = _load(a)
    reps = _run_reports(a, insts, props, a.k, a.init, a.compliance, a.step_mode)
    base = rules_verdicts.make_baseline(reps, k=a.k, init=a.init, compliance=a.compliance, step_mode=a.step_mode)
    rules_verdicts.write_baseline(a.out, base)
    print(f"wrote {a.out}: {len(base['rows'])} rows, engine_hash {base['engine_hash'][:12]}")
    return 0


def cmd_diff(a) -> int:
    t0 = time.monotonic()
    try:
        base = rules_verdicts.load_baseline(a.baseline)
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    bp = base["params"]
    k = a.k if a.k is not None else bp["k"]
    init = a.init if a.init is not None else bp["init"]
    compliance = a.compliance if a.compliance is not None else bp["compliance"]
    step_mode = a.step_mode if a.step_mode is not None else bp["step_mode"]
    insts, props = _load(a)
    reps = _run_reports(a, insts, props, k, init, compliance, step_mode)
    d = rules_verdicts.diff_rows(rules_verdicts.baseline_rows(base), rules_verdicts.rows_from_reports(reps))
    d["params"] = {"k": k, "init": init, "compliance": compliance, "step_mode": step_mode}
    d["baseline_engine_hash"] = base.get("engine_hash")
    d["engine_hash"] = rules_cache.code_hash()
    print(rules_verdicts.format_diff(d))
    if d["baseline_engine_hash"] != d["engine_hash"]:
        print("note: engine source hash differs from the baseline's", file=sys.stderr)
    if d["params"] != bp:
        print(f"note: parameters differ from the baseline's {bp}", file=sys.stderr)
    if a.json_out:
        from pathlib import Path
        Path(a.json_out).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    if a.scoreboard:
        scoreboard.append_row(a.scoreboard, _scoreboard_row("rules diff", reps, t0, len(d["changed"])))
    return 0 if d["ok"] else 1


def cmd_cache(a) -> int:
    c = rules_cache.RuleCache()
    if a.action == "clear":
        print(f"removed {c.clear()} cache file(s) from {c.root}")
        return 0
    st = c.stats()
    print(f"{st['root']}: {st['entries']} entr{'y' if st['entries'] == 1 else 'ies'}, {st['bytes']} bytes, "
          f"by kind {st['by_kind']}, schema {st['schema']}, code hash {st['code_hash']}")
    return 0


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


def cmd_ablate(a) -> int:
    insts, props = _load(a)
    try:
        ks = tuple(int(x) for x in a.k.split(","))
    except ValueError:
        print(f"--k {a.k!r}: expected comma-separated integers, e.g. 6,8", file=sys.stderr)
        return 2
    all_insts = insts
    if a.entry:
        insts = [i for i in insts if i.id in a.entry]
        if not insts:
            print(f"no entry matches {a.entry}", file=sys.stderr)
            return 2
    full = {}
    results = {}
    kinds = rules_ablate.check_kinds(all_insts)
    hdr = ("rule", "deontic", "strand", "load_freedom", "up/down", "mixed", "load_goods", "note", "orphaned_or_else", "k-disagree", "flips")

    def row(m):
        first = m.by_k[ks[0]]
        lf = "/".join(str(m.by_k[k].load_freedom) for k in ks)
        ud = "/".join(f"{m.by_k[k].load_freedom_up}+{m.by_k[k].load_freedom_down}" for k in ks)
        mx = "/".join(str(m.by_k[k].load_freedom_mixed) for k in ks)
        lg = "/".join(str(m.by_k[k].load_goods) for k in ks)
        if first.inconsistent_after:
            summ = "inconsistent after deletion (no compliant trace)"
        else:
            summ = ", ".join(f"{n}:{b}>{c}[{first.flip_directions.get(n, '')}]" if first.flip_directions.get(n) else f"{n}:{b}>{c}"
                             for n, b, c in first.flips) or "-"
        note = ("deregulated (action becomes unregulated: always enabled, derived power zeroed)" if first.deregulated
                else "prohibit leaks off-condition (sole regulator): not ranked" if first.offcondition_free
                else "prohibited" if first.variant == "prohibited"
                else "permission removed" if first.permission_removed else "-")
        if first.load_freedom_down > 0 and first.load_freedom_up == 0 and not (first.deregulated or first.offcondition_free):
            note = "load-bearing protection" if note == "-" else note + "; load-bearing protection"
        return (m.rule_id, first.deontic, first.strand, lf, ud, mx, lg, note,
                ",".join(first.orphaned_or_else) or "-", ",".join(m.k_disagreement) or "-", summ)

    def table(rows):
        widths = [max(len(str(x[i])) for x in [hdr, *rows]) for i in range(len(hdr))]
        fmt = "  ".join("{:<%d}" % w for w in widths)
        print(fmt.format(*hdr))
        print(fmt.format(*["-" * w for w in widths]))
        for r in rows:
            print(fmt.format(*[str(x) for x in r]))

    for inst in insts:
        res = rules_ablate.ablate_multi_k(inst, props, ks, kinds, init=a.init, compliance=a.compliance, step_mode=a.step_mode)
        results[inst.id] = res
        r0 = res[0].by_k[ks[0]] if res else None
        full[inst.id] = {"applicable": r0.applicable if r0 else 0,
                         "not_applicable": r0.not_applicable if r0 else [],
                         "check_kinds": r0.check_kinds if r0 else {},
                         "rules": [m.to_dict() for m in res]}
        res.sort(key=lambda m: (-m.by_k[ks[0]].load_freedom_up, m.rule_id))
        napp = f"{r0.applicable} properties applicable, {len(r0.not_applicable)} not applicable" if r0 else "no rules"
        print(f"== {inst.id}  ({napp}; k={','.join(map(str, ks))}; loads shown per k; flips at k={ks[0]}; open means not found within k)")
        if r0:
            print("   check kinds: " + ", ".join(f"{n}={c}" + (f"[{r0.check_sources[n]}]" if r0.check_sources.get(n, "expected") != "expected" else "")
                                                for n, c in sorted(r0.check_kinds.items())) + "  ([src]: property=explicit check key, majority/suffix/default=fallback; unmarked = entry expectation)")
        table([row(m) for m in res if not (m.by_k[ks[0]].deregulated or m.by_k[ks[0]].offcondition_free)])
        dereg = [row(m) for m in res if m.by_k[ks[0]].deregulated or m.by_k[ks[0]].offcondition_free]
        if dereg:
            print("-- deregulated, not ranked (deleted rule was the action's last may/must, or the prohibit of a sole-regulator may leaks off-condition; loads shown, excluded from ranking)")
            table(dereg)
        print()
    if a.summary:
        from pathlib import Path
        Path(a.summary).write_text(json.dumps(rules_ablate.summarize(results, ks), indent=1))
        print(f"wrote {a.summary}")
    if a.json:
        from pathlib import Path
        Path(a.json).write_text(json.dumps({"ks": list(ks), "entries": full}, indent=1))
        print(f"wrote {a.json}")
    return 0


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

    def cache_flags(sp):
        sp.add_argument("--no-cache", action="store_true", help="bypass the result cache (neither read nor write)")
        sp.add_argument("--timing", action="store_true", help="print z3 timing: total, per institution, 5 slowest checks, cache hits")

    s = rs.add_parser("check"); common(s); cache_flags(s)
    s.add_argument("--inst", required=True)
    s.add_argument("--prop", default=None)
    s.add_argument("--trace", action="store_true", help="print counterexample traces")
    s.set_defaults(fn=cmd_check)
    s = rs.add_parser("check-all"); common(s); cache_flags(s)
    s.add_argument("--scoreboard", default=None, metavar="PATH", help="append one markdown table row for this run")
    s.set_defaults(fn=cmd_check_all)

    s = rs.add_parser("verdicts", help="write a golden-verdict baseline (sorted, timing-free JSON)"); common(s); cache_flags(s)
    s.add_argument("--out", required=True, metavar="FILE")
    s.set_defaults(fn=cmd_verdicts)

    s = rs.add_parser("diff", help="recompute and diff against a baseline; exit 1 on changed / removed rows")
    s.add_argument("--baseline", required=True, metavar="FILE")
    s.add_argument("--k", type=int, default=None, help="override the baseline's k")
    s.add_argument("--init", choices=["empty", "free", "declared"], default=None)
    s.add_argument("--compliance", choices=["strict", "sanctioned"], default=None)
    s.add_argument("--step-mode", choices=["one", "many"], default=None)
    s.add_argument("--institutions", default=None); s.add_argument("--properties", default=None)
    s.add_argument("--json", dest="json_out", default=None, metavar="OUT", help="write the diff as JSON")
    s.add_argument("--scoreboard", default=None, metavar="PATH")
    cache_flags(s)
    s.set_defaults(fn=cmd_diff)
    s = rs.add_parser("cache", help="result cache under runs/rules-cache/: stats | clear")
    s.add_argument("action", choices=["stats", "clear"])
    s.set_defaults(fn=cmd_cache)
    s = rs.add_parser("iso", help="rule-set isomorphism: bijection over roles, fluents, actions")
    s.add_argument("--pair", nargs=2, metavar=("A", "B"), default=None)
    s.add_argument("--all", action="store_true", help="matrix over every pair + the dataset's expectations")
    s.add_argument("--with-strands", action="store_true", help="also report with strand tags in the skeleton")
    s.add_argument("--cond", choices=list(rules_iso.COND_LEVELS), default=None,
                   help="condition level: exact (default) or guard (conditional vs unconditional only)")
    s.add_argument("--institutions", default=None); s.add_argument("--properties", default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_iso)
    s = rs.add_parser("ablate", help="delete each rule, report which property verdicts flip (load_freedom / load_goods)")
    for flag in ("--institutions", "--properties"):
        s.add_argument(flag, default=None)
    s.add_argument("--init", choices=["empty", "free", "declared"], default=None)
    s.add_argument("--compliance", choices=["strict", "sanctioned"], default="strict")
    s.add_argument("--step-mode", choices=["one", "many"], default="one")
    s.set_defaults(fn=cmd_ablate)
    s.add_argument("--k", default="6,8", help="comma-separated bounds (default 6,8)")
    s.add_argument("--entry", action="append", default=None, help="restrict to this institution id (repeatable)")
    s.add_argument("--json", default=None, metavar="PATH", help="write the full structure to PATH")
    s.add_argument("--summary", default=None, metavar="PATH",
                   help="write the per-entry ranking summary (top ranked rules, ties, inconsistent/uncounted counts) to PATH")
    s = rs.add_parser("gate", help="Phase 0 gate (a)-(f); exit 0 = PASS"); common(s)
    s.add_argument("--verbose", action="store_true", help="print the per-pair iso reports behind each criterion")
    s.set_defaults(fn=cmd_gate)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phil rules")
    register(p.add_subparsers(dest="cmd", required=True))
    return p
