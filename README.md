# philosophy-engine

## What this is

An engine that formalizes arguments and institutions, checks them with Z3, and compares them for shared logical form. Every result ships as a plain sentence plus the formal certificate behind it: validity verdicts with countermodels, reachability verdicts over bounded traces, isomorphism with its remainder. Runs are reproducible and expectations are written down before runs.

The theory this engine serves (a general theory of liberation), its claims register, reviews and the institutions dataset live in [computational-liberation](https://github.com/reeshuffled/computational-liberation), which depends on this repo and runs it over its own `data/`.

**Status:** early research software; expect breaking changes. Apache-2.0.

- [Decisions (ADRs)](docs/decisions/) | [Glossary](docs/glossary.md) | [Institutions plan](plans/institutions-phase0.md) | [Contributing](CONTRIBUTING.md)

**Two data families.** Arguments (`data/phase0`): Phase 0 done. Institutions (`data/institutions`): in progress, moving to computational-liberation when the ADR 0013 re-encode lands.

---

Generative philosophy engine. **Phase 0 scope:** a first-order prototype. Take ~15 hand-reconstructed
philosophical arguments, formalize them (LLM, N candidates), check them with Z3, back-translate to
English to judge faithfulness, select the best formalization, and test whether two arguments with the
same logical form are recognised as isomorphic. Nothing beyond classical first-order logic: no modal,
probabilistic, deontic or higher-order encodings.

Python: 3.14 (z3-solver 5.3.0 and pydantic have wheels for 3.14; no 3.13 fallback was needed).
Setup: `uv sync`; tests: `uv run pytest`. Layout and stages: see the Phase 0 plan.

## Handoff decisions

- **Find before generate.** Look for an existing argument/premise/concept in the library (and its
  formalization) before asking an LLM to create one; generation is the fallback.
- **Isomorphism is the result.** The headline output is "these two arguments share a form",
  established by canonical skeleton + Z3 equivalence under a predicate bijection, not a score.
- **Validity, not truth.** Z3 answers "does the conclusion follow from the premises as formalized".
  `refuted` means *invalid as formalized* (often a missing implicit premise), never "the argument is
  unsound"; `unknown`/timeouts map to verdict `open` and are never treated as invalid.
- **Premise types.** Every premise is tagged `logical | definitional | empirical | normative`, and
  implicit premises are first-class (`implicit: true`), because validity alone says nothing about
  which premises are worth contesting.

## Formalization format

JSON envelope (`schemas.FormalizationJSON`): declared sorts, predicates (arity + required gloss),
constants, one S-expression per premise id plus `C`. Grammar: `forall exists => iff and or not =`,
predicate application, atoms. Anything else (`ite`, `+`, `let`, ...) is a parse error with a precise
message. No `eval`; formulas are parsed to our own AST (`sexpr.py`), validated (`fol.validate`) and
lowered to z3 (`fol.lower`).

## Z3 core API (step 1)

- `checks.run_all(f: FormalizationJSON, reconstruction_ids: list[str] | None = None, timeout_ms=5000, retry_unknown=True) -> CheckReport`
- `checks.verdict_of(report) -> "valid" | "refuted" | "open" | "inconsistent"`
- `fol.validate(f, reconstruction_ids=None) -> (Parsed | None, errors: list[str])` (errors are retry-feedback text)
- `fol.build_env(f) -> Env`, `fol.lower(ast, env) -> z3.ExprRef`, `fol.rename(ast, mapping)`,
  `fol.normalize(ast)`, `fol.normalized_text(ast)`, `fol.conjuncts(ast)`, `fol.predicates_used(ast, f)`
- `sexpr.parse(text) -> AST`, `sexpr.to_sexpr(ast) -> str`, `sexpr.ParseError`

Fixed seed (0), per-check timeout, one retry at 3x timeout with a `simplify;smt` tactic, z3 version
recorded in each report.

## Schema changes

`schemas.py` is frozen after builder step 1; add requests below, one line each.
Step 1 additions to the plan's `CheckReport`: `unknown_reason`, `z3_version`.
Second-fix additions: `CheckReport.suspect_biconditional`, `CheckReport.sense_mismatch_hint` (both soft, additive). Review-fix additions: `CheckReport.unknown_probes` (z3-unknown probes; fields left None, verdict open), `SelectionResultX.rejected_judge`, `llm_call.stop_reason` (migrated via ALTER TABLE).

## Usage

Default DB is `runs/phase0.db` (gitignored); every command takes `--db PATH`.

```
uv run phil ingest [--data data/phase0/arguments.json]
uv run phil run [--mock] [--from-human] [--n-candidates N] [--stage S ...] [--args ID ...]
                [--resume/--no-resume] [--retry-failed] [--new-run]   # continues the latest run by default
uv run phil status [--run ID]
uv run phil show ARG_ID [--run ID]       # reconstruction, candidates, check, judge, rank, countermodel
uv run phil calls [--stage S] [--arg ID] # LLM call/token summary (cost only if config.PRICES is set)
uv run phil report [--run ID] [--out FILE.md]
uv run phil gate [--run ID]              # exit 0 = PASS
uv run phil dashboard [--run ID] [--out runs/dashboard.html]  # one self-contained HTML file (open via file://; graph loads d3 7.9.0 from cdnjs)
```

One-liner (live, needs `ANTHROPIC_API_KEY` in `.env`): `phil run --from-human --n-candidates 2 && phil report --out runs/report-live-1.md && phil gate`.
Offline: `phil run --mock`. Live golden test: `uv run pytest -m llm` (live tests run only with `-m llm`, and `.env` is loaded first; skipped without a key; runs 4 arguments
from the human reconstructions and needs >=3 selected verdicts to match `expected_verdict`).
`checks.verdict_of` returns `inconsistent` when the premises are unsat; expected `inconsistent` is scored against that verdict directly.

## Private instance

The engine carries no personal claims. A private repo (mine: `philosophy-me`, sibling to `exo` / `exo-me`) depends on this
one as an editable uv path dependency and supplies its own `data/<family>/arguments.json`, `runs/` and `.env`.
Paths resolve, in order: `PHIL_DATA_DIR` / `PHIL_RUNS_DIR` env vars; else `./data` and `./runs` of the current working
directory if they exist; else this repo's own. `.env` is read from the CWD first, then the engine root (real env wins).
`phil families` lists `<data>/*/arguments.json`. Run `uv run phil ...` from inside the instance repo.

## Phase 0 gate

`phil gate` passes iff (a) all five stages (reconstruct, formalize, judge, select, iso) ran over all
arguments with 0 failed jobs; (b) selection demonstrably rejects trivialized candidates:
`rejected_trivial` + judge hard-rejects carrying `conclusion_smuggled` >= 1 across the run (waived for mock
runs; the orphan-conclusion check is a soft penalty now, so `rejected_trivial` alone was unreachable); and
(c) verdict agreement vs expected >= 60% over arguments with an expected verdict (percentage printed;
waived for mock runs, whose canned responses say nothing about the arguments).

Current result:
- Mock: **PASS** (see `runs/report-mock.md`). Caveat: the mock formalizes most arguments as opaque atoms,
  so verdict agreement is only meaningful for `cogito` (the mock's hand-written case); the gate is an
  orchestration check, not evidence about formalization quality.
- Live: **PASS** on both runs (2026-10-15), but verdict agreement is 11/15 from human reconstructions and 5/15 from LLM reconstructions; see "Phase 0 findings" below.

## Phase 0 findings

First live runs against the real Claude API (2026-10-15; reason model `claude-sonnet-5-5`, judge `claude-haiku-5-5`,
`--n-candidates 2`). Reports: `runs/report-live-1.md` (run 6, `--from-human`) and `runs/report-live-2.md`
(run 7, LLM reconstructions). Both gitignored.

**Transport fix needed before anything ran.** `anthropic` 1.15 removed the `temperature` kwarg from
`messages.create()` (TypeError on every call), and Sonnet 5.5 returns 400 for forced `tool_choice`.
`LLMClient._complete` now sends no temperature (still recorded in `llm_call` / cache key for provenance) and
uses structured outputs (`output_config.format`, every object closed with `additionalProperties: false`);
schemas with open dict fields (`JudgeOut.scores`) fall back to a forced tool, which Haiku 5.5 still accepts.
No stage logic changed. Consequence: the two candidates are sampled at the API default, not at 0.7/0.8, so
they are often near-identical (`induction-circular` run 1: both candidates the same formulas).

### Gate

Both runs: **PASS** (all five stages, 0 failed jobs; `rejected_trivial` = 2 in run 1, 4 in run 2). Note that
in run 2 two of the four "trivial" rejections are `premises inconsistent (argument vacuously valid)` on
`ship-of-theseus-gradual`, i.e. the checker finding the *expected* inconsistency, which the gate counts as a
trivialization reject.

### Verdict agreement

| argument | expected | run 1 (from human) | run 2 (LLM recon) |
|---|---|---|---|
| cogito | valid | valid ✓ | valid ✓ |
| aristotle-function | valid | valid ✓ | open ✗ (contested) |
| gettier-counterexample | valid | valid ✓ | open ✗ |
| epicurus-death | valid | valid ✓ | valid ✓ |
| singer-drowning-child | valid | valid ✓ | open ✗ |
| kalam | valid | valid ✓ | valid ✓ |
| thomson-violinist | valid | valid ✓ | open ✗ |
| epicurean-trilemma | valid | valid ✓ | open ✗ |
| divine-hiddenness | valid | valid ✓ | valid ✓ |
| hobbes-state-of-nature | valid | valid ✓ | open ✗ (both candidates orphan-predicate trivial) |
| xunzi-origin-of-ritual | valid | valid ✓ | open ✗ |
| sorites-heap | inconsistent | open ✗ (no unsat candidate) | refuted ✗ (no unsat candidate) |
| ship-of-theseus-gradual | inconsistent | refuted ✗ | open ✓ (both candidates unsat) |
| mill-desirable | invalid | open ✗ (both candidates orphan-predicate trivial + judge) | open ✗ (contested) |
| induction-circular | valid | refuted ✗ | open ✗ |
| **agreement** | | **11/15** | **5/15** |

| run | contested | rejected_trivial (checker only) | rejected_judge | unsat candidates |
|---|---|---|---|---|
| 1 (from human) | 0 | 2 | 4 | 0 |
| 2 (LLM recon) | 2 (aristotle-function, mill-desirable) | 4 | 11 | 2 |

Live golden test (`uv run --env-file .env pytest -m llm`; the plain `uv run pytest -m llm` is skipped because
`conftest.py` checks the environment before `config.load_env` runs): **FAIL**, 1/4 (needs 3):

```
cogito               expected=valid      selected=valid    OK
epicurus-death       expected=valid      selected=open     DIFF
mill-desirable       expected=invalid    selected=open     DIFF
induction-circular   expected=valid      selected=refuted  DIFF
```

`epicurus-death` was `valid` in run 1 and `open` here from the same human reconstruction: run-to-run
variance at the judge threshold (fresh in-memory store, no cache).

### Isomorphism (vs the 3 human strong pairs)

| run | found | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| 1 | cogito~kalam, divine-hiddenness~epicurean-trilemma | 1 | 1 | 2 | 0.50 | 0.33 |
| 2 | cogito~kalam | 0 | 1 | 3 | 0.00 | 0.00 |

The false-friend group (cogito / kalam / induction-circular, graded `weak_isomorphic_to`) **was** matched in
both runs: `cogito~kalam` is the only false positive each time (same skeleton hash; the matcher has nothing
beyond skeleton shape to separate weak from strong pairs). `induction-circular` was not matched to either
because its P2 carries an extra `method` guard. `hobbes~xunzi` and `sorites~ship-of-theseus` were never
found: the formalizer picks different arities/guards per argument, so the skeletons differ.

### Concept registry (per run, from that run's candidates)

| run | distinct (label, sense) | labels with >1 sense (sense-split) | senses with >1 label (alias) |
|---|---|---|---|
| 1 | 97 | 14 | 10 |
| 2 | 183 | 21 | 15 |

Typical rows: `person` → `person:human` / `person:moral` / `person:moral-person`; `exists:actual` ←
`exists_actual` / `exists_actually`. Almost all splits are spelling variants of one sense, not real
disambiguation. The `concept` and `review` tables are global (no `run_id`), so `phil report`'s registry and
review sections also include the mock runs' opaque `p1..p5, c` atoms; the numbers above were recomputed from
each run's `formalization` rows and the review rows from each run's job time window.

### Review queue (rows created during the run)

| reason | run 1 | run 2 |
|---|---|---|
| sense_mismatch_hint | 4 | 94 |
| gloss warning (connective word in gloss) | 10 | 35 |
| label reused across senses | 15 | 32 |
| same sense under different labels | 9 | 20 |
| contested selection | 0 | 2 |
| **total** | **38** | **183** |

### Tokens and cost (from `llm_call`; prices Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per MTok)

| run | stage | model | calls | in | out | est. $ |
|---|---|---|---|---|---|---|
| 1 | reconstruct | sonnet-5-5 | 14 | 20,736 | 11,755 | 0.16 |
| 1 | formalize | sonnet-5-5 | 28 | 96,024 | 35,787 | 0.55 |
| 1 | judge | haiku-5-5 | 28 | 63,885 | 10,010 | 0.01 |
| 2 | reconstruct | sonnet-5-5 | 0 (cache hits from run 1) | | | |
| 2 | formalize | sonnet-5-5 | 30 | 106,100 | 76,885 | 0.98 |
| 2 | judge | haiku-5-5 | 32 | 87,100 | 16,995 | 0.02 |
| **both** | | | | **373,845** | **151,432** | **≈ $1.72** |

Plus ≈ $0.15 for the smoke runs (runs 4–5) and the golden test. `phil calls` sums across all runs and has
no `config.PRICES`, so the per-run numbers come from a direct query. The reconstruct stage runs the LLM even
under `--from-human` (its output is simply not picked), which is where run 1's reconstruct cost comes from.

### Three biggest failure modes

1. **Formalizer will not supply bridge premises, so valid arguments come out `refuted`.** The prompt
   forbids adding premises, so wherever the human reconstruction leaves a trivial link implicit the checker
   finds a countermodel. `induction-circular` (both runs): P2 is formalized as
   `(forall x (=> (and (method x) (succeeded_in_past x)) (succeeds_in_future x)))` but nothing asserts
   `(method induction)`, so Z3 refutes it with `method = {}`. The sorites pair is the same shape: the
   9999-step chain is not a premise, so `sorites-heap` is `sat`/`refuted` instead of unsat in both runs.
   The flip side is `mill-desirable`: the orphan-conclusion-predicate rule correctly notices
   `desirable_as_end` appears only in C, but then rejects both candidates as trivial, so the expected
   `refuted` becomes `open`.

2. **Judge thresholds and hard-reject flags dominate selection once reconstructions are LLM-made.**
   Run 2: 11 of 30 candidates hard-rejected, 10 of 15 arguments `open`. `gettier-counterexample`: the LLM
   reconstruction has 6 premises; both formalizations get `missing_implicit_premise` (hard reject) plus
   min_score 0.4–0.5, although Z3 finds both valid and the judge's own comments are about wording
   ("adds the epistemic qualifier", "'so' rendered as a conjunct"). The judge is charging the formalizer for
   choices made at reconstruction time, and `min_score < 0.6` on any single premise kills a candidate.

3. **Sense ids are not stable across candidates or arguments, which breaks both the registry and iso.**
   The same predicate gets a fresh sense string per call (`succeed:past` vs `success:past`,
   `prevent:ability` vs `prevent:able`), producing 21 sense-split labels and 94 `sense_mismatch_hint` rows in
   run 2, while genuinely different predicates (`cogito` P2 vs `kalam` P1, both `(forall x (=> (A x) (B x)))`)
   share a skeleton and are matched as isomorphic in both runs. Iso recall fell from 0.33 to 0.00 when the
   reconstructions were LLM-made because arity and guard choices vary per argument.

### Other issues logged (not fixed)

- `--from-human` still spends reconstruct calls (see cost).
- `candidates` column in `phil report` counts formalizations across runs for the same reconstruction row
  (`cogito` shows 4 in run 1 because the smoke run 5 shared the human reconstruction).
- `concept` / `review` tables lack `run_id`; report sections mix runs.
- `conftest.py` skip check runs before `config.load_env`, so `.env` alone does not enable `-m llm`.
- Candidate diversity now depends on API-default sampling (temperature no longer sent).

### Re-run after fixes (run 8, 2026-10-15, `--from-human --n-candidates 3`, engine 7329580)

Report: `runs/report-live-3.md`. Gate: **FAIL** on criterion (b) only — all five stages ran with 0 failed
jobs, but `rejected_trivial` is now 0 because the orphan-conclusion check became a soft penalty and the only
vacuous candidates were the expected-inconsistent ones, which the gate no longer counts. Criterion (b) is
effectively unreachable with the fixed engine and needs restating.

| run | agree | contested | rejected_trivial | rejected_judge | est. $ |
|---|---|---|---|---|---|
| 1 (from human, n=2) | 11/15 | 0 | 2 | 4 | 0.72 |
| 3 (from human, n=3, fixed) | **12/15** | 1 (induction-circular) | 0 | 6 | 0.94 |

Changes vs run 1: `induction-circular` now `valid` (one candidate drops the `method` guard; contested 2–1
with the refuted ones), `mill-desirable` still `open` (all three candidates judge-rejected rather than
trivial-rejected), `sorites-heap` and `ship-of-theseus-gradual` still `refuted` — no candidate makes the
chain premise explicit, so neither comes out `inconsistent`.

Isomorphism: precision n/a, recall 0.00. The three strong human pairs are all missed again; the richness
gate now files `cogito~kalam`, `cogito~induction-circular` and `induction-circular~kalam` as shape-only
weak-isomorphic, and all three are graded weak in the data, so there are no false positives. Concept
registry for the run: 149 (label, sense) rows, 37 labels with more than one sense. Review queue for the
run: 38 label-reused-across-senses, 17 same-sense-different-label, 11 gloss warnings, 5 sense-mismatch
hints, 3 orphan-conclusion-predicate, 1 contested. The `candidates` column still counts formalizations
across runs for the same human reconstruction row (5–7 shown instead of 3).

## Fix round after Phase 0 (re-run live: see "Re-run after fixes" above)

1. Candidate diversity: `config.STRATEGY_HINTS[candidate_idx % 4]` is appended to the formalize user prompt and stored in `formalization.strategy_hint`.
2. Orphan conclusion predicate is a soft flag (`CheckReport.orphan_conclusion_predicate`, select penalty `ORPHAN_CONCLUSION_PENALTY`=0.10, review row); a hard trivial reason only if C is also a tautology.
3. Verdict `inconsistent` (premises unsat). Select keeps unsat candidates when the human `expected_verdict` is `inconsistent` or >= 2 candidates agree; the gate does not count those as trivialization; report/dashboard score against `inconsistent` directly. iso also considers `inconsistent` selections.
4. Iso richness (`stage_iso.is_rich`): bare shapes are recorded as `weak-isomorphic` ("shape-only"); in `iso_eval` they are never FP (`weak_correct` when graded in `weak_isomorphic_to`) and are outside precision/recall.
5. `senses.normalize_label/normalize_sense` run inside `Store.upsert_concept` (`concept.raw_label` keeps the original); `concept` and `review` have `run_id` (concepts are scoped per run); old DBs are migrated and backfilled on open; report/dashboard filter by run.
6. Judge samples `JUDGE_SAMPLES`=2 (sample_idx 0, 1), scores averaged, `hard_reject` only if every sample has a hard flag; `JudgeReportX.judge_call_ids`.
7. conftest loads `.env` first; live tests are skipped unless `-m llm` is given.

## Fix round 2 (after live runs on two families)

1. Gate (b) redefined, gate (c) added (agreement >= 60%); `report.gate`, `phil gate`, report and dashboard text updated.
2. Judge `min_score` below `JUDGE_MIN_SCORE` is a select-score penalty (`JUDGE_MIN_PENALTY` 0.15 per failing premise, cap 0.3), not a filter. Hard judge flags (both samples agree), `mean_score` and `conclusion_score` still filter.
3. `conclusion_smuggled` is ignored when the human expected verdict is `inconsistent` and the candidate is unsat; the judge prompt says an inconsistent premise set is not smuggling.
4. `PremiseIn.shared_id` (optional) survives ingest/store; report and dashboard gain a "Shared premise reliance" table and list formally idle shared premises.
5. Iso uses the top-ranked parsed valid/inconsistent candidate of `open` arguments, tagged `unverified: true`; precision/recall stay selected-only, with a second "incl. unverified" line.
6. Formalize prompt carries a per-run sense registry (<= 60 entries, most-used first) with a reuse-or-contrast instruction; `normalize_sense` folds a sense part repeating the label. `feels:good` vs `feels_good:...` is not folded mechanically (indistinguishable from `exists:actual` for `exists_actual`); the registry steers instead.
7. `--from-human` makes no reconstruct LLM call (the human reconstruction is copied into the run, source `human`).
8. Judge prompt: implicit premises strong enough to make the empirical premises idle are flagged `strengthened`.

## Fix round 3 (after rees family run 2, engine 828c559)

1. Candidate diversity. `config.STRATEGY_HINTS` are structural bands over the predicate count (lean <= P+1,
   rich >= P+2 with explicit sorts, relational in [P, P+3] with binary relations, propositional-lean), filled from
   the premise count by `stage_formalize.strategy_hint(idx, n_premises)`; every candidate after the first gets a
   DO NOT REUSE block listing the (name/arity) predicate sets earlier candidates used. `stage_common.fingerprint`
   (normalized formulas + predicate set) dedupes identical candidates before the judge: the later candidate copies
   the earlier report (`JudgeReportX.duplicate_of_candidate`, no judge call). `SelectionResultX.diversity`
   (`distinct/n`, distinct predicate sets) is a report column, a report summary line ("all candidates identical
   in: ...") and a dashboard column.
2. Judge flag split. `missing_implicit_premise` is replaced by `reconstruction_gap` (soft: review row on the
   reconstruction, never rejects a formalization) and `formalization_omits_premise` (hard). `HARD_REJECT_FLAGS` =
   conclusion_smuggled, sense_drift, formalization_omits_premise. `hard_rejects` recomputes from `sample_flags`,
   so reports stored by the round-2 engine with the legacy flag are re-read as soft (e.g. `fiction-beats-lies`,
   Z3-valid at judge means 0.85-0.96, would now be selected). `prompts/judge.v1.md` describes both flags.
3. `mean_score` below `JUDGE_MEAN_SCORE` is a select-score penalty (`JUDGE_MEAN_PENALTY` 0.15), not a filter;
   `conclusion_score` is the only judge score that filters. Selections carry `status` (`selected`, `judge-weak`
   = decided by Z3 and selected with judge mean below threshold, `open: decided candidates all rejected`,
   `open: no decided candidate`, `open: no candidates`) and `judge_weak`; report and dashboard show the status
   column, a "decided by Z3 but judge-weak" line, and a review row per judge-weak selection.
4. Iso second pass (`stage_iso.match_relaxed`, run over the pairs the strict pass misses). Diagnosis on
   `commitment-reauthoring ~ evaluator-drift` (both sides Z3-valid in run 2): the skeletons differed only by an
   extra `author_of` typing guard repeated in P2/P3 antecedents, explicit `Agent`/`Rule` sorts vs one sort,
   binder order (`(r a)` vs `(l e)`, which `normalize` alpha-renames by position), and the argument order of one
   binary relation. The relaxed skeleton (`stage_iso.relax`) erases sorts, flattens curried implications, drops
   guard-only atoms from antecedents that keep a substantive conjunct, drops Z3-redundant premises, and the
   matcher compares under binder-canonical text with binary argument flips, then Z3-confirms on the relaxed
   formulas. Stored as `isomorphic-to` with `method: relaxed`, `abstractions`, `flips`; strict precision/recall
   exclude it, the "incl. unverified + relaxed" line includes it; report and dashboard list the relaxed pairs.
   All nine candidate combinations of the rees pair match under the relaxed pass (none strictly).
5. Shared reliance: `open` arguments count through their best parsed valid/inconsistent candidate
   (`stage_iso.top_parsed_candidate`), tagged unverified (`*` in the table; `idle` vs `idle_verified`), as iso does.

## Fix round 4 (after rees family run 3, engine 356117f)

1. Self-confessed bridges. `stage_select.confession_in_notes` parses the formalizer's `notes` clause by clause
   (parentheticals stripped) for admissions that a formula goes beyond / adds to / strengthens / "puts the bridge
   inside" a stated premise, with negation patterns so "the bridge is missing and was not added", "a bridge such as
   X is not added, because that would strengthen P3" and "rather than add a premise" do not count. The judge now
   also sees a FORMALIZER NOTES block (`prompts/judge.v1.md`) and may raise `formalization_adds_bridge`; it counts
   only when every sample raises it (`confession_in_judge`). The flag is neither hard nor soft: it is a confession
   signal. Bridge rule in `select_for`: a confessed candidate is never selected while a faithful sibling is
   Z3-decided (rejected with reason `confessed bridge (...)`, counted in `SelectionResultX.rejected_bridge`); if
   every surviving candidate confesses, the best is chosen but the verdict is `open` with status
   `needs bridge: <quote>`. `SelectionResultX.confessed` keeps the quotes; review rows on the formalization
   (`confessed bridge:`) and, for the withheld case, on the reconstruction (`needs bridge:`).
   Control redundancy: for an expected-invalid argument, a Z3-valid candidate with redundant premises is flagged
   `control_valid_via_redundancy` ("valid without [P3]") with a review row.
   On run 3 the heuristic fires on exactly 1 of 87 candidates: `never-die` candidate 2 ("I therefore put the
   bridge inside P2"), which is the control that went false-valid. Re-selecting rees3.db: never-die `valid` ->
   `open: decided candidates all rejected` (its two faithful siblings are Z3-refuted but rejected on
   conclusion_score 0.65 / 0.60, so the control still does not reach `refuted`); no other row changes
   (agreement 20/29 unchanged). Regression: `tests/test_fix_round4.py` (mock candidate whose notes say
   "I put the bridge inside P2").
2. Iso third pass (`stage_iso.match_projected`, after the relaxed pass). Diagnosis of the run-3 selected pair
   `commitment-reauthoring ~ evaluator-drift`: skeleton hashes differ on three counts (2 sorts vs 1; 5 binary
   predicates vs 3 binary + 1 unary, `costly_to_keep_for/2` vs `costly_to_keep/1`; a two-atom substantive
   antecedent `(and (evaluates_loop r l) (belongs_to_loop r l))` in P1 and C vs one atom). The relaxed pass erases
   the sorts but cannot cross the other two: both atoms also occur in C so neither is guard-only, and nothing
   equates a unary with a binary predicate. All three premises are in both unsat cores (`redundant_premises` empty
   on both sides), so matching on the core subset cannot help either. The projected pass applies two
   content-neutral rewrites to the relaxed skeletons: cluster collapse (atoms that always occur together as
   co-conjuncts with identical arguments, and nowhere else, become one predicate: equivalence-preserving) and
   arity projection (drop one argument position of a predicate when that position is uniformly a bound variable or
   one constant, tried only to make the two arity profiles equal: a specialization, so stored as
   `method: projected` with `arity-projected:` in the abstractions, never as a strict match). The result is run
   through the relaxed matcher (binder-canonical text, binary flips, Z3 confirmation); among several matching
   projections the one with the fewest flips wins. On rees3.db the pair is found with 0 flips
   (`cluster-collapsed:belongs_to_loop+evaluates_loop`, `arity-projected:costly_to_keep_for/2->1@1`); recall incl.
   passes 0.00 -> 1.00, the false friend unchanged. Fixture pair `tests/fixtures/iso/iso_projected_{a,b}.json`
   reproduces the shape with neutral vocabulary (strict: no; relaxed: no; projected: yes). For pairs in the human
   iso / weak-iso truth that no pass matches, an `iso-skipped` row `projected: declined: <which signature component
   differs>` is written and listed under the report's Isomorphism table.
3. Report / dashboard: `confessed bridges` column (per candidate: confessed + rejected / chosen-verdict-withheld,
   and `control valid without [P..]`), a "Confessed bridges (round 4)" summary line, `projected pass` rows in the
   Isomorphism table (and `precision/recall incl. unverified + relaxed + projected`).
