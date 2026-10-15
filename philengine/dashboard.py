"""Static HTML dashboard: one self-contained file, data embedded as JSON, d3 from cdnjs for the graph."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from . import report, senses, stage_iso
from .pipeline import ALL_STAGES
from .store import Store
from .verbalize import symbol_legend, verbalize

D3_URL = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"


def _pairs(ps) -> list[list[str]]:
    return sorted(sorted(p) for p in ps)


def _cand(f, sel, rec) -> dict:
    from . import sexpr as sx
    rank = {e.get("formalization_id"): (i + 1, e) for i, e in enumerate(sel.ranking)} if sel else {}
    pos, e = rank.get(f.id, (None, {}))
    d = {"id": f.id, "idx": f.candidate_idx, "status": f.status, "rank": pos, "score": e.get("score"),
         "rejected_reasons": e.get("rejected_reasons", []), "notes": e.get("notes", []),
         "chosen": bool(sel and sel.chosen_formalization_id == f.id),
         "check": f.check.model_dump() if f.check else None,
         "judge": f.judge.model_dump() if f.judge else None,
         "formalization": None, "items": []}
    fm = f.formalization
    if fm:
        d["formalization"] = {"notes": fm.notes, "sorts": [s.model_dump() for s in fm.sorts],
                              "predicates": [p.model_dump() for p in fm.predicates],
                              "constants": [c.model_dump() for c in fm.constants]}
        try:
            eng = verbalize(fm)
        except Exception as ex:  # gloss/arity problems: still show S-expressions
            eng = {}
            d["verbalize_error"] = str(ex)
        for it in [*fm.premises, fm.conclusion]:
            label = "C" if it is fm.conclusion else it.premise_id
            try:
                leg = symbol_legend(sx.parse(it.sexpr), fm)
            except Exception:
                leg = ""
            d["items"].append({"id": label, "sexpr": it.sexpr, "english": eng.get(label, ""), "legend": leg})
    return d


def build_data(store: Store, run_id: int) -> dict:
    run = store.one("SELECT * FROM run WHERE id=?", (run_id,))
    rows = report.per_argument(store, run_id)
    g = report.gate(store, run_id)
    jobs = store.jobs(run_id)
    stage_counts = {s: dict(Counter(j["status"] for j in jobs if j["stage"] == s)) for s in ALL_STAGES}
    ev = stage_iso.iso_eval(store, run_id)
    iso_rel = {frozenset((r["src_id"], r["dst_id"])): r for r in store.relations("isomorphic-to", run_id=run_id)}
    hashes = stage_iso.skeleton_hashes(store, run_id)

    p_rows = store.query("SELECT * FROM premise")
    premises = {p["id"]: {"id": p["id"], "text": p["text"], "type": p["type"], "args": []} for p in p_rows}
    args, ap = [], store.query("SELECT * FROM argument_premise ORDER BY argument_id, ord")
    for r in ap:
        premises[r["premise_id"]]["args"].append({"argument": r["argument_id"], "label": r["label"],
                                                  "implicit": bool(r["implicit"])})
    uses: dict[tuple, set] = {}
    for r in rows:
        aid, rec, sel = r["id"], r["rec"], r["sel"]
        a = store.get_argument(aid)
        cands, pmap = [], {}
        if rec:
            cands = [_cand(f, sel, rec) for f in store.list_formalizations(rec.id)]
            for f in store.list_formalizations(rec.id):
                for p in (f.formalization.predicates if f.formalization else []):
                    uses.setdefault((senses.normalize_label(p.name), senses.normalize_sense(p.sense)), set()).add(aid)
        for x in ap:
            if x["argument_id"] == aid:
                pmap[x["label"]] = x["premise_id"]
        args.append({
            "id": aid, "name": a.get("name"), "author": a.get("author"), "work": a.get("work"),
            "source_text": a.get("source_text"), "notes": a.get("notes"), "expected": r["expected"],
            "selected": r["selected"], "agree": r["agree"], "contested": r["contested"],
            "rejected_trivial": r["rejected_trivial"], "rejected_judge": sel.rejected_judge if sel else 0,
            "n_candidates": r["n_candidates"], "chosen_formalization_id": sel.chosen_formalization_id if sel else None,
            "reconstruction": ({"source": rec.source, "conclusion": rec.reconstruction.conclusion,
                                "conclusion_type": rec.reconstruction.conclusion_type,
                                "premises": [p.model_dump() for p in rec.reconstruction.premises]} if rec else None),
            "premise_ids": pmap, "candidates": cands,
            "objections": a.get("objections", []), "hash": hashes.get(aid)})

    concepts = []
    for c in store.concepts(run_id):
        n = len(uses.get((c["label"], c["sense"]), ())) or (1 if c["first_seen"] else 0)
        concepts.append({"id": f"{c['label']}:{c['sense']}", "label": c["label"], "sense": c["sense"],
                         "gloss": c["gloss"], "n_args": n, "args": sorted(uses.get((c["label"], c["sense"]), ())),
                         "split": False, "alias": False})
    cby = {c["id"]: c for c in concepts}
    cedges = []
    by_label: dict[str, list] = {}
    by_sense: dict[str, list] = {}
    for c in concepts:  # sense-split / sense-alias derived from this run's own registry rows
        by_label.setdefault(c["label"], []).append(c["id"])
        by_sense.setdefault(c["sense"], []).append(c["id"])
    for kind, groups in (("sense-split", by_label), ("sense-alias", by_sense)):
        for ids in groups.values():
            if len(ids) > 1:
                for i in ids:
                    cby[i]["split" if kind == "sense-split" else "alias"] = True
                cedges += [{"s": x, "t": y, "kind": kind} for k, x in enumerate(ids) for y in ids[k + 1:]]

    objections = []
    for r in store.relations("attacks"):
        e = r["evidence"] or {}
        objections.append({"id": r["src_id"], "argument": e.get("argument_id"), "dst_kind": r["dst_kind"],
                           "dst_id": r["dst_id"], "text": e.get("text") or e.get("objection") or "",
                           "target": e.get("target")})
    isos = [{"a": sorted(k)[0], "b": sorted(k)[1], "evidence": v["evidence"],
              "unverified": bool((v["evidence"] or {}).get("unverified"))} for k, v in iso_rel.items()]

    reviews = [dict(r) for r in store.reviews(run_id)]
    calls: dict[tuple, dict] = {}
    for r in store.llm_calls():
        kind = "mock" if r["model"] == "mock" else ("cached" if r["latency_ms"] == 0 else "live")
        d = calls.setdefault((r["stage"] or "-", r["model"] or "-"),
                             {"stage": r["stage"] or "-", "model": r["model"] or "-", "n": 0, "live": 0,
                              "cached": 0, "mock": 0, "errors": 0, "in": 0, "out": 0})
        d["n"] += 1
        d[kind] += 1
        d["errors"] += 1 if r["error"] else 0
        d["in"] += r["input_tokens"] or 0
        d["out"] += r["output_tokens"] or 0

    started = ""
    if run and run["started_at"]:
        started = time.strftime("%b %-d, %Y %-I:%M %p", time.localtime(run["started_at"]))
    return {
        "run": {"id": run_id, "mock": bool(run and run["mock"]), "started": started,
                "z3": run["z3_version"] if run else None, "git_sha": run["git_sha"] if run else None},
        "stage_counts": stage_counts, "stages": list(ALL_STAGES), "gate": g,
        "gate_line": f"Gate: {'PASS' if g['passed'] else 'FAIL'} ({report.gate_summary(g)})",
        "shared_reliance": report.shared_reliance(store, run_id, rows),
        "iso": {"precision": ev["precision"], "recall": ev["recall"], "truth": _pairs(ev["truth"]),
                "found": _pairs(ev["found"]), "tp": _pairs(ev["tp"]), "fp": _pairs(ev["fp"]),
                "fn": _pairs(ev["fn"]), "weak_found": _pairs(ev["weak_found"]), "weak_correct": _pairs(ev["weak_correct"]),
                "weak_other": _pairs(ev["weak_other"]),
                "precision_all": ev["precision_all"], "recall_all": ev["recall_all"],
                "unverified": _pairs(ev["unverified"]), "unverified_weak": _pairs(ev["unverified_weak"]), "false_friends": _pairs(ev["false_friends"]), "weak": _pairs(ev["weak"])},
        "arguments": args, "premises": list(premises.values()), "concepts": concepts, "concept_edges": cedges,
        "objections": objections, "isos": isos, "reviews": reviews, "calls": list(calls.values()),
    }


def build_html(store: Store, run_id: int) -> str:
    data = json.dumps(build_data(store, run_id), default=str).replace("<", "\\u003c").replace(">", "\\u003e") \
        .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return TEMPLATE.replace("__D3__", D3_URL).replace("__DATA__", data)


def write_dashboard(store: Store, run_id: int, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(store, run_id), encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Philosophy engine dashboard</title>
<style>
:root{--bg:#fbfaf7;--panel:#fff;--ink:#1b1b1f;--muted:#4a4a55;--line:#cfcdc6;--accent:#1f4fbf;
--ok:#0b6b2e;--okbg:#dff3e5;--bad:#a3151f;--badbg:#fbe1e3;--open:#7a4a00;--openbg:#fdeccb;--hl:#fff3b8;
--n-valid:#1a8a45;--n-refuted:#c62832;--n-open:#d98a00;--n-none:#6b6b78;--prem:#4a78d4;--conc:#8a4fc4}
@media (prefers-color-scheme:dark){:root{--bg:#14151a;--panel:#1e2027;--ink:#ecebf0;--muted:#b9b8c6;--line:#43454f;
--accent:#8fb2ff;--ok:#7fe0a1;--okbg:#17382400;--bad:#ff9aa1;--badbg:#42191d;--open:#ffcf7a;--openbg:#3c2c0c;
--hl:#4a4310;--n-valid:#3fc276;--n-refuted:#f0616b;--n-open:#f0a826;--n-none:#a3a3b3;--prem:#7aa0f0;--conc:#c39bf0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{font-size:18px;margin:0}h2{font-size:16px;margin:20px 0 8px}h3{font-size:14px;margin:14px 0 6px}
nav{display:flex;gap:4px;padding:8px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}
nav button{background:none;border:1px solid var(--line);color:var(--ink);padding:6px 12px;border-radius:6px;cursor:pointer;font:inherit}
nav button.on{background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:600}
main{padding:16px 20px;max-width:1400px}section{display:none}section.on{display:block}
table{border-collapse:collapse;width:100%;background:var(--panel)}th,td{border:1px solid var(--line);padding:5px 9px;text-align:left;vertical-align:top;font-size:14px}
th{background:var(--bg);font-weight:600}
code,pre,.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
pre{background:var(--panel);border:1px solid var(--line);padding:8px;overflow:auto;white-space:pre-wrap;margin:4px 0}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;border:1px solid currentColor}
.valid,.PASS,.yes{color:var(--ok);background:var(--okbg)}.refuted,.FAIL,.NO{color:var(--bad);background:var(--badbg)}
.open,.inconsistent{color:var(--open);background:var(--openbg)}.none{color:var(--muted)}
.gate{font-size:16px;font-weight:600;padding:8px 12px;border:2px solid currentColor;border-radius:8px;display:inline-block}
.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:150px}
.card b{font-size:22px;display:block}.muted{color:var(--muted)}
.done{opacity:.8}.rej{opacity:.85;border-style:dashed}
.cand{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}
.cand.chosen{border:3px solid var(--ok);background:var(--okbg)}
.cand.rej{border-style:dashed}
.tag{background:var(--hl);color:var(--ink);padding:0 6px;border-radius:4px;font-size:12px}
tr.click{cursor:pointer}tr.click:hover td{background:var(--hl)}
#gwrap{display:flex;gap:12px}#gsvg{flex:1;height:72vh;background:var(--panel);border:1px solid var(--line);border-radius:8px;min-width:0}
#gpanel{width:380px;max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:14px}
.toolbar{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;align-items:center}
.legend span{margin-right:12px;white-space:nowrap}.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:4px;vertical-align:-1px}
#tip{position:fixed;pointer-events:none;background:var(--panel);color:var(--ink);border:1px solid var(--line);padding:6px 9px;border-radius:6px;font-size:13px;display:none;max-width:420px;z-index:9}
.nodelabel{fill:var(--ink);font-size:11px;pointer-events:none}
@media(max-width:900px){#gwrap{flex-direction:column}#gpanel{width:auto}}
</style></head><body>
<header><h1>Philosophy engine</h1><span id="hdr" class="muted"></span></header>
<nav id="nav"></nav>
<main>
<section id="overview"></section>
<section id="graph"><div class="toolbar"><label><input type="checkbox" id="tHash"> skeleton-hash groups (false friends)</label>
<label><input type="checkbox" id="tConc" checked> concepts</label><label><input type="checkbox" id="tUse"> argument-concept usage</label>
<span class="legend"><span><i class="dot" style="background:var(--n-valid)"></i>valid</span><span><i class="dot" style="background:var(--n-refuted)"></i>refuted</span>
<span><i class="dot" style="background:var(--n-open)"></i>open</span><span><i class="dot" style="background:var(--prem)"></i>premise</span>
<span><i class="dot" style="background:var(--conc)"></i>concept</span><span style="color:var(--bad)">red = attacks</span> <span>dashed = concept relation</span></span></div>
<div id="gwrap"><svg id="gsvg"></svg><div id="gpanel"><span class="muted">Click a node.</span></div></div>
<div id="gmsg" class="muted"></div></section>
<section id="detail"></section>
<section id="concepts"></section>
<section id="review"></section>
<section id="calls"></section>
</main><div id="tip"></div>
<script id="data" type="application/json">__DATA__</script>
<script src="__D3__"></script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pill=(v)=>`<span class="pill ${esc(v||'none')}">${esc(v||'-')}</span>`;
const fmt=x=>x==null?'n/a':x.toFixed(2);
const pairs=a=>a.length?a.map(p=>p.join(' ~ ')).join(', '):'-';
const A=Object.fromEntries(D.arguments.map(a=>[a.id,a]));
$('#hdr').textContent=`run ${D.run.id}${D.run.mock?' (mock)':''} · started ${D.run.started} · z3 ${D.run.z3||'?'}`;
const TABS=[['overview','Overview'],['graph','Graph'],['detail','Arguments'],['concepts','Concepts'],['review','Review queue'],['calls','LLM calls']];
$('#nav').innerHTML=TABS.map(([k,l])=>`<button data-t="${k}">${l}</button>`).join('');
let graphDone=false;
function show(t){document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===t));
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));
 if(t==='graph'&&!graphDone){graphDone=true;drawGraph();}}
$('#nav').onclick=e=>{if(e.target.dataset.t)show(e.target.dataset.t)};
function openArg(id){curArg=id;renderDetail();show('detail');}
let curArg=D.arguments[0]?.id;

// ---- overview
(function(){
 const g=D.gate,tr=D.arguments.length;
 let h=`<div class="gate ${g.passed?'PASS':'FAIL'}">${esc(D.gate_line)}</div>`;
 h+=`<h2>Stage jobs</h2><table><tr><th>stage</th><th>done</th><th>failed</th><th>pending/running</th><th>skipped</th></tr>`;
 for(const s of D.stages){const c=D.stage_counts[s]||{};h+=`<tr><td>${s}</td><td>${c.done||0}</td><td>${c.failed||0}</td><td>${(c.pending||0)+(c.running||0)}</td><td>${c.skipped||0}</td></tr>`}
 h+=`</table><h2>Verdict agreement</h2><p class="muted">Verdicts are validity as formalized; refuted = invalid as formalized, not unsound. `inconsistent` = the selected formalization's premises are unsat; it is scored against expected `inconsistent` directly.</p>
 <table><tr><th>argument</th><th>expected</th><th>selected</th><th>agree</th><th>contested</th><th>rejected_trivial</th><th>rejected_judge</th><th>candidates</th></tr>`;
 for(const a of D.arguments){h+=`<tr class="click" onclick="openArg('${esc(a.id)}')"><td>${esc(a.id)}</td><td>${pill(a.expected)}</td><td>${pill(a.selected)}</td>
  <td>${a.agree===true?'<span class="pill yes">yes</span>':a.agree===false?'<span class="pill NO">NO</span>':'-'}</td><td>${a.contested?'yes':''}</td><td>${a.rejected_trivial}</td><td>${a.rejected_judge}</td><td>${a.n_candidates}</td></tr>`}
 const dec=D.arguments.filter(a=>a.agree!=null);
 h+=`</table><p>Agreement: ${dec.filter(a=>a.agree).length}/${tr} (undecided: ${tr-dec.length})</p>`;
 const SR=D.shared_reliance||[];
 if(SR.length){h+=`<h2>Shared premise reliance</h2><p class="muted">Per shared premise: arguments citing it, and in how many decided arguments the chosen formalization actually needs it (not in redundant_premises).</p>
 <table><tr><th>shared_id</th><th>arguments citing</th><th>needed in</th><th>idle in</th></tr>`;
  for(const d of SR){h+=`<tr><td>${esc(d.shared_id)}</td><td>${d.arguments.map(a=>esc(a.argument+':'+a.label)).join(', ')}</td><td>${d.n_needed}/${d.n_decided} (of ${d.n_args} citing)</td><td>${esc(d.arguments.filter(a=>a.needed===false).map(a=>a.argument).join(', ')||'-')}</td></tr>`}
  h+=`</table><p>Formally idle shared premises: ${esc(SR.filter(d=>d.idle).map(d=>d.shared_id).join(', ')||'none')}</p>`}
 const I=D.iso;
 h+=`<h2>Isomorphism</h2><div class="cards"><div class="card">precision<b>${fmt(I.precision)}</b></div><div class="card">recall<b>${fmt(I.recall)}</b></div><div class="card">precision incl. unverified<b>${fmt(I.precision_all)}</b></div><div class="card">recall incl. unverified<b>${fmt(I.recall_all)}</b></div></div>
 <table><tr><th>truth</th><td>${esc(pairs(I.truth))}</td></tr><tr><th>found</th><td>${esc(pairs(I.found))}</td></tr><tr><th>false positives</th><td>${esc(pairs(I.fp))}</td></tr>
 <tr><th>false negatives</th><td>${esc(pairs(I.fn))}</td></tr><tr><th>false friends</th><td>${esc(pairs(I.false_friends))}</td></tr><tr><th>weak (graded)</th><td>${esc(pairs(I.weak))}</td></tr>
 <tr><th>unverified (candidate not selected)</th><td>${esc(pairs(I.unverified))}</td></tr><tr><th>unverified, shape-only</th><td>${esc(pairs(I.unverified_weak))}</td></tr>
 <tr><th>shape-only (weak-isomorphic)</th><td>${esc(pairs(I.weak_found))}</td></tr><tr><th>weak-correct</th><td>${esc(pairs(I.weak_correct))}</td></tr></table>`;
 $('#overview').innerHTML=h;
})();

// ---- detail
function sel(){return `<select id="argsel">${D.arguments.map(a=>`<option value="${esc(a.id)}" ${a.id===curArg?'selected':''}>${esc(a.id)}</option>`).join('')}</select>`}
function kv(o){return Object.entries(o).map(([k,v])=>`${k}=${esc(JSON.stringify(v))}`).join(' ')}
function renderDetail(){
 const a=A[curArg];if(!a){$('#detail').innerHTML='no arguments';return}
 let h=`<div class="toolbar"><label>Argument ${sel()}</label></div><h2>${esc(a.id)}: ${esc(a.name)} ${pill(a.selected)} ${a.contested?'<span class="tag">contested</span>':''}</h2>
 <p class="muted">${esc(a.author||'')} ${esc(a.work||'')} · expected ${esc(a.expected)} · candidates ${a.n_candidates} · rejected_trivial ${a.rejected_trivial} · rejected_judge ${a.rejected_judge}</p>
 <h3>Source text</h3><pre>${esc(a.source_text)}</pre>`;
 const r=a.reconstruction;
 if(r){h+=`<h3>Reconstruction (${esc(r.source)})</h3><table><tr><th>id</th><th>type</th><th>implicit</th><th>text</th></tr>`;
  for(const p of r.premises)h+=`<tr><td>${esc(p.id)}</td><td>${esc(p.type)}</td><td>${p.implicit?'<span class="tag">implicit</span>':''}</td><td>${esc(p.text)}</td></tr>`;
  h+=`<tr><td><b>C</b></td><td>${esc(r.conclusion_type||'')}</td><td></td><td>${esc(r.conclusion)}</td></tr></table>`}
 if(a.objections.length){h+=`<h3>Objections</h3><ul>`+a.objections.map(o=>`<li><b>${esc(o.id)}</b> → ${esc(o.target)}: ${esc(o.text||o.objection||JSON.stringify(o))}</li>`).join('')+`</ul>`}
 h+=`<h3>Candidates</h3>`;
 for(const c of a.candidates){
  const k=c.check,j=c.judge,rej=(c.rejected_reasons||[]).length>0&&!c.chosen;
  h+=`<div class="cand ${c.chosen?'chosen':''} ${rej?'rej':''}"><b>Candidate ${c.idx}</b> (formalization ${c.id}, ${esc(c.status)})
   ${c.chosen?'<span class="pill valid">WINNER</span>':''} ${c.rank?`rank ${c.rank}, score ${c.score==null?'-':(+c.score).toFixed(3)}`:''}`;
  if(c.rejected_reasons?.length)h+=`<div><b>Rejected:</b> ${c.rejected_reasons.map(esc).join(' | ')}</div>`;
  if(c.notes?.length)h+=`<div><b>Notes:</b> ${c.notes.map(esc).join(' | ')}</div>`;
  if(c.items.length){h+=`<table><tr><th>id</th><th>S-expression</th><th>English (verbalized)</th><th>sense legend</th></tr>`+
   c.items.map(i=>`<tr><td>${esc(i.id)}</td><td class="mono">${esc(i.sexpr)}</td><td>${esc(i.english)}</td><td class="mono">${esc(i.legend)}</td></tr>`).join('')+`</table>`;
   if(c.verbalize_error)h+=`<div class="muted">verbalize error: ${esc(c.verbalize_error)}</div>`;
   if(c.formalization?.notes)h+=`<div><b>Formalizer notes:</b> ${esc(c.formalization.notes)}</div>`}
  if(k){h+=`<h3>Check</h3><div>valid ${pill(k.valid==='refuted'?'refuted':k.valid)} · premises ${esc(k.consistent)} · parse_ok ${k.parse_ok} · minimal ${k.minimal} · nontrivial ${k.nontrivial} · vacuous ${k.vacuous}</div>`;
   if(k.trivial_reasons.length)h+=`<div><b>Trivial reasons:</b> ${k.trivial_reasons.map(esc).join('; ')}</div>`;
   if(k.suspect_biconditional.length)h+=`<div><b>suspect_biconditional:</b> ${k.suspect_biconditional.map(esc).join(', ')}</div>`;
   if(k.unknown_probes.length)h+=`<div><b>unknown_probes:</b> ${k.unknown_probes.map(esc).join(', ')}</div>`;
   if(k.redundant_premises.length)h+=`<div><b>redundant:</b> ${k.redundant_premises.map(esc).join(', ')}</div>`;
   if(k.parse_errors.length)h+=`<div><b>parse errors:</b> ${k.parse_errors.map(esc).join('; ')}</div>`;
   if(k.valid==='refuted'&&k.countermodel_text)h+=`<b>Countermodel</b><pre>${esc(k.countermodel_text)}</pre>`}
  if(j){h+=`<h3>Judge</h3><div>mean ${j.mean_score.toFixed(2)} · min ${j.min_score.toFixed(2)} · conclusion ${j.conclusion_score.toFixed(2)} · flags ${j.flags.length?esc(j.flags.join(', ')):'none'} ${j.hard_reject?'<span class="pill refuted">hard reject</span>':''}</div>
   <table><tr><th>item</th><th>score</th><th>back-translation</th><th>comment</th></tr>`+Object.entries(j.back_translations).map(([id,t])=>
   `<tr><td>${esc(id)}</td><td>${id==='C'?j.conclusion_score:(j.scores[id]??'')}</td><td>${esc(t)}</td><td>${esc(j.per_item_comments[id]||'')}</td></tr>`).join('')+`</table>`}
  h+=`</div>`}
 $('#detail').innerHTML=h;const s=$('#argsel');if(s)s.onchange=()=>{curArg=s.value;renderDetail()};
}
renderDetail();

// ---- concepts
(function(){
 let h=`<table><tr><th>label</th><th>sense</th><th>gloss</th><th>#arguments</th><th>flags</th></tr>`;
 for(const c of D.concepts)h+=`<tr><td>${esc(c.label)}</td><td class="mono">${esc(c.sense)}</td><td>${esc(c.gloss)}</td><td>${c.n_args}</td><td>${c.split?'<span class="pill open">sense-split</span> ':''}${c.alias?'<span class="pill open">sense-alias</span>':''}</td></tr>`;
 $('#concepts').innerHTML=h+'</table>';
})();
// ---- review
(function(){
 const by={};D.reviews.forEach(r=>(by[r.reason]=by[r.reason]||[]).push(r));
 let h=`<p>${D.reviews.length} review rows, ${Object.keys(by).length} distinct reasons.</p>`;
 for(const [reason,rs] of Object.entries(by))h+=`<h3>${esc(reason)} (${rs.length})</h3><table><tr><th>target</th><th>state</th><th>note</th></tr>`+rs.map(r=>`<tr><td>${esc(r.target_kind)}:${esc(r.target_id)}</td><td>${esc(r.state)}</td><td>${esc(r.note||'')}</td></tr>`).join('')+'</table>';
 $('#review').innerHTML=h;
})();
// ---- calls
(function(){
 let h=`<table><tr><th>stage</th><th>model</th><th>calls</th><th>live</th><th>cached</th><th>mock</th><th>errors</th><th>in tokens</th><th>out tokens</th></tr>`;
 const t={n:0,live:0,cached:0,mock:0,errors:0,in:0,out:0};
 for(const c of D.calls){h+=`<tr><td>${esc(c.stage)}</td><td>${esc(c.model)}</td><td>${c.n}</td><td>${c.live}</td><td>${c.cached}</td><td>${c.mock}</td><td>${c.errors}</td><td>${c.in}</td><td>${c.out}</td></tr>`;for(const k in t)t[k]+=c[k]}
 h+=`<tr><th colspan="2">total</th><th>${t.n}</th><th>${t.live}</th><th>${t.cached}</th><th>${t.mock}</th><th>${t.errors}</th><th>${t.in}</th><th>${t.out}</th></tr></table>`;
 $('#calls').innerHTML=h;
})();

// ---- graph
function verdictColor(v){return v==='valid'?'var(--n-valid)':v==='refuted'?'var(--n-refuted)':(v==='open'||v==='inconsistent')?'var(--n-open)':'var(--n-none)'}
function drawGraph(){
 const svgEl=$('#gsvg');
 if(typeof d3==='undefined'){$('#gmsg').textContent='d3 failed to load (needs network access to cdnjs.cloudflare.com once); other tabs work offline.';return}
 const nodes=[],links=[],ids=new Set();
 const add=n=>{if(!ids.has(n.id)){ids.add(n.id);nodes.push(n)}};
 D.arguments.forEach(a=>add({id:'a:'+a.id,kind:'arg',label:a.id,verdict:a.selected,r:11,arg:a.id}));
 D.premises.forEach(p=>add({id:'p:'+p.id,kind:'prem',label:p.args.map(x=>x.argument+'.'+x.label).join(', '),r:5+Math.min(p.args.length,4)*1.5,prem:p}));
 D.concepts.forEach(c=>add({id:'c:'+c.id,kind:'conc',label:c.id,r:6,conc:c}));
 D.arguments.forEach(a=>Object.values(a.premise_ids).forEach(pid=>{if(ids.has('p:'+pid))links.push({source:'a:'+a.id,target:'p:'+pid,kind:'uses'})}));
 D.objections.forEach(o=>{if(o.dst_kind==='premise'&&ids.has('p:'+o.dst_id))links.push({source:'p:'+o.dst_id,target:'p:'+o.dst_id,kind:'attacks',o});
  else if(ids.has('a:'+o.dst_id))links.push({source:'a:'+o.dst_id,target:'a:'+o.dst_id,kind:'attacks',o})});
 // objections are drawn as small red nodes attached to their target
 const objLinks=[];links.filter(l=>l.kind==='attacks').forEach(l=>{const id='o:'+l.o.argument+':'+l.o.id;add({id,kind:'obj',label:l.o.id,r:4,o:l.o});objLinks.push({source:id,target:l.source,kind:'attacks',o:l.o})});
 const L=[...links.filter(l=>l.kind!=='attacks'),...objLinks];
 D.isos.forEach(i=>L.push({source:'a:'+i.a,target:'a:'+i.b,kind:'iso',ev:i.evidence}));
 D.concept_edges.forEach(e=>L.push({source:'c:'+e.s,target:'c:'+e.t,kind:e.kind}));
 D.concepts.forEach(c=>c.args.forEach(a=>L.push({source:'a:'+a,target:'c:'+c.id,kind:'cuse'})));
 const byHash={};D.arguments.forEach(a=>{if(a.hash)(byHash[a.hash]=byHash[a.hash]||[]).push(a.id)});
 const truth=new Set(D.iso.truth.map(p=>p.slice().sort().join('|')));
 Object.values(byHash).forEach(g=>{for(let i=0;i<g.length;i++)for(let j=i+1;j<g.length;j++){const ff=!truth.has([g[i],g[j]].sort().join('|'));L.push({source:'a:'+g[i],target:'a:'+g[j],kind:'hash',ff})}});
 const svg=d3.select(svgEl),box=svgEl.getBoundingClientRect(),W=box.width||900,H=box.height||600;
 const root=svg.append('g');
 svg.call(d3.zoom().scaleExtent([.1,6]).on('zoom',e=>root.attr('transform',e.transform)));
 const st={uses:'var(--line)',attacks:'var(--n-refuted)',iso:'var(--accent)','sense-split':'var(--conc)','sense-alias':'var(--conc)',cuse:'var(--line)',hash:'var(--n-open)'};
 const link=root.append('g').selectAll('line').data(L).join('line').attr('stroke',d=>st[d.kind]).attr('stroke-width',d=>d.kind==='iso'?3:d.kind==='attacks'?2:1.2)
  .attr('stroke-dasharray',d=>d.kind.startsWith('sense')?'5 4':d.kind==='hash'?'2 3':null);
 const tip=$('#tip');
 const showTip=(e,h)=>{tip.innerHTML=h;tip.style.display='block';tip.style.left=Math.min(e.clientX+12,innerWidth-440)+'px';tip.style.top=(e.clientY+12)+'px'};
 link.on('mousemove',(e,d)=>{
  if(d.kind==='iso')showTip(e,`<b>${esc(d.source.arg||d.source.label)} ~ ${esc(d.target.label)}</b> isomorphic-to<br><span class="mono">${esc(JSON.stringify(d.ev?.mapping||d.ev))}</span>${d.ev?.unverified?'<br>unverified (candidate not selected)':''}`);
  else if(d.kind==='hash')showTip(e,`same skeleton hash${d.ff?' (false friend: not in truth)':''}`);
  else showTip(e,esc(d.kind));}).on('mouseleave',()=>tip.style.display='none');
 const node=root.append('g').selectAll('g').data(nodes).join('g').style('cursor','pointer')
  .call(d3.drag().on('start',(e,d)=>{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y}).on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y}).on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=d.fy=null}));
 node.append('circle').attr('r',d=>d.r).attr('fill',d=>d.kind==='arg'?verdictColor(d.verdict):d.kind==='prem'?'var(--prem)':d.kind==='obj'?'var(--n-refuted)':'var(--conc)')
  .attr('stroke','var(--ink)').attr('stroke-width',d=>d.kind==='arg'?2:1);
 node.filter(d=>d.kind==='arg'||d.kind==='conc').append('text').attr('class','nodelabel').attr('x',d=>d.r+3).attr('y',4).text(d=>d.label);
 node.on('mousemove',(e,d)=>showTip(e,esc(d.kind==='prem'?d.prem.text:d.kind==='obj'?'objection '+d.label+': '+(d.o.text||''):d.label))).on('mouseleave',()=>tip.style.display='none');
 node.on('click',(e,d)=>nodePanel(d));
 const sim=d3.forceSimulation(nodes).force('link',d3.forceLink(L).id(d=>d.id).distance(d=>d.kind==='hash'?120:d.kind==='iso'?90:50).strength(d=>d.kind==='hash'?.05:.5))
  .force('charge',d3.forceManyBody().strength(-90)).force('center',d3.forceCenter(W/2,H/2)).force('collide',d3.forceCollide(d=>d.r+3))
  .on('tick',()=>{link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);node.attr('transform',d=>`translate(${d.x},${d.y})`)});
 function vis(){const h=$('#tHash').checked,c=$('#tConc').checked,u=$('#tUse').checked;
  link.style('display',d=>(d.kind==='hash'&&!h)||(d.kind==='cuse'&&!(u&&c))||(d.kind.startsWith('sense')&&!c)?'none':null);
  node.style('display',d=>d.kind==='conc'&&!c?'none':null)}
 ['#tHash','#tConc','#tUse'].forEach(s=>$(s).onchange=vis);vis();
}
function nodePanel(d){
 const p=$('#gpanel');
 if(d.kind==='arg'){const a=A[d.arg];p.innerHTML=`<h3>${esc(a.id)} ${pill(a.selected)}</h3><div>${esc(a.name)}</div><div class="muted">expected ${esc(a.expected)}</div>
  <p><button onclick="openArg('${esc(a.id)}')">Open argument detail</button></p><pre>${esc((a.source_text||'').slice(0,600))}</pre>
  ${a.reconstruction?a.reconstruction.premises.map(x=>`<div>[${esc(x.id)}] ${esc(x.text)}</div>`).join(''):''}`}
 else if(d.kind==='prem'){p.innerHTML=`<h3>Premise (${esc(d.prem.type)})</h3><div>${esc(d.prem.text)}</div><h3>Used by</h3>`+d.prem.args.map(x=>`<div><a href="#" onclick="openArg('${esc(x.argument)}');return false">${esc(x.argument)}</a> as ${esc(x.label)}${x.implicit?' (implicit)':''}</div>`).join('')}
 else if(d.kind==='conc'){const c=d.conc;p.innerHTML=`<h3>${esc(c.label)}</h3><div class="mono">${esc(c.sense)}</div><div>${esc(c.gloss)}</div><div>${c.split?'sense-split ':''}${c.alias?'sense-alias':''}</div><h3>Arguments</h3>`+(c.args.map(x=>`<div><a href="#" onclick="openArg('${esc(x)}');return false">${esc(x)}</a></div>`).join('')||'-')}
 else{p.innerHTML=`<h3>Objection ${esc(d.o.id)}</h3><div>${esc(d.o.text)}</div><div class="muted">in ${esc(d.o.argument)}, target ${esc(d.o.target)}</div>`}
}
show('overview');
</script></body></html>
"""
