"""SQLite store (plain sqlite3). One connection guarded by an RLock so worker threads can share it."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from . import config
from .models_ext import FormalizationX, JudgeReportX, ReconstructionX, SelectionResultX
from .schemas import (CheckReport, FormalizationRecord, JudgeReport, Reconstruction,
                      ReconstructionRecord, SelectionResult)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS run(
  id INTEGER PRIMARY KEY, started_at REAL, config_json TEXT, git_sha TEXT, z3_version TEXT, mock INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS argument(
  id TEXT PRIMARY KEY, name TEXT, author TEXT, work TEXT, source_text TEXT,
  expected_verdict TEXT, notes TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS premise(
  id TEXT PRIMARY KEY,            -- sha1 of normalized text
  text TEXT NOT NULL,
  type TEXT,
  type_ext TEXT,                  -- original type (may be 'metaphysical')
  first_argument_id TEXT);
CREATE TABLE IF NOT EXISTS argument_premise(
  argument_id TEXT NOT NULL, premise_id TEXT NOT NULL, ord INTEGER NOT NULL,
  label TEXT NOT NULL,            -- local id "P1"
  implicit INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(argument_id, label));
CREATE TABLE IF NOT EXISTS concept(
  id TEXT PRIMARY KEY, label TEXT, gloss TEXT, sense TEXT, first_seen TEXT);
CREATE TABLE IF NOT EXISTS relation(
  id INTEGER PRIMARY KEY, src_kind TEXT, src_id TEXT, dst_kind TEXT, dst_id TEXT,
  kind TEXT NOT NULL,             -- supports|attacks|isomorphic-to
  evidence_json TEXT, run_id INTEGER);
CREATE TABLE IF NOT EXISTS reconstruction(
  id INTEGER PRIMARY KEY, argument_id TEXT NOT NULL, source TEXT NOT NULL, run_id INTEGER,
  model TEXT, json TEXT NOT NULL, llm_call_id INTEGER);
CREATE TABLE IF NOT EXISTS formalization(
  id INTEGER PRIMARY KEY, reconstruction_id INTEGER NOT NULL, candidate_idx INTEGER NOT NULL, run_id INTEGER,
  status TEXT NOT NULL, formalization_json TEXT, check_json TEXT, judge_json TEXT, llm_call_ids_json TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS selection(
  id INTEGER PRIMARY KEY, reconstruction_id INTEGER NOT NULL, run_id INTEGER,
  chosen_formalization_id INTEGER, verdict TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review(
  id INTEGER PRIMARY KEY, target_kind TEXT, target_id TEXT, reason TEXT,
  state TEXT DEFAULT 'open', note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS llm_call(
  id INTEGER PRIMARY KEY, run_id INTEGER, stage TEXT, argument_id TEXT, candidate_idx INTEGER,
  sample_idx INTEGER NOT NULL DEFAULT 0, model TEXT, temperature REAL, prompt_name TEXT,
  prompt_hash TEXT NOT NULL, cache_key TEXT, prompt TEXT, response TEXT,
  input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER, error TEXT, created_at REAL, stop_reason TEXT);
CREATE INDEX IF NOT EXISTS llm_call_cache ON llm_call(cache_key);
CREATE TABLE IF NOT EXISTS job(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, argument_id TEXT NOT NULL, stage TEXT NOT NULL,
  candidate_idx INTEGER NOT NULL DEFAULT -1,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|failed|skipped
  attempts INTEGER NOT NULL DEFAULT 0, error TEXT, started_at REAL, finished_at REAL,
  UNIQUE(run_id, argument_id, stage, candidate_idx));
"""


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def premise_id(text: str) -> str:
    return hashlib.sha1(norm_text(text).encode()).hexdigest()


def _j(obj) -> str:
    return obj.model_dump_json() if hasattr(obj, "model_dump_json") else json.dumps(obj)


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        with self.lock:
            self.db.executescript(SCHEMA)
            cols = {r["name"] for r in self.db.execute("PRAGMA table_info(llm_call)")}
            if "stop_reason" not in cols:  # migrate DBs created before stop_reason existed
                self.db.execute("ALTER TABLE llm_call ADD COLUMN stop_reason TEXT")
            self._migrate()
            if not self.db.execute("SELECT 1 FROM schema_version").fetchone():
                self.db.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
            self.db.commit()

    def _migrate(self) -> None:
        """Additive, guarded ALTERs for DBs created by earlier versions (caller holds the lock)."""
        def cols(t):
            return {r["name"] for r in self.db.execute(f"PRAGMA table_info({t})")}
        fresh_scope = "run_id" not in cols("concept")
        for table, col, ddl in (("formalization", "strategy_hint", "TEXT"), ("concept", "raw_label", "TEXT"),
                                ("concept", "run_id", "INTEGER"), ("review", "run_id", "INTEGER")):
            if col not in cols(table):
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        if fresh_scope:
            self._backfill_run_ids()

    def _backfill_run_ids(self) -> None:
        """One-time: give pre-run_id concept/review rows a run. Concepts go to every run whose formalizations
        declare that (label, sense), re-keyed per run and normalized (raw label kept); reviews go to the run whose
        job window contains their created_at."""
        from . import senses
        runs = {r["id"]: r for r in self.db.execute("SELECT id FROM run")}
        used: dict[tuple, set] = {}
        for r in self.db.execute("SELECT run_id, formalization_json FROM formalization WHERE run_id IS NOT NULL "
                                 "AND formalization_json IS NOT NULL"):
            try:
                preds = json.loads(r["formalization_json"]).get("predicates", [])
            except json.JSONDecodeError:
                continue
            for p in preds:
                used.setdefault((p.get("name"), p.get("sense", "")), set()).add(r["run_id"])
        for c in self.db.execute("SELECT * FROM concept WHERE run_id IS NULL").fetchall():
            rids = [x for x in sorted(used.get((c["label"], c["sense"] or ""), ())) if x in runs]
            if not rids:
                continue
            for rid in rids:
                lab, sen = senses.normalize_label(c["label"]), senses.normalize_sense(c["sense"] or "")
                cid = self.concept_id(lab, sen, c["gloss"] or "", rid)
                self.db.execute("INSERT OR IGNORE INTO concept(id,label,gloss,sense,first_seen,raw_label,run_id) "
                                "VALUES (?,?,?,?,?,?,?)", (cid, lab, c["gloss"], sen, c["first_seen"], c["label"], rid))
            self.db.execute("DELETE FROM concept WHERE id=?", (c["id"],))
        win = {r["run_id"]: (r["a"], r["b"]) for r in self.db.execute(
            "SELECT run_id, min(started_at) a, max(finished_at) b FROM job WHERE started_at IS NOT NULL "
            "GROUP BY run_id")}
        for q in self.db.execute("SELECT id, created_at FROM review WHERE run_id IS NULL").fetchall():
            for rid, (a, b) in win.items():
                if a is not None and b is not None and a - 1 <= (q["created_at"] or 0) <= b + 1:
                    self.db.execute("UPDATE review SET run_id=? WHERE id=?", (rid, q["id"]))
                    break

    def close(self):
        self.db.close()

    # ---- low level
    def execute(self, sql: str, args=()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def query(self, sql: str, args=()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def one(self, sql: str, args=()) -> sqlite3.Row | None:
        with self.lock:
            return self.db.execute(sql, args).fetchone()

    # ---- run
    def new_run(self, config_json: dict | None = None, mock: bool = False, git_sha: str | None = None) -> int:
        try:
            import z3
            zv = z3.get_version_string()
        except Exception:
            zv = None
        return self.execute("INSERT INTO run(started_at, config_json, git_sha, z3_version, mock) VALUES (?,?,?,?,?)",
                            (time.time(), json.dumps(config_json or {}), git_sha, zv, int(mock))).lastrowid

    def latest_run(self) -> int | None:
        r = self.one("SELECT max(id) m FROM run")
        return r["m"] if r else None

    # ---- arguments / ingest
    def ingest(self, path: str | Path | None = None) -> int:
        """Load arguments.json (all extra fields accepted). Idempotent. Returns #arguments."""
        path = Path(path) if path else config.data_dir() / "phase0" / "arguments.json"
        data = json.loads(path.read_text())
        for a in data:
            self.ingest_argument(a)
        return len(data)

    def ingest_argument(self, a: dict) -> None:
        try:
            rec = ReconstructionX.model_validate(a["reconstruction"])
        except Exception as e:  # fail loudly with the argument id
            raise ValueError(f"argument {a.get('id')!r}: bad reconstruction: {e}") from e
        aid = a["id"]
        self.execute(
            "INSERT OR REPLACE INTO argument(id,name,author,work,source_text,expected_verdict,notes,json) VALUES (?,?,?,?,?,?,?,?)",
            (aid, a.get("name"), a.get("author"), a.get("work"), a.get("source_text"),
             a.get("expected_verdict"), a.get("notes"), json.dumps(a)))
        # human reconstruction (raw json keeps metaphysical + fol_hint)
        raw = json.dumps(a["reconstruction"])
        ex = self.one("SELECT id FROM reconstruction WHERE argument_id=? AND source='human'", (aid,))
        if ex:
            self.execute("UPDATE reconstruction SET json=? WHERE id=?", (raw, ex["id"]))
        else:
            self.execute("INSERT INTO reconstruction(argument_id,source,json) VALUES (?, 'human', ?)", (aid, raw))
        # premise library
        self.execute("DELETE FROM argument_premise WHERE argument_id=?", (aid,))
        label2pid = {}
        for i, p in enumerate(rec.premises):
            pid = premise_id(p.text)
            label2pid[p.id] = pid
            self.execute("INSERT OR IGNORE INTO premise(id,text,type,type_ext,first_argument_id) VALUES (?,?,?,?,?)",
                         (pid, p.text, p.type, p.type, aid))
            self.execute("INSERT OR REPLACE INTO argument_premise(argument_id,premise_id,ord,label,implicit) VALUES (?,?,?,?,?)",
                         (aid, pid, i, p.id, int(p.implicit)))
        # objections -> attacks relations
        self.execute("DELETE FROM relation WHERE kind='attacks' AND src_kind='objection' AND json_extract(evidence_json,'$.argument_id')=?", (aid,))
        for o in a.get("objections", []):
            tgt = o.get("target")
            if tgt in label2pid:
                dk, di = "premise", label2pid[tgt]
            else:
                dk, di = "argument", aid  # e.g. attacks the conclusion / whole argument
            ev = dict(o, argument_id=aid)
            self.execute("INSERT INTO relation(src_kind,src_id,dst_kind,dst_id,kind,evidence_json) VALUES ('objection',?,?,?,'attacks',?)",
                         (o.get("id"), dk, di, json.dumps(ev)))

    def get_argument(self, argument_id: str) -> dict:
        r = self.one("SELECT json FROM argument WHERE id=?", (argument_id,))
        if not r:
            raise KeyError(f"unknown argument {argument_id!r}")
        return json.loads(r["json"])

    def argument_ids(self) -> list[str]:
        return [r["id"] for r in self.query("SELECT id FROM argument ORDER BY rowid")]

    def iso_truth(self) -> set[frozenset]:
        """Ground-truth isomorphic pairs from `isomorphic_to` (symmetric, deduped)."""
        out = set()
        for aid in self.argument_ids():
            for b in self.get_argument(aid).get("isomorphic_to", []):
                out.add(frozenset((aid, b)))
        return out

    # ---- reconstruction
    def insert_reconstruction(self, argument_id: str, source: str, reconstruction, model: str | None = None,
                              run_id: int | None = None, llm_call_id: int | None = None) -> int:
        return self.execute(
            "INSERT INTO reconstruction(argument_id,source,run_id,model,json,llm_call_id) VALUES (?,?,?,?,?,?)",
            (argument_id, source, run_id, model, _j(reconstruction), llm_call_id)).lastrowid

    def _recon_record(self, r) -> ReconstructionRecord:
        rec = ReconstructionX.model_validate_json(r["json"]).to_frozen()
        return ReconstructionRecord(id=r["id"], argument_id=r["argument_id"], source=r["source"],
                                    model=r["model"], reconstruction=rec, llm_call_id=r["llm_call_id"])

    def get_reconstruction(self, rid: int) -> ReconstructionRecord:
        r = self.one("SELECT * FROM reconstruction WHERE id=?", (rid,))
        if not r:
            raise KeyError(rid)
        return self._recon_record(r)

    def latest_reconstruction(self, argument_id: str, source: str | None = None) -> ReconstructionRecord | None:
        q, args = "SELECT * FROM reconstruction WHERE argument_id=?", [argument_id]
        if source:
            q += " AND source=?"
            args.append(source)
        r = self.one(q + " ORDER BY id DESC LIMIT 1", args)
        return self._recon_record(r) if r else None

    # ---- formalization
    def insert_formalization(self, reconstruction_id: int, candidate_idx: int, status: str,
                             formalization: FormalizationX | None = None, check: CheckReport | None = None,
                             judge: JudgeReport | None = None, llm_call_ids: list[int] | None = None,
                             run_id: int | None = None, strategy_hint: str = "") -> int:
        return self.execute(
            "INSERT INTO formalization(reconstruction_id,candidate_idx,run_id,status,formalization_json,check_json,judge_json,llm_call_ids_json,strategy_hint) VALUES (?,?,?,?,?,?,?,?,?)",
            (reconstruction_id, candidate_idx, run_id, status,
             _j(formalization) if formalization else None, _j(check) if check else None,
             _j(judge) if judge else None, json.dumps(llm_call_ids or []), strategy_hint)).lastrowid

    def update_formalization(self, fid: int, *, status: str | None = None, check: CheckReport | None = None,
                             judge: JudgeReport | None = None, llm_call_ids: list[int] | None = None) -> None:
        sets, args = [], []
        for col, val in (("status", status), ("check_json", _j(check) if check else None),
                         ("judge_json", _j(judge) if judge else None),
                         ("llm_call_ids_json", json.dumps(llm_call_ids) if llm_call_ids is not None else None)):
            if val is not None:
                sets.append(f"{col}=?")
                args.append(val)
        if sets:
            self.execute(f"UPDATE formalization SET {', '.join(sets)} WHERE id=?", (*args, fid))

    def _form_record(self, r) -> FormalizationRecord:
        return FormalizationRecord(
            id=r["id"], reconstruction_id=r["reconstruction_id"], candidate_idx=r["candidate_idx"],
            formalization=FormalizationX.model_validate_json(r["formalization_json"]) if r["formalization_json"] else None,
            check=CheckReport.model_validate_json(r["check_json"]) if r["check_json"] else None,
            judge=JudgeReportX.model_validate_json(r["judge_json"]) if r["judge_json"] else None,
            status=r["status"], llm_call_ids=json.loads(r["llm_call_ids_json"] or "[]"),
            strategy_hint=r["strategy_hint"] or "")

    def get_formalization(self, fid: int) -> FormalizationRecord:
        r = self.one("SELECT * FROM formalization WHERE id=?", (fid,))
        if not r:
            raise KeyError(fid)
        return self._form_record(r)

    def list_formalizations(self, reconstruction_id: int) -> list[FormalizationRecord]:
        return [self._form_record(r) for r in self.query(
            "SELECT * FROM formalization WHERE reconstruction_id=? ORDER BY candidate_idx, id", (reconstruction_id,))]

    # ---- selection
    def insert_selection(self, sel: SelectionResult, run_id: int | None = None) -> int:
        return self.execute(
            "INSERT INTO selection(reconstruction_id,run_id,chosen_formalization_id,verdict,json) VALUES (?,?,?,?,?)",
            (sel.reconstruction_id, run_id, sel.chosen_formalization_id, sel.verdict, _j(sel))).lastrowid

    def get_selection(self, reconstruction_id: int) -> SelectionResult | None:
        r = self.one("SELECT json FROM selection WHERE reconstruction_id=? ORDER BY id DESC LIMIT 1", (reconstruction_id,))
        return SelectionResultX.model_validate_json(r["json"]) if r else None

    # ---- relations / concepts / reviews (review is a stub)
    def insert_relation(self, src_kind, src_id, dst_kind, dst_id, kind, evidence=None, run_id=None) -> int:
        return self.execute(
            "INSERT INTO relation(src_kind,src_id,dst_kind,dst_id,kind,evidence_json,run_id) VALUES (?,?,?,?,?,?,?)",
            (src_kind, src_id, dst_kind, dst_id, kind, json.dumps(evidence) if evidence is not None else None, run_id)).lastrowid

    def relations(self, kind: str | None = None, **eq) -> list[dict]:
        q, args = "SELECT * FROM relation WHERE 1=1", []
        if kind:
            q += " AND kind=?"
            args.append(kind)
        for k, v in eq.items():
            q += f" AND {k}=?"
            args.append(v)
        out = []
        for r in self.query(q + " ORDER BY id", args):
            d = dict(r)
            d["evidence"] = json.loads(d.pop("evidence_json")) if d["evidence_json"] else None
            out.append(d)
        return out

    @staticmethod
    def concept_id(label: str, sense: str, gloss: str, run_id: int | None = None) -> str:
        scope = f"{run_id}|" if run_id is not None else ""
        return hashlib.sha1(f"{scope}{label}|{sense}|{norm_text(gloss)}".encode()).hexdigest()

    def upsert_concept(self, label: str, gloss: str, sense: str = "", first_seen: str | None = None,
                       run_id: int | None = None) -> str:
        """Register (label, sense) after normalization (senses.normalize_*; the raw label is kept in raw_label).
        Concepts are scoped per run when run_id is given, so each run has its own registry."""
        from . import senses
        raw_label = label
        label, sense = senses.normalize_label(label), senses.normalize_sense(sense)
        cid = self.concept_id(label, sense, gloss, run_id)
        is_new = self.one("SELECT 1 FROM concept WHERE id=?", (cid,)) is None
        if is_new and sense:
            splits = [r for r in self.concepts_by_label(label, run_id) if r["sense"] and r["sense"] != sense]
            aliases = [r for r in self.concepts_by_sense(sense, run_id) if r["label"] != label]
            if splits:  # never merge: record the split
                senses_ = sorted({r["sense"] for r in splits} | {sense})
                args = sorted({r["first_seen"] for r in splits if r["first_seen"]} | ({first_seen} if first_seen else set()))
                self.insert_relation("concept", label, "concept", label, "sense-split",
                                     {"senses": senses_, "argument_ids": args}, run_id)
                self.insert_review("concept", label, "label reused across senses: " + ", ".join(senses_), run_id)
            if aliases:
                other = sorted({r["label"] for r in aliases})
                self.insert_relation("concept", label, "concept", other[0], "sense-alias",
                                     {"sense": sense, "labels": [label, *other],
                                      "argument_ids": sorted({r["first_seen"] for r in aliases if r["first_seen"]}
                                                             | ({first_seen} if first_seen else set()))}, run_id)
                self.insert_review("concept", label, f"same sense {sense!r} under different labels: {[label, *other]}", run_id)
        self.execute("INSERT OR IGNORE INTO concept(id,label,gloss,sense,first_seen,raw_label,run_id) VALUES (?,?,?,?,?,?,?)",
                     (cid, label, gloss, sense, first_seen, raw_label, run_id))
        return cid

    def concepts_by_label(self, label: str, run_id: int | None = None) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM concept WHERE label=? AND run_id IS ? ORDER BY rowid", (label, run_id))

    def concepts_by_sense(self, sense: str, run_id: int | None = None) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM concept WHERE sense=? AND run_id IS ? ORDER BY rowid", (sense, run_id))

    def concepts(self, run_id: int | None = None) -> list[sqlite3.Row]:
        """Registry rows of one run (None = all runs, un-scoped)."""
        if run_id is None:
            return self.query("SELECT * FROM concept ORDER BY label, sense")
        return self.query("SELECT * FROM concept WHERE run_id=? ORDER BY label, sense", (run_id,))

    def reviews(self, run_id: int | None = None) -> list[sqlite3.Row]:
        if run_id is None:
            return self.query("SELECT * FROM review ORDER BY id")
        return self.query("SELECT * FROM review WHERE run_id=? ORDER BY id", (run_id,))

    def insert_review(self, target_kind: str, target_id: str, reason: str, run_id: int | None = None) -> int:
        return self.execute("INSERT INTO review(target_kind,target_id,reason,created_at,run_id) VALUES (?,?,?,?,?)",
                            (target_kind, target_id, reason, time.time(), run_id)).lastrowid

    # ---- llm_call
    def insert_llm_call(self, **f) -> int:
        cols = ["run_id", "stage", "argument_id", "candidate_idx", "sample_idx", "model", "temperature", "prompt_name",
                "prompt_hash", "cache_key", "prompt", "response", "input_tokens", "output_tokens", "latency_ms", "error", "stop_reason"]
        return self.execute(
            f"INSERT INTO llm_call({','.join(cols)},created_at) VALUES ({','.join('?' * (len(cols) + 1))})",
            (*[f.get(c) for c in cols], time.time())).lastrowid

    def find_cached_call(self, cache_key: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM llm_call WHERE cache_key=? AND error IS NULL AND response IS NOT NULL "
                        "AND TRIM(response) != '' AND (stop_reason IS NULL OR stop_reason != 'max_tokens') "
                        "AND model != 'mock' ORDER BY id LIMIT 1", (cache_key,))

    def llm_calls(self, stage: str | None = None, argument_id: str | None = None) -> list[sqlite3.Row]:
        q, args = "SELECT * FROM llm_call WHERE 1=1", []
        if stage:
            q += " AND stage=?"
            args.append(stage)
        if argument_id:
            q += " AND argument_id=?"
            args.append(argument_id)
        return self.query(q + " ORDER BY id", args)

    # ---- jobs
    def upsert_job(self, run_id: int, argument_id: str, stage: str, candidate_idx: int = -1) -> sqlite3.Row:
        self.execute("INSERT OR IGNORE INTO job(run_id,argument_id,stage,candidate_idx) VALUES (?,?,?,?)",
                     (run_id, argument_id, stage, candidate_idx))
        return self.one("SELECT * FROM job WHERE run_id=? AND argument_id=? AND stage=? AND candidate_idx=?",
                        (run_id, argument_id, stage, candidate_idx))

    def set_job(self, job_id: int, status: str, error: str | None = None) -> None:
        now = time.time()
        if status == "running":
            self.execute("UPDATE job SET status='running', attempts=attempts+1, started_at=?, finished_at=NULL, error=NULL WHERE id=?",
                         (now, job_id))
        elif status in ("done", "failed", "skipped"):
            self.execute("UPDATE job SET status=?, error=?, finished_at=? WHERE id=?", (status, error, now, job_id))
        else:
            self.execute("UPDATE job SET status=?, error=NULL, started_at=NULL, finished_at=NULL WHERE id=?", (status, job_id))

    def jobs(self, run_id: int, stage: str | None = None) -> list[sqlite3.Row]:
        q, args = "SELECT * FROM job WHERE run_id=?", [run_id]
        if stage:
            q += " AND stage=?"
            args.append(stage)
        return self.query(q + " ORDER BY id", args)

    def reset_running_jobs(self, run_id: int) -> int:
        return self.execute("UPDATE job SET status='pending', started_at=NULL WHERE run_id=? AND status='running'",
                            (run_id,)).rowcount
