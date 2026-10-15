# philosophy-engine

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
- `checks.verdict_of(report) -> "valid" | "refuted" | "open"`
- `fol.validate(f, reconstruction_ids=None) -> (Parsed | None, errors: list[str])` (errors are retry-feedback text)
- `fol.build_env(f) -> Env`, `fol.lower(ast, env) -> z3.ExprRef`, `fol.rename(ast, mapping)`,
  `fol.normalize(ast)`, `fol.normalized_text(ast)`, `fol.conjuncts(ast)`, `fol.predicates_used(ast, f)`
- `sexpr.parse(text) -> AST`, `sexpr.to_sexpr(ast) -> str`, `sexpr.ParseError`

Fixed seed (0), per-check timeout, one retry at 3x timeout with a `simplify;smt` tactic, z3 version
recorded in each report.

## Schema changes

`schemas.py` is frozen after builder step 1; add requests below, one line each.
Step 1 additions to the plan's `CheckReport`: `unknown_reason`, `z3_version`.
Review-fix additions: `CheckReport.unknown_probes` (z3-unknown probes; fields left None, verdict open), `SelectionResultX.rejected_judge`, `llm_call.stop_reason` (migrated via ALTER TABLE).

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
```

One-liner (live, needs `ANTHROPIC_API_KEY` in `.env`): `phil run --from-human --n-candidates 2 && phil report --out runs/report-live-1.md && phil gate`.
Offline: `phil run --mock`. Live golden test: `uv run pytest -m llm` (skipped without a key; runs 4 arguments
from the human reconstructions and needs >=3 selected verdicts to match `expected_verdict`).
Expected `inconsistent` is scored as "some candidate's premises were unsat".

## Phase 0 gate

`phil gate` passes iff (a) all five stages (reconstruct, formalize, judge, select, iso) ran over all
arguments with 0 failed jobs, and (b) selection rejected >= 1 trivialized candidate across the run
(`rejected_trivial` total >= 1).

Current result:
- Mock: **PASS** (see `runs/report-mock.md`). Caveat: the mock formalizes most arguments as opaque atoms,
  so verdict agreement is only meaningful for `cogito` (the mock's hand-written case); the gate is an
  orchestration check, not evidence about formalization quality.
- Live: **not run** (no `ANTHROPIC_API_KEY` available when this step was built).
