# 0012. Participation in encoding

## Context
Every institution so far is encoded from statutes by the author and automated assistants. The theory's "margins first" test (Combahee) appears in the prioritization criteria but not in the process that produces the data. An encoding nobody who lives under the institution has seen can be internally consistent and still unfaithful.

## Decision
Before the dataset grows past Phase 0, add a coding step in which people who live under an institution review its encoding. It is modeled on inter-coder agreement in the Institutional Grammar literature (IG 2.0 Codebook, arXiv 2008.08937). Disagreements are recorded as alternative rule sets on the entry, in a `contested` list. Verdicts that diverge across alternatives are reported as outputs and not resolved by the author.

## Alternatives rejected
Author-only encoding with notes on disputes: hides the dispute in rules that look neutral (see 0008). Reviewer consensus before publishing: forces agreement that may not exist.

## Consequences
Dataset growth is slower. The schema needs a request for `contested` alternatives. The cheapest faithfulness test is encoding the author's own arrangements, which are small and fully known, and checking the engine against what the author knows.

## Status
proposed
