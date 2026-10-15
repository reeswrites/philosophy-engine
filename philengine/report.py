"""Markdown report + gate evaluation over one run."""
from __future__ import annotations

import json

from . import checks, config, senses, stage_iso
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
               "contested": bool(sel and sel.contested), "n_candidates": len(forms), "sel": sel, "rec": rec,
               "status": selection_status(sel), "judge_weak": bool(sel and getattr(sel, "judge_weak", False)),
               "diversity": (sel.diversity if sel and getattr(sel, "diversity", None) else None)}
        row["rejected_trivial"] = trivial_rejects(row)
        row["bridges"] = bridges_of(sel)
        row["bridges_text"] = bridges_text(row["bridges"])
        rows.append(row)
    return rows


def bridges_of(sel) -> list[dict]:
    """Round 4: per candidate, confessed bridges (formalizer notes / agreed judge flag) and, for expected-invalid
    controls, Z3-valid candidates that drop the control's own premise. [] when nothing was flagged."""
    if sel is None:
        return []
    out = []
    confessed = dict(getattr(sel, "confessed", {}) or {})
    for e in sel.ranking:
        idx = e.get("candidate_idx")
        if idx is None:
            continue
        flags = e.get("flags", [])
        q = confessed.get(str(idx)) or next((n[len("confessed bridge: "):] for n in e.get("notes", [])
                                             if n.startswith("confessed bridge: ")), None)
        if q or "formalization_adds_bridge" in flags:
            out.append({"candidate": idx, "kind": "confessed", "quote": q or "", "chosen": False,
                        "rejected": any(r.startswith("confessed bridge") for r in e.get("rejected_reasons", []))})
        red = next((n for n in e.get("notes", []) if n.startswith("control valid via redundancy")), None)
        if red:
            out.append({"candidate": idx, "kind": "control-redundancy", "quote": red, "chosen": False, "rejected": False})
    for b in out:
        fid = next((e.get("formalization_id") for e in sel.ranking if e.get("candidate_idx") == b["candidate"]), None)
        b["chosen"] = fid is not None and fid == sel.chosen_formalization_id
    return out


def bridges_text(bs: list[dict]) -> str:
    if not bs:
        return "-"
    parts = []
    for b in bs:
        tag = "chosen, verdict withheld" if b["chosen"] else ("rejected" if b["rejected"] else "flagged")
        if b["kind"] == "confessed":
            q = b["quote"].replace("|", "/")
            parts.append(f"c{b['candidate']} confessed ({tag}): \"{q[:80]}{'…' if len(q) > 80 else ''}\"")
        else:
            m = b["quote"].split("without ", 1)
            parts.append(f"c{b['candidate']} control valid without {m[1].split(' (')[0] if len(m) > 1 else '?'}")
    return "; ".join(parts)


def selection_status(sel) -> str:
    """Round-3 status; selections stored before it get a status derived from what they hold."""
    if sel is None:
        return "no selection"
    if getattr(sel, "status", ""):
        return sel.status
    if sel.chosen_formalization_id is not None:
        return "selected"
    if any(e.get("verdict") in ("valid", "refuted", "inconsistent") for e in sel.ranking):
        return "open: decided candidates all rejected"
    return "open: no decided candidate"


def diversity_text(d: dict | None) -> str:
    if not d or not d.get("n"):
        return "-"
    return f"{d['distinct']}/{d['n']}" + (f" ({d['distinct_pred_sets']} pred sets)" if d.get("distinct_pred_sets") != d["distinct"] else "")


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
    rows = per_argument(store, run_id)
    run = store.one("SELECT mock FROM run WHERE id=?", (run_id,))
    mock = bool(run and run["mock"])
    rt = sum(r["rejected_trivial"] for r in rows)
    smug = sum(smuggled_rejects(r) for r in rows)
    # (b) selection demonstrably rejects trivialized candidates: checker-trivial rejects, or judge hard rejects
    # whose flag is conclusion_smuggled. A mock run (canned responses) satisfies it vacuously.
    b_ok = mock or (rt + smug) >= 1
    # (c) verdict agreement vs expected >= GATE_AGREEMENT (rows with an expected verdict; n/a for mock runs,
    # whose canned responses say nothing about the arguments)
    exp_rows = [r for r in rows if r["expected"] is not None]
    n_agree = sum(1 for r in exp_rows if r["agree"])
    agreement = n_agree / len(exp_rows) if exp_rows else None
    c_ok = mock or agreement is None or agreement >= config.GATE_AGREEMENT
    return {"a_ok": a_ok, "missing_stages": missing, "failed": len(failed), "not_done": len(not_done),
            "rejected_trivial": rt, "rejected_smuggled": smug, "mock": mock, "b_ok": b_ok,
            "agreement": agreement, "n_agree": n_agree, "n_expected": len(exp_rows), "c_ok": c_ok,
            "passed": a_ok and b_ok and c_ok}


def smuggled_rejects(row: dict) -> int:
    """Candidates the judge hard-rejected with conclusion_smuggled (a trivialization the checker may not see)."""
    sel = row["sel"]
    if sel is None:
        return 0
    return sum(1 for e in sel.ranking
               if any(x.startswith("judge hard reject") and "conclusion_smuggled" in x
                      for x in e.get("rejected_reasons", [])))


def gate_summary(g: dict) -> str:
    ag = "n/a" if g["agreement"] is None else f"{g['agreement'] * 100:.0f}% ({g['n_agree']}/{g['n_expected']})"
    return (f"all stages ran with 0 failed jobs: {g['a_ok']}; (b) rejected_trivial={g['rejected_trivial']} + "
            f"judge conclusion_smuggled rejects={g['rejected_smuggled']}{' (mock: waived)' if g['mock'] else ''}: {g['b_ok']}; "
            f"(c) agreement {ag} vs >= {config.GATE_AGREEMENT * 100:.0f}%{' (mock: waived)' if g['mock'] else ''}: {g['c_ok']}")


def shared_reliance(store: Store, run_id: int, rows: list[dict] | None = None) -> list[dict]:
    """Per shared_id: the arguments citing it and, where the selected formalization is decided (valid/inconsistent),
    whether it actually NEEDS the premise (not in the Z3 `redundant_premises`). needed=None -> not determinable
    (open/refuted/no selection). `idle` = decided somewhere and needed nowhere."""
    rows = per_argument(store, run_id) if rows is None else rows
    by: dict[str, dict] = {}
    for r in rows:
        rec, sel = r["rec"], r["sel"]
        if not rec:
            continue
        chosen, unverified = None, False
        if sel and sel.chosen_formalization_id:
            chosen = store.get_formalization(sel.chosen_formalization_id)
        elif sel and sel.verdict == "open":  # round 3: `open` arguments use their best parsed decided candidate, tagged
            chosen = stage_iso.top_parsed_candidate(store, rec.id)
            unverified = chosen is not None
        verdict = (checks.verdict_of(chosen.check) if unverified else sel.verdict) if chosen else (sel.verdict if sel else None)
        decided = bool(chosen and chosen.check and chosen.check.parse_ok and verdict in ("valid", "inconsistent"))
        for p in rec.reconstruction.premises:
            if not p.shared_id:
                continue
            d = by.setdefault(p.shared_id, {"shared_id": p.shared_id, "text": p.text, "arguments": []})
            needed = (p.id not in chosen.check.redundant_premises) if decided else None
            d["arguments"].append({"argument": r["id"], "label": p.id, "verdict": sel.verdict if sel else None,
                                   "needed": needed, "unverified": bool(unverified and decided),
                                   "candidate_verdict": verdict if unverified else None})
    out = []
    for sid in sorted(by):
        d = by[sid]
        dec = [a for a in d["arguments"] if a["needed"] is not None]
        ver = [a for a in dec if not a["unverified"]]
        d.update(n_args=len(d["arguments"]), n_decided=len(dec), n_needed=sum(1 for a in dec if a["needed"]),
                 n_unverified=sum(1 for a in dec if a["unverified"]),
                 idle=bool(dec) and not any(a["needed"] for a in dec),
                 idle_verified=bool(ver) and not any(a["needed"] for a in ver))
        out.append(d)
    return out


def _pairs(ps) -> str:
    return ", ".join(sorted("~".join(sorted(p)) for p in ps)) or "-"


def build_report(store: Store, run_id: int) -> str:
    rows = per_argument(store, run_id)
    run = store.one("SELECT * FROM run WHERE id=?", (run_id,))
    out = [f"# Phase 0 report (run {run_id}{', mock' if run and run['mock'] else ''})", ""]
    g = gate(store, run_id)
    out += [f"Gate: **{'PASS' if g['passed'] else 'FAIL'}** ({gate_summary(g)})", ""]
    out += ["## Arguments", "",
            "Verdicts are validity *as formalized*; `refuted` = invalid as formalized, not unsound. "
            "`inconsistent` = the selected formalization's premises are unsat (a finding, scored against expected "
            "`inconsistent` directly).", "",
            "`status`: `selected`; `judge-weak` = decided by Z3 and selected, but the judge mean score is below "
            f"{config.JUDGE_MEAN_SCORE} (a penalty, not a filter); `open: decided candidates all rejected` = a "
            "Z3-decided candidate existed and every candidate was rejected (hard judge flag, triviality, parse). "
            "`diversity` = distinct candidates (by normalized formulas + predicate set) / candidates. "
            "`confessed bridges` (round 4) = candidates whose formalizer notes (or an agreed judge "
            "`formalization_adds_bridge` flag) admit a formula goes beyond a stated premise: never selected over a "
            "faithful Z3-decided sibling; `needs bridge: <quote>` status = every survivor confesses, verdict withheld. "
            "Also lists, for expected-invalid controls, candidates Z3-valid without the control's own premise.", "",
            "| argument | expected | selected | agree | status | contested | rejected_trivial | candidates | diversity | confessed bridges |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ag = {True: "yes", False: "NO", None: "-"}[r["agree"]]
        out.append(f"| {r['id']} | {r['expected']} | {r['selected'] or '-'} | {ag} | {r['status']} | "
                   f"{'yes' if r['contested'] else ''} | {r['rejected_trivial']} | {r['n_candidates']} | "
                   f"{diversity_text(r['diversity'])} | {r['bridges_text']} |")
    dec = [r for r in rows if r["agree"] is not None]
    out += ["", f"Agreement: {sum(1 for r in dec if r['agree'])}/{len(rows)} "
                f"(undecided/no selection: {len(rows) - len(dec)})", ""]
    contested = [r["id"] for r in rows if r["contested"]]
    out += [f"Contested: {', '.join(contested) or 'none'}", ""]
    weak = [r["id"] for r in rows if r["status"] == "judge-weak"]
    rej = [r["id"] for r in rows if r["status"] == "open: decided candidates all rejected"]
    bridged = [r["id"] for r in rows if r["status"].startswith("needs bridge")]
    conf = [r["id"] for r in rows if any(b["kind"] == "confessed" for b in r["bridges"])]
    ctrl = [r["id"] for r in rows if any(b["kind"] == "control-redundancy" for b in r["bridges"])]
    out += [f"Decided by Z3 but judge-weak (selected, mean < {config.JUDGE_MEAN_SCORE}): {', '.join(weak) or 'none'}", "",
            f"Open with a Z3-decided candidate (all rejected): {', '.join(rej) or 'none'}", "",
            f"Confessed bridges (round 4): {', '.join(conf) or 'none'}; verdict withheld (needs bridge): "
            f"{', '.join(bridged) or 'none'}; controls valid only by dropping their own premise: {', '.join(ctrl) or 'none'}", ""]
    divs = [r["diversity"] for r in rows if r["diversity"] and r["diversity"].get("n")]
    if divs:
        ident = [r["id"] for r in rows if r["diversity"] and r["diversity"].get("n", 0) > 1 and r["diversity"].get("distinct") == 1]
        mean_ratio = sum(d["ratio"] for d in divs) / len(divs)
        out += [f"Candidate diversity: mean distinct/n = {mean_ratio:.2f}; all candidates identical in: "
                f"{', '.join(ident) or 'none'}", ""]

    out += ["## Objection coverage", "", "| argument | objections | targeting a premise | argument-level |", "|---|---|---|---|"]
    for aid in store.argument_ids():
        rels = [r for r in store.relations("attacks") if (r["evidence"] or {}).get("argument_id") == aid]
        n = len(rels)
        p = sum(1 for r in rels if r["dst_kind"] == "premise")
        out.append(f"| {aid} | {n} | {p} | {n - p} |")

    sr = shared_reliance(store, run_id, rows)
    if sr:
        out += ["", "## Shared premise reliance", "",
                "Per shared premise: arguments citing it, and in how many of the decided ones (valid/inconsistent) the "
                "chosen formalization actually needs it (not in `redundant_premises`).", "",
                "`open` arguments count through their best parsed valid/inconsistent candidate, marked `*` (unverified: "
                "the candidate was not selected), as in the isomorphism stage.", "",
                "| shared_id | arguments citing | needed in | idle in |", "|---|---|---|---|"]
        for d in sr:
            cite = ", ".join(f"{a['argument']}:{a['label']}" for a in d["arguments"])
            idle_in = ", ".join(a["argument"] + ("*" if a["unverified"] else "")
                                for a in d["arguments"] if a["needed"] is False) or "-"
            unv = f"; {d['n_unverified']} unverified" if d.get("n_unverified") else ""
            out.append(f"| {d['shared_id']} | {cite} | {d['n_needed']}/{d['n_decided']} (of {d['n_args']} citing{unv}) | {idle_in} |")
        idle = [d["shared_id"] + ("" if d["idle_verified"] else "*") for d in sr if d["idle"]]
        out += ["", f"Formally idle shared premises (cited, decided, needed nowhere; `*` = only with unverified "
                    f"candidates counted): {', '.join(idle) or 'none'}"]

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
            f"| precision | {fmt(ev['precision'])} |", f"| recall | {fmt(ev['recall'])} |",
            f"| unverified (candidate not selected) | {_pairs(ev['unverified'])} |",
            f"| unverified, shape-only | {_pairs(ev['unverified_weak'])} |",
            f"| relaxed pass (guard-abstracted, Z3-confirmed) | {_pairs(ev['relaxed'])} |",
            f"| relaxed, in truth | {_pairs(ev['relaxed_tp'])} |",
            f"| relaxed, not in truth | {_pairs(ev['relaxed_fp'])} |",
            f"| relaxed, shape-only | {_pairs(ev['relaxed_weak'])} |",
            f"| projected pass (cluster-collapsed / arity-projected, Z3-confirmed) | {_pairs(ev['projected'])} |",
            f"| projected, in truth | {_pairs(ev['projected_tp'])} |",
            f"| projected, not in truth | {_pairs(ev['projected_fp'])} |",
            f"| precision incl. unverified + relaxed + projected | {fmt(ev['precision_all'])} |",
            f"| recall incl. unverified + relaxed + projected | {fmt(ev['recall_all'])} |", "",
            "Relaxed pass (round 3): sorts erased, curried implications flattened, guard-only atoms dropped from "
            "antecedents that keep a substantive conjunct, Z3-redundant premises dropped, binder order canonicalized, "
            "binary argument order free; still Z3-confirmed on the relaxed formulas. Strict precision/recall exclude it.", "",
            "Projected pass (round 4, after the relaxed pass): atoms that always occur together as co-conjuncts with "
            "the same arguments are collapsed into one predicate (equivalence-preserving), then one argument position "
            "of a predicate is dropped where that makes the two arity profiles agree (a SPECIALIZATION, listed in the "
            "evidence as `arity-projected:`); Z3-confirmed on the projected formulas. Weaker than relaxed; reported "
            "separately.", ""]
    for r in store.relations("iso-skipped", **({"run_id": run_id} if run_id is not None else {})):
        why = (r["evidence"] or {}).get("reason", "")
        if r["dst_kind"] == "argument" and "declined" in why:
            out.append(f"- `{r['src_id']}~{r['dst_id']}` {why}")
    out += [""]
    out += [
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
