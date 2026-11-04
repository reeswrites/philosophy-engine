# Decision records

Short records of design decisions for the institutions data family. Each is 120-250 words, plain prose, one decision per file. Plan: `plans/institutions-phase0.md`. Terms: `docs/glossary.md`.

## Format

Every ADR has these sections, in this order:

- **Context**: what forced the decision.
- **Decision**: what we chose, stated so it can be checked.
- **Alternatives rejected**: what else was considered and why it lost.
- **Consequences**: what follows, including costs and open risks.
- **Status**: `proposed`, `accepted`, or `superseded by NNNN`.

A decision is changed by a new ADR that supersedes the old one, not by rewriting it.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-institutions-as-second-data-family.md) | Institutions as a second data family, not a new project | accepted |
| [0002](0002-rule-format-adico-json.md) | Rule format: ADICO as our own JSON, IG Script tags borrowed | accepted |
| [0003](0003-time-by-bounded-unrolling.md) | Time by bounded unrolling in Z3 (k=6) | accepted |
| [0004](0004-entailment-not-prediction.md) | Entailment, not prediction | accepted |
| [0005](0005-isomorphism-as-headline-result.md) | Isomorphism as the headline result, reported with its remainder | accepted |
| [0006](0006-strand-tags-bundles-implicit-rules.md) | Strand tags, bundle types and implicit rules as metadata | accepted |
| [0007](0007-dataset-clusters-pairs-and-gate.md) | Dataset as clusters and minimal pairs, with a rediscovery gate | accepted |
| [0008](0008-guardrails.md) | Guardrails on populations and contested history | accepted |
| [0009](0009-state-obligations.md) | State obligations: an aim can be a fluent (must-be), not only an action | accepted |
| [0010](0010-iso-abstraction-levels.md) | Isomorphism abstraction level is precommitted per claim | accepted |
| [0011](0011-dual-use-and-scope-limits.md) | Dual use and scope limits | accepted |
| [0012](0012-participation-in-encoding.md) | Participation in encoding | proposed |
| [0013](0013-derived-power-fluents.md) | Power fluents are derived from what the rules enable, never asserted as effects | accepted |
| [0014](0014-review-council.md) | Review council after every batch | accepted |
| [0015](https://github.com/reeswrites/computational-liberation/blob/main/docs/decisions/0015-layer2-abm-design.md) | Layer 2 ABM design choices (A1–A7); lives in computational-liberation | accepted |
| [0016](https://github.com/reeswrites/computational-liberation/blob/main/docs/decisions/0016-failure-mode-axes.md) | Failure modes on three axes (who pays / rule / time); lives in computational-liberation | accepted |
