"""Markdown report + gate evaluation over one run."""
from __future__ import annotations

import json

from . import senses, stage_iso
from .pipeline import ALL_STAGES
from .runner import Ctx
from .stage_common import pick_reconstruction
from .store import Store

AGREE = {"valid": "valid", "invalid": "refuted", "inconsistent": "inconsistent"}  # expected_verdict -> engine verdict


def run_options(store: Store, run_id: int) -> dict:
    r = store.one("SELECT config_json FROM run WHERE id=?", (run_id,))
    try:
        return json.loads(r["config_json"] or "{}") if r else {}
    except json.JSONDecodeError:
        return {}


def _recon(store, run_id, aid):
    try:
        return pick_reconstruction(Ctx(store, run_id, None, run_options(store, run_id)), aid)
    except LookupError:
        return None


def per_argument(store: Store, run_id: int) -> list[dict]:
    rows = []
    for aid in store.argument_ids():
        a = store.get_argument(aid)
        rec = _recon(store, run_id, aid)
        sel = store.get_selection(rec.id) if rec else None
        forms = store.list_formalizations(rec.id) if rec else []
        exp = a.get("expected_verdict")
        got = sel.verdict if sel else None
        agree = got == AGREE.get(exp, exp) if got else None
        row = {"id": aid, "expected": exp, "selected": got, "agree": agree,
               "contested": bool(sel and sel.contested), "n_candidates": len(forms), "sel": sel, "rec": rec}
        row["rejected_trivial"] = trivial_rejects(row)
        rows.append(row)
    return rows


def trivial_rejects(row: dict) -> int:
    """rejected_trivial for the gate. For an argument whose expected verdict is `inconsistent`, a candidate rejected
    only because its premises were unsat (a real finding, not trivialization) does not count; this also corrects
    selections stored before inconsistent candidates stopped being rejected."""
    sel = row["sel"]
    if sel is None:
        return 0
    if row["expected"] != "inconsistent":
        return sel.rejected_trivial
    n = 0
    for e in sel.ranking:
        for reason in e.get("rejected_reasons", []):
            if reason == "vacuous":
                continue
            if reason.startswith("trivial: "):
                rest = [x for x in reason[len("trivial: "):].split("; ") if not x.startswith("premises inconsistent")]
                if rest:
                    n += 1
                    break
    return n


def gate(store: Store, run_id: int) -> dict:
    jobs = store.jobs(run_id)
    by = {s: [j for j in jobs if j["stage"] == s] for s in ALL_STAGES}
    missing = [s for s in ALL_STAGES if not by[s]]
    failed = [j for j in jobs if j["status"] == "failed"]
    not_done = [j for j in jobs if j["status"] != "done"]
    a_ok = not missing and not failed and not not_done
    rt = sum(r["rejected_trivial"] for r in per_argument(store, run_id))
    b_ok = rt >= 1
    return {"a_ok": a_ok, "missing_stages": missing, "failed": len(failed), "not_done": len(not_done),
            "rejected_trivial": rt, "b_ok": b_ok, "passed": a_ok and b_ok}


def _pairs(ps) -> str:
    return ", ".join(sorted("~".join(sorted(p)) for p in ps)) or "-"


def build_report(store: Store, run_id: int) -> str:
    rows = per_argument(store, run_id)
    run = store.one("SELECT * FROM run WHERE id=?", (run_id,))
    out = [f"# Phase 0 report (run {run_id}{', mock' if run and run['mock'] else ''})", ""]
    g = gate(store, run_id)
    out += [f"Gate: **{'PASS' if g['passed'] else 'FAIL'}** (all stages ran with 0 failed jobs: {g['a_ok']}; "
            f"rejected_trivial total = {g['rejected_trivial']})", ""]
    out += ["## Arguments", "",
            "Verdicts are validity *as formalized*; `refuted` = invalid as formalized, not unsound. "
            "`inconsistent` = the selected formalization's premises are unsat (a finding, scored against expected "
            "`inconsistent` directly).", "",
            "| argument | expected | selected | agree | contested | rejected_trivial | candidates |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        ag = {True: "yes", False: "NO", None: "-"}[r["agree"]]
        out.append(f"| {r['id']} | {r['expected']} | {r['selected'] or '-'} | {ag} | "
                   f"{'yes' if r['contested'] else ''} | {r['rejected_trivial']} | {r['n_candidates']} |")
    dec = [r for r in rows if r["agree"] is not None]
    out += ["", f"Agreement: {sum(1 for r in dec if r['agree'])}/{len(rows)} "
                f"(undecided/no selection: {len(rows) - len(dec)})", ""]
    contested = [r["id"] for r in rows if r["contested"]]
    out += [f"Contested: {', '.join(contested) or 'none'}", ""]

    out += ["## Objection coverage", "", "| argument | objections | targeting a premise | argument-level |", "|---|---|---|---|"]
    for aid in store.argument_ids():
        rels = [r for r in store.relations("attacks") if (r["evidence"] or {}).get("argument_id") == aid]
        n = len(rels)
        p = sum(1 for r in rels if r["dst_kind"] == "premise")
        out.append(f"| {aid} | {n} | {p} | {n - p} |")

    ev = stage_iso.iso_eval(store, run_id)
    fmt = lambda x: "n/a" if x is None else f"{x:.2f}"  # noqa: E731
    out += ["", "## Isomorphism", "",
            "| metric | value |", "|---|---|",
            f"| truth pairs | {_pairs(ev['truth'])} |", f"| found pairs | {_pairs(ev['found'])} |",
            f"| true positives | {_pairs(ev['tp'])} |", f"| false positives | {_pairs(ev['fp'])} |",
            f"| false negatives | {_pairs(ev['fn'])} |",
            f"| shape-only (weak-isomorphic, not counted above) | {_pairs(ev['weak_found'])} |",
            f"| shape-only, graded weak (weak-correct) | {_pairs(ev['weak_correct'])} |",
            f"| shape-only, ungraded | {_pairs(ev['weak_other'])} |",
            f"| precision | {fmt(ev['precision'])} |", f"| recall | {fmt(ev['recall'])} |", "",
            "False friends (same skeleton hash, not in truth) vs `weak_isomorphic_to`:", "",
            "| pair | graded weak? |", "|---|---|"]
    ff = ev["false_friends"]
    for p in sorted(ff, key=lambda p: sorted(p)):
        out.append(f"| {'~'.join(sorted(p))} | {'yes' if p in ev['weak'] else 'no'} |")
    if not ff:
        out.append("| (none) | |")
    out.append(f"\nWeak pairs graded: {_pairs(ev['weak'])}; found among false friends: "
               f"{_pairs(ff & ev['weak'])}")

    # concept registry: count distinct arguments whose candidates declare the (label, sense)
    uses: dict[tuple, set] = {}
    for r in rows:
        if not r["rec"]:
            continue
        for f in store.list_formalizations(r["rec"].id):
            for p in (f.formalization.predicates if f.formalization else []):
                uses.setdefault((senses.normalize_label(p.name), senses.normalize_sense(p.sense)), set()).add(r["id"])
    out += ["", f"## Concept registry (run {run_id})", "", "| label | sense | gloss | #args |", "|---|---|---|---|"]
    for c in store.concepts(run_id):
        n = len(uses.get((c["label"], c["sense"]), ())) or (1 if c["first_seen"] else 0)
        out.append(f"| {c['label']} | {c['sense']} | {(c['gloss'] or '').replace('|', '/')} | {n} |")

    out += ["", f"## Review queue (run {run_id})", "", "| target | reason | state |", "|---|---|---|"]
    for q in store.reviews(run_id):
        out.append(f"| {q['target_kind']}:{q['target_id']} | {q['reason']} | {q['state']} |")
    return "\n".join(out) + "\n"
