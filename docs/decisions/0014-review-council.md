# 0014 Review council after every batch

## Context
On 2026-11-03 the first build of the institutions family passed its own gate (36/36) and would have been published as a result. An independent reviewer that had not seen the build showed the headline claim was built into the encodings. A consistency review the same day found 28 disagreements across documents written hours apart. Both reviews were cheap relative to the work they corrected.

## Decision
Every batch of work gets a council of fresh reviewers before anything is called a result or published as one. Four seats, each a separate brief, never the agent or person who built the thing:
- Correctness: can the result be produced by construction? Delete rules, add controls, check vacuity.
- Consistency: do intent, theory, ADRs, plans, dataset notes, claims and code agree? Output: docs/reviews/<date>-consistency.md and an updated docs/claims.md.
- Scope: does this batch move the thin path in docs/plan.md, or open a front? Name what should be parked.
- Encoding faithfulness: for each new institution, someone who did not encode it reads the rules against the cited source and the back-translated counterexample traces (ADR 0012).

## Alternatives rejected
- Self-review by the builder: it is what failed.
- A single reviewer: the correctness and consistency reviews found disjoint problems.

## Consequences
Slower batches; a docs/reviews/ record that grows with the project; the claims register as the honest public summary.

## Status
Accepted 2026-11-03.
