# 0004. Entailment, not prediction

## Context
Z3 can say what a rule set permits or forces. It cannot say how often anything happens. Institutional analysis invites forward claims ("this reform will fail"), and a checker that appears to support them would be misleading.

## Decision
`reachable` means the rules permit a state, not that it occurs. `invariant` and `persists` say what the rules force within k steps. Frequency, uptake and behaviour belong to a separate agent-based layer, which is Phase 1. No forward-looking claim about a real institution is made until backtests on historical cases pass.

## Alternatives rejected
Attaching probabilities to rules inside the solver: invents numbers with no calibration. Reporting reachable states as likely outcomes: conflates permission with occurrence.

## Consequences
Phase 0 results are statements about encodings. They are strong on structure and silent on outcomes. Reports must use the verbs "permits", "forces" and "open", and judge-stage traces are checked against the source, so a surprising trace is treated as a likely encoding error.

## Status
accepted
