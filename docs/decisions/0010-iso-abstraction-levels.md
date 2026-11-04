# 0010. Isomorphism abstraction level is precommitted per claim

## Context
The iso stage compares rule sets at levels. At `exact`, conditions are literal. At `guard`, conditions are reduced to conditional or unconditional. Each level can be run with or without strand tags. The care + control cluster (`coverture-household`, `police-crisis`, `cps`) is isomorphic only at guard + strands, through the sub-signature maintain~assess and chastise~use_force under husband→officer. At exact level the three share no rule. The plan left open whether strand tags alone make care + control isomorphic by construction.

## Decision
The abstraction level for a cluster claim is precommitted in the dataset entry before the pair is run. `isomorphic_to` records the level and the expected sub-signature. A claim that passes only at a level not named in advance is reported as a finding, not as a gate pass.

## Alternatives rejected
Choosing the level after seeing results: any cluster can be made to pass by sliding the level. Fixing one global level: the cluster is real only at guard, and exact would erase it.

## Consequences
Every cross-domain "same form" result carries its level. The open question was answered the wrong way on first pass: the 2026-11-03 skeptical review showed that strand tags and guard-level condition erasure jointly make care + control match by construction (a five-rule lease matched), so the sub-signature now requires three legs (care duty, control permission on the same subject, exit bar) and negative controls in the gate (ADR 0013). Authors must think about the level when writing an entry, which costs a little time and prevents quiet drift. Findings from unplanned levels are still reported, so nothing is hidden.

## Status
accepted
