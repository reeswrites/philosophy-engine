# 0003. Time by bounded unrolling inside Z3 (k=6)

## Context
Rules about care, custody and exit only matter over time: a state is reached, persists, or is blocked. We need temporal checks without adding a second toolchain to a project that already has one solver.

## Decision
Fluents and actions get a step index t in 0..k, with frame axioms saying fluents persist unless an action changes them. Default k = 6. Everything stays inside Z3. "Unreachable within k" is reported as `open`, never as safe, and `holds_to_k` names its bound in the verdict.

## Alternatives rejected
TLA+ and NuSMV: capable, but a new dependency and a second encoding, deferred until bounded checking is shown to be the bottleneck. Symboleo with nuXmv (contracts) is the closest in method, but it targets contract obligations rather than institutions. Governatori's LegalRuleML to SPINdle, with the reparation chain operator, is the closest analogue to Or-else; we use it as a reference for conflict semantics, not as a backend.

## Consequences
Short-horizon claims are cheap and the counterexample is a concrete trace. Any claim about the long run is out of reach and must stay `open`. If k=6 hides behaviour in a test case, the case is recorded, and the bound or the tool is revisited.

## Status
accepted
