# Claims register

One row per claim the project makes or plans to make. Status ∈ {supported, weakened, refuted, untested, retracted}.
Evidence names a test, gate criterion or review; "none" means nothing checks it yet. Last checked 2026-11-03, after the
skeptical review (`docs/reviews/2026-11-03-phase0-skeptical-review.md`) and before the ADR 0013 re-encode completes.
A claim is `supported` only if a check that could have failed passed and the review did not undercut it.

## Layer 1 results (institutions family)

| # | Claim | Where stated | Evidence | Status | Last checked |
|---|---|---|---|---|---|
| L1 | The engine rediscovers the care+control cluster (police, CPS, coverture household) from the rules alone. | theory.md rules-engine table, Phase 0 test (1); plan gate (b); ADR 0007 | gate (b) after re-encode (lease, public-library match nothing; gate reads precommitted level); second review: unregulated actions count as always enabled, strand tags still load-bearing, a 6-rule airline-flight matches | weakened | 2026-11-03 |
| L2 | The unarmed crisis team is excluded from the care+control cluster. | plan gate (b); theory Phase 0 test (1) | gate (b) after re-encode; second review: crisis-team `none` at every level; but `enabled` default means deleting permissions strengthens power claims | weakened | 2026-11-03 |
| L3 | One-rule minimal pairs are told apart at the iso level (reported "one rule apart"). | plan gate (c)/(f); theory Phase 0 test (2); roadmap | gate (c), (f); `test_rules_iso.py`; review: "Iso distance 1 is syntactic and real" | supported | 2026-11-03 |
| L4 | One-rule minimal pairs get different *verdicts* on the preregistered property. | plan gate (c); ADR 0013 | gate (c) via `differs_on`; second review: loader now rejects initial literals on derived fluents; guardianship verdict rests on R9 (disability vs may); swapped property disclosed as post hoc | supported | 2026-11-03 |
| L5 | Cosmetic reform (owner→guardian rename) is detected: renamed ≅ ownership, guardianship ≠ ownership. | plan gate (f); ADR 0007; theory "The rules engine now tests for it" | gate (f) `pure_rename`; review: "cosmetic rename is detected" | supported | 2026-11-03 |
| L6 | The kibbutz children's house regendered care via an implicit assignment rule, and the engine finds it (`care_assigned_by_sex` persists, implicit rule flagged). | plan gate (d); ADR 0007; intent kill switch; theory Phase 0 test (3) | gate (d) is `deferred`; institution not encoded (batch 2 draft, preregistered) | untested | 2026-11-03 |
| L7 | Happy the elephant's habeas denial is a second implicit-rule failure (remedy must be immediate release). | ADR 0007; plan extension 4 | none (not encoded; sources partly unconfirmed) | untested | 2026-11-03 |
| L8 | The floor ("you can walk away unless a rule stops you") had to be encoded as a default (`defaults: can_exit: true`), not as a rule. | theory roadmap "Done today"; plan schema-builder appendix | dataset convention; no test isolates it; review 5c notes `no_standing` trivially unreachable on police-crisis for the same reason | weakened | 2026-11-03 |
| L9 | ADICO needs state obligations (must-be) alongside action obligations. | ADR 0009; theory roadmap | check-all 29/36 → 36/36 under `one`; `test_rules_lower.py`; review 3: four must-be rules are inert, including the cps "care" leg | weakened | 2026-11-03 |
| L10 | The Z3 lowering matches an independent reference semantics. | theory roadmap ("313 tests incl. independent reference semantics"); ADR 0013 | `tests/test_rules_meta.py`, `rules_reference.py` (metamorphic + differential) | supported | 2026-11-03 |
| L11 | Strand tags alone do not make care+control isomorphic; condition abstraction does. | ADR 0010 Consequences | review 4: retagging crisis-team R3 produces a match; the form needs only one superadditive + one rival `may` | refuted | 2026-11-03 |
| L12 | Care+control iso holds at `guard+strands` and at no other level, and the level was precommitted. | ADR 0010; dataset `isomorphic_to` | review 4: `rules_gate.py` slid exact→guard and never read the level (fixed per ADR 0013; not yet re-run) | weakened | 2026-11-03 |
| L13 | Negative controls (a lease and one unrelated institution) do not match care+control at the precommitted level. | ADR 0013; review required fixes | gate (b) `not_isomorphic_to_control`; no control institution in the dataset yet | untested | 2026-11-03 |
| L14 | Power fluents derived from enabledness let the checks tell a rule set from its paraphrase (deleting `may detain` changes the verdict). | ADR 0013 | re-encode in progress; no result yet | untested | 2026-11-03 |
| L15 | Verdicts match expectations 36/36 (gate (e) ≥ 60%). | ADR 0009; dataset README; theory roadmap | check-all before ADR 0013; ADR 0013 says verdicts may change | weakened | 2026-11-03 |
| L16 | Unreachable within k is reported `open`, never `safe`; `reachable` is permission, not prediction. | ADR 0003, 0004; glossary; plan | `test_rules_checks.py`; verdict vocabulary | supported | 2026-11-03 |
| L17 | The dark twin: a gig platform keeps exit cheap and strips insurance and voice (`worker_uninsured` reachable, `rules_revisable_by_subject` open). | plan dataset table; batch 2 §4 | preregistered, not encoded | untested | 2026-11-03 |
| L18 | Ostrom's fishery makes rule revision reachable by the users, not only by the state. | plan dataset table; batch 2 §5 | preregistered, not encoded | untested | 2026-11-03 |

## Prior-work and method claims

| # | Claim | Where stated | Evidence | Status | Last checked |
|---|---|---|---|---|---|
| M1 | No prior work runs a solver over Institutional Grammar statements. | ADR 0001, 0002 | literature survey of three sources (IG-Parser, arXiv 2505.13393, arXiv 1711.06128); Symboleo/nuXmv and SPINdle named as nearest analogues in ADR 0003 | supported (survey only; not systematic) | 2026-11-03 |
| M2 | Few have combined economic-planning and norm simulation around liberation itself. | theory Precedents | precedents table; no systematic search | untested | 2026-11-03 |
| M3 | Bounded unrolling at k=6 is enough for the Phase 0 properties. | ADR 0003 | no recorded case where raising k changed a verdict; metamorphic test "raising k never removes reachable" | untested | 2026-11-03 |
| M4 | Expectations are written before runs (preregistration). | intent; CONTRIBUTING 2, 5 | batch 2 preregistered; dataset README records expectation edits after check-all (review 5) | weakened | 2026-11-03 |
| M5 | Encodings are reviewed by people who live under the institution. | ADR 0012 (proposed); CONTRIBUTING | none; no `contested` field; all entries author-encoded | untested | 2026-11-03 |

## Theory-level claims (Layers 2–5; no forward claim until layer 3 passes)

| # | Claim | Where stated | Evidence | Status | Last checked |
|---|---|---|---|---|---|
| T1 | Floor first: a material floor precedes collective power and standing in a liberation sequence. | theory Sequence; glossary "material floor"; roadmap layer 5 pass test | none; intent lists it as a hypothesis; backtest inventory names counter-cases (property acts, no-fault divorce) | untested | 2026-11-03 |
| T2 | Care is a crossroads (touches floor, power and imagination), not a master key. | theory Prioritizing | none | untested | 2026-11-03 |
| T3 | Substitution (technology) is necessary but not sufficient; capital finds another use. | theory non-human levers; plan extension 5 (whaling) | whaling/margarine history cited; preregistered `whaling-kerosene` encoding not built; backtest 1 planned | untested | 2026-11-03 |
| T4 | Standing comes last in practice because courts weigh floodgates; the floor must shrink them first. | theory non-human additions 2 | Happy/Cecilia cases cited; contradicted in intent by property acts/no-fault divorce | untested | 2026-11-03 |
| T5 | Cosmetic reform is a distinct failure mode (rename or revocable exit changes nothing structural). | theory non-human additions 4 | L5 at the encoding level only | supported (encoding level) | 2026-11-03 |
| T6 | Liberation starts when surplus lets people see a bundle and assurance lets them leave together. | theory How liberation starts | none; layer 2 gate (a)/(b) would test the assurance half | untested | 2026-11-03 |
| T7 | A committed minority of about 25% flips a convention. | theory Assurance, Precedents | Centola 2018 cited; contested for costly behaviour; layer 2 gate (b) records rather than asserts it | untested | 2026-11-03 |
| T8 | Rules lead change rather than trail it (the planner reading of the theory). | intent "would surprise the author"; roadmap "Rule" | backtest inventory: whaling, footbinding, Norway quota recorded as rules-trailed; not yet run | untested | 2026-11-03 |
| T9 | The three mechanisms (material, coordination, imagination) separate and can be switched. | intent; layer 2 plan | none | untested | 2026-11-03 |
| T10 | Freedom and flourishing add rather than conflict. | intent | none; layer 2 reports disagreement rows | untested | 2026-11-03 |
| T11 | The four failure modes (dark twin, displacement, backlash, rebundling) can be written as checkable properties. | ADR 0006; plan Checks | `worker_uninsured` (dark twin) exists in `properties.json`; no displacement, backlash or rebundling property | untested | 2026-11-03 |

## Status counts

supported 6 · weakened 8 · refuted 1 · untested 19 · retracted 0 (34 rows).
