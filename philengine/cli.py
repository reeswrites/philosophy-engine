"""`phil` command line."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import config, report
from .pipeline import ALL_STAGES, run_all
from .store import Store

# USD per million tokens (input, output); only used if the model is listed.
PRICES: dict[str, tuple[float, float]] = getattr(config, "PRICES", {})


def _data_path(a) -> str:
    d = getattr(a, "data", None)
    if d:
        return d
    root = config.data_dir()
    p0 = root / "phase0" / "arguments.json"
    if p0.is_file():
        return str(p0)
    found = sorted(root.glob("*/arguments.json"))
    if len(found) == 1:
        return str(found[0])
    print(f"no argument family found under {root}; pass --data", file=sys.stderr)
    raise SystemExit(2)


def _db_path(a) -> str:
    if a.db:
        return a.db
    try:
        family = Path(_data_path(a)).parent.name
    except SystemExit:
        if hasattr(a, "data"):
            raise
        family = "phase0"
    return str(config.runs_dir() / f"{family}.db")


def _store(a) -> Store:
    return Store(_db_path(a))


def _run_id(st: Store, a) -> int | None:
    return a.run if getattr(a, "run", None) else st.latest_run()


def cmd_ingest(a) -> int:
    st = _store(a)
    n = st.ingest(_data_path(a))
    print(f"ingested {n} arguments into {_db_path(a)}")
    return 0


def cmd_run(a) -> int:
    st = _store(a)
    if not st.argument_ids():
        st.ingest(_data_path(a))
    options = {"from_human": bool(a.from_human)}
    if a.n_candidates:
        options["n_candidates"] = a.n_candidates
    run_id = a.run
    if run_id is None:
        run_id = st.latest_run() if (a.resume and st.latest_run() and not a.new_run) else None
    if run_id is None:
        run_id = st.new_run(options, mock=a.mock)
    if a.mock:
        from .llm import MockLLMClient
        llm = MockLLMClient(st, run_id)
    else:
        config.load_env()
        from .llm import LLMClient
        try:
            llm = LLMClient(st, run_id)
        except config.ConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    stages = ALL_STAGES if (not a.stage or "all" in a.stage) else tuple(s for s in ALL_STAGES if s in a.stage)
    out = run_all(st, run_id, llm, a.args or None, stages, options, a.resume, a.retry_failed)
    print(f"run {run_id}")
    for s, r in out.items():
        print(f"  {s:12s} done={r.done} failed={r.failed} skipped={r.skipped} reset={r.reset}")
    return 0 if all(r.ok for r in out.values()) else 1


def cmd_status(a) -> int:
    st = _store(a)
    rid = _run_id(st, a)
    if rid is None:
        print("no runs")
        return 1
    print(f"run {rid}")
    for s in ALL_STAGES:
        c = Counter(j["status"] for j in st.jobs(rid, s))
        print(f"  {s:12s} " + (" ".join(f"{k}={v}" for k, v in sorted(c.items())) or "(no jobs)"))
    for j in st.jobs(rid):
        if j["status"] == "failed":
            print(f"  FAILED {j['stage']} {j['argument_id']}#{j['candidate_idx']}: {j['error']}")
    return 0


def cmd_show(a) -> int:
    st = _store(a)
    rid = _run_id(st, a) or 0
    try:
        arg = st.get_argument(a.arg_id)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1
    rec = report._recon(st, rid, a.arg_id)
    print(f"# {a.arg_id}: {arg.get('name')} (expected: {arg.get('expected_verdict')})")
    if not rec:
        print("no reconstruction")
        return 1
    print(f"\nReconstruction #{rec.id} [{rec.source}]")
    for p in rec.reconstruction.premises:
        print(f"  [{p.id}] ({p.type}{', implicit' if p.implicit else ''}) {p.text}")
    print(f"  [C] {rec.reconstruction.conclusion}")
    sel = st.get_selection(rec.id)
    rank = {e.get("formalization_id"): (i + 1, e) for i, e in enumerate(sel.ranking)} if sel else {}
    for f in st.list_formalizations(rec.id):
        pos, e = rank.get(f.id, (None, {}))
        print(f"\n-- candidate {f.candidate_idx} (formalization {f.id}, {f.status})"
              + (f"  rank {pos}  score {e.get('score')}" if pos else "")
              + ("  << CHOSEN" if sel and sel.chosen_formalization_id == f.id else ""))
        if e.get("notes"):
            print("   notes: " + " | ".join(e["notes"]))
        if e.get("rejected_reasons"):
            print("   rejected: " + " | ".join(e["rejected_reasons"]))
        if f.formalization:
            fm = f.formalization
            for p in fm.premises:
                print(f"   {p.premise_id}: {p.sexpr}")
            print(f"   C: {fm.conclusion.sexpr}")
            if fm.notes:
                print(f"   notes: {fm.notes}")
        if f.check:
            c = f.check
            print(f"   check: parse_ok={c.parse_ok} consistent={c.consistent} valid={c.valid} minimal={c.minimal} "
                  f"nontrivial={c.nontrivial} vacuous={c.vacuous} redundant={c.redundant_premises}")
            if c.trivial_reasons:
                print(f"   trivial: {c.trivial_reasons}")
            if c.parse_errors:
                print(f"   parse errors: {c.parse_errors}")
            if c.valid == "refuted" and c.countermodel_text:
                print("   countermodel:\n      " + c.countermodel_text.replace("\n", "\n      "))
        if f.judge:
            j = f.judge
            print(f"   judge: mean={j.mean_score:.2f} min={j.min_score:.2f} concl={j.conclusion_score:.2f} "
                  f"flags={list(j.flags)} hard_reject={getattr(j, 'hard_reject', False)}")
            v = getattr(j, "verbalization", "")
            if v:
                print("   verbalization:\n      " + v.replace("\n", "\n      "))
            for k, t in j.back_translations.items():
                print(f"   back-translation {k} ({j.scores.get(k, j.conclusion_score if k == 'C' else '?')}): {t}")
    if sel:
        print(f"\nSelection: verdict={sel.verdict} chosen={sel.chosen_formalization_id} "
              f"contested={sel.contested} rejected_trivial={sel.rejected_trivial} rejected_judge={sel.rejected_judge}")
    return 0


def cmd_calls(a) -> int:
    st = _store(a)
    rows = st.llm_calls(stage=a.stage, argument_id=a.arg)
    agg: dict[tuple, dict] = {}
    for r in rows:
        d = agg.setdefault((r["stage"], r["model"]), {"n": 0, "in": 0, "out": 0, "err": 0, "cached": 0})
        d["n"] += 1
        d["in"] += r["input_tokens"] or 0
        d["out"] += r["output_tokens"] or 0
        d["err"] += 1 if r["error"] else 0
        d["cached"] += 1 if (r["latency_ms"] == 0 and r["model"] != "mock") else 0
    print(f"{'stage':12s} {'model':22s} {'calls':>6s} {'cached':>6s} {'errors':>6s} {'in_tok':>9s} {'out_tok':>9s} cost_usd")
    tot = 0.0
    priced = False
    for (s, m), d in sorted(agg.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        cost = ""
        if m in PRICES:
            c = (d["in"] * PRICES[m][0] + d["out"] * PRICES[m][1]) / 1e6
            tot += c
            priced = True
            cost = f"{c:.4f}"
        print(f"{s or '-':12s} {m or '-':22s} {d['n']:6d} {d['cached']:6d} {d['err']:6d} {d['in']:9d} {d['out']:9d} {cost}")
    print(f"total calls: {len(rows)}" + (f"  est cost: ${tot:.4f}" if priced else ""))
    return 0


def cmd_report(a) -> int:
    st = _store(a)
    rid = _run_id(st, a)
    if rid is None:
        print("no runs", file=sys.stderr)
        return 1
    md = report.build_report(st, rid)
    if a.out:
        from pathlib import Path
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md)
        print(f"wrote {a.out}")
    else:
        print(md)
    return 0


def cmd_gate(a) -> int:
    st = _store(a)
    rid = _run_id(st, a)
    if rid is None:
        print("GATE: FAIL (no runs)")
        return 1
    g = report.gate(st, rid)
    print(f"run {rid}")
    print(f"(a) all five stages ran with 0 failed jobs: {'OK' if g['a_ok'] else 'NO'}"
          f" (missing stages: {g['missing_stages'] or 'none'}; failed: {g['failed']}; not done: {g['not_done']})")
    print(f"(b) selection rejected >=1 trivialized candidate (checker trivial/vacuous, or judge hard-flag conclusion_smuggled;"
          f" mock runs waive): {'OK' if g['b_ok'] else 'NO'}"
          f" (rejected_trivial = {g['rejected_trivial']}, judge conclusion_smuggled rejects = {g['rejected_smuggled']}, mock = {g['mock']})")
    ag = "n/a" if g["agreement"] is None else f"{g['agreement'] * 100:.0f}% ({g['n_agree']}/{g['n_expected']})"
    print(f"(c) verdict agreement vs expected >= {config.GATE_AGREEMENT * 100:.0f}% (mock runs waive): {'OK' if g['c_ok'] else 'NO'}"
          f" (agreement = {ag})")
    print(f"GATE: {'PASS' if g['passed'] else 'FAIL'}")
    return 0 if g["passed"] else 1


def cmd_dashboard(a) -> int:
    from . import dashboard
    st = _store(a)
    rid = _run_id(st, a)
    if rid is None:
        print("no runs", file=sys.stderr)
        return 1
    print(f"wrote {dashboard.write_dashboard(st, rid, a.out or str(config.runs_dir() / "dashboard.html"))}")
    return 0


def cmd_families(a) -> int:
    root = config.data_dir()
    found = sorted(root.glob("*/arguments.json"))
    if not found:
        print(f"no families under {root}", file=sys.stderr)
        return 1
    for f in found:
        try:
            n = len(json.loads(f.read_text()))
        except Exception:
            n = "?"
        print(f"{f.parent.name}\t{n} arguments\t{f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phil", description="philosophy-engine Phase 0")
    sub = p.add_subparsers(dest="cmd", required=True)

    def db(sp, run=False):
        sp.add_argument("--db", default=None)
        if run:
            sp.add_argument("--run", type=int, default=None)

    s = sub.add_parser("ingest"); db(s)
    s.add_argument("--data", default=None); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("run"); db(s, True)
    s.add_argument("--data", default=None)
    s.add_argument("--mock", action="store_true")
    s.add_argument("--from-human", action="store_true")
    s.add_argument("--n-candidates", type=int, default=None)
    s.add_argument("--stage", action="append", choices=[*ALL_STAGES, "all"])
    s.add_argument("--args", nargs="+", metavar="ID")
    s.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    s.add_argument("--retry-failed", action="store_true")
    s.add_argument("--new-run", action="store_true", help="start a fresh run instead of continuing the latest")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("status"); db(s, True); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("show"); db(s, True); s.add_argument("arg_id"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("calls"); db(s)
    s.add_argument("--stage"); s.add_argument("--arg"); s.set_defaults(fn=cmd_calls)
    s = sub.add_parser("report"); db(s, True); s.add_argument("--out"); s.set_defaults(fn=cmd_report)
    s = sub.add_parser("dashboard"); db(s, True)
    s.add_argument("--out", default=None); s.set_defaults(fn=cmd_dashboard)
    s = sub.add_parser("gate"); db(s, True); s.set_defaults(fn=cmd_gate)
    s = sub.add_parser("families", help="list <DATA_DIR>/*/arguments.json"); s.set_defaults(fn=cmd_families)
    from .cli_rules import register as _register_rules  # institutions family: `phil rules check[-all]`
    _register_rules(sub)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
