# 0013. Power fluents are derived from what the rules enable, never asserted as effects

## Context
The skeptical review (`docs/reviews/2026-11-03-phase0-skeptical-review.md`) found the headline result built in: `can_sanction` was set as an effect of `marry` / `dispatch_officer` / `investigate` / `acquire` and never cleared, so deleting every `may detain` and `may use_force` rule left `care_and_sanction_same_role` unchanged. `has_standing`, `can_claim_for` and `controls_reproduction` had the same shape, and companion-guardianship's verdict rested on an `initial` literal, not on R9. An asserted power survives the removal of the rule that grants it, so the checks could not tell a rule set from its paraphrase.

## Decision
A power is what the rules enable. `FluentDecl.derived` defines a fluent by an S-expression over `(enabled ACTION args...)` and other fluents: `(enabled a x y)` holds iff some `may`/`must` rule on `a` with that binding has its condition true and no `must_not` disability (`or_else: null`) does. A derived fluent has no frame axiom or initial value and cannot appear in effects, `initial`, `defaults`, `initial_free` or an aim; cycles are errors. The reference semantics computes the same reading independently. With it: must-be rules nothing can break are reported `inert` (gate (a) fails on a `load_bearing` one); invariant and persists verdicts carry a vacuity flag; the gate tests each `isomorphic_to` claim only at its precommitted level, with negative controls, and gate (c) at the preregistered `differs_on` property.

## Alternatives rejected
Adding "clear" effects wherever a rule could be removed: the encoder simulates the lowering by hand. A judge-stage check that effects mirror rules: catches the symptom late and only when the judge runs.

## Consequences
The dataset must be re-encoded; verdicts may change, which is the point. An action no `may`/`must` rule names counts as enabled (warning). Must-be on a derived fluent has no encoding yet.

## Status
accepted
