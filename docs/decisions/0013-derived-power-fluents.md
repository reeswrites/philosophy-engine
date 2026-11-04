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

## Amendment 2026-11-03: an action no may/must rule names is not enabled
The second review (`docs/reviews/2026-11-03-phase0-second-review.md`, items 1-2) found that `(enabled a ...)` read
constant true for an action no `may`/`must` rule names, so deleting the very rules that grant a power (police R3+R5,
guardianship R9) left the derived power in place: the falsifier the Decision promises did not run. Amended: `(enabled
a args)` is constant false when no `may`/`must` rule names `a` (the warning stays, and says "never enabled"); a
`must_not` alone still does not enable. Both `rules_lower` and `rules_reference` implement this independently. The
trace semantics is unchanged: an action no rule names may still fire (that is the permissive floor of the model),
but it confers no power, because a power is what the rules grant. Consequence: a derived fluent whose every action
is unregulated is constant false, and a universal property over it may hold vacuously, which the vacuity flag reports.

## Amendment 2026-11-03: Monotonicity laws are scoped by enablement polarity
The metamorphic laws "adding a must_not / removing a may never adds reachability" hold only for properties monotone in
enablement. `no_standing` (mwpa-suit) is defined over the negated derived power `has_standing := (enabled sue ...)`, so
removing R16 (wife may sue) correctly makes it reachable. Rule (tests/test_rules_meta.py, `enablement_polarity`): walk the
property and, transitively, the `derived` expression of every derived fluent it mentions, tracking negation parity
(`not` and the antecedent of `=>` flip; `<=>`/`xor` count both). A property is monotone iff no `(enabled ...)` occurs
under an odd number of negations; anti-monotone iff it occurs only under odd. The two laws are asserted for monotone
properties only; for anti-monotone ones the mirror holds (removing a may never removes reachability). Mixed-polarity
properties are exempt from both. mwpa-suit minus R16 -> `no_standing` reachable is pinned as a regression test.

## Amendment 2026-11-05: liberty actions
The 2026-11-03 amendment made an action no `may`/`must` rule names confer no power. That is right for powers a rule
grants (earnings, standing) and wrong for liberties an institution withholds by prohibition (coverture R7 `must_not
contract`): cutting a sole prohibition could never move a derived power, because with nothing granting it the power was
already constant false. Experiment 2026-11-05: flipping nameless actions to enabled across the board moved 14
preregistered verdicts (coverture read liberal), so the split cannot be a global default; it is declared per action by
the encoder, preregistered. `ActionDecl.liberty: bool = False`. For a liberty action instance, `(enabled a args)` at t is
true iff no disability (a `must_not` with `or_else` null) on that instance has its condition true at t, whether or not a
`may`/`must` names it (a `may`/`must` on it is redundant for enablement; a `must` still matters as an obligation). A
power action (the default) keeps the 2026-11-03 semantics. This is the Hohfeldian liberty/power distinction: a liberty is
the absence of a duty not to, a power is a granted ability to change legal relations. Trace semantics is unchanged
(`regulated_actions` and the firing-enablement block still let an unregulated action fire); liberty touches only the
`(enabled ...)` pseudo-predicate in derived fluents, and the "never enabled" warning no longer fires for liberty actions.
Both `rules_lower.Lowering.enabled` and `rules_reference.power` implement it independently.
