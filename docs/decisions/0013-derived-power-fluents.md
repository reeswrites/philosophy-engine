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

## Amendment 2026-11-05: default-capacity actions

(Date convention: this heading and the "Experiment 2026-11-05" below were written late on 2026-11-04 local time; commit timestamps are authoritative, as computational-liberation plans/priority-slice1-results.md states.)
The 2026-11-03 amendment made an action no `may`/`must` rule names confer no power. That is right for powers a rule
grants (detain, attach, reassign) and wrong for default capacities an institution withholds by prohibition (coverture
R7 `must_not contract`): cutting a sole prohibition could never move a derived power, because with nothing granting it
the power was already constant false. Experiment 2026-11-05: flipping nameless actions to enabled across the board moved
14 preregistered verdicts (coverture read liberal), so the split cannot be a global default; it is declared per action by
the encoder, preregistered. `ActionDecl.default_capacity: bool = False` (the old key `liberty` was accepted as an
input alias; the alias was removed 2026-11-04 after the dataset sync). For a default-capacity action instance,
`(enabled a args)` at t is true iff no disability (a `must_not` with `or_else` null) on that instance has its condition
true at t, whether or not a `may`/`must` names it (a `may`/`must` on it is redundant for enablement; a `must` still
matters as an obligation). A power action (the default) keeps the 2026-11-03 semantics. A default capacity is what a
person of that kind can do unless an express disability removes it (a feme sole contracts, sues, holds property;
coverture removes these by `must_not ... or_else null`); a power, the default for actions, exists only when a
`may`/`must` confers it (detain, attach, reassign). Decided 2026-11-04: only a disability (`must_not` with `or_else`
null) removes a default capacity; a sanctioned `must_not` leaves the capacity in place and punishes its exercise, as it
does for a conferred power. Pinned by test. Trace semantics is unchanged (`regulated_actions` and the firing-enablement
block still let an unregulated action fire); default capacity touches only the `(enabled ...)` pseudo-predicate in
derived fluents, and the "never enabled" warning no longer fires for default-capacity actions.
Both `rules_lower.Lowering.enabled` and `rules_reference.power` implement it independently.

Note 2026-11-04 (after docs/reviews/2026-11-05-liberty-flag-rev3-review.md in computational-liberation): (1) the
ABM is affected: `abm/model.py` gates available actions on `Reference.power`, so a default-capacity action with no
`may`/`must` is now a lawful candidate for agents; the frozen layer-2 gate record is not guaranteed to reproduce on
entries with a default-capacity action (seven coverture-chain entries), and `abm/model.py`'s docstring line stating "an
action no may/must rule names is never available" is out of date. (2) The reviewer noted the original name was a
Hohfeldian misnomer (contracting is a power; the mechanism is a default capacity of that kind of agent, removed only by
an express disability). Both decided 2026-11-04; see above.

## Amendment 2026-11-06: derived obligation fluents

computational-liberation plans/priority-slice2.md "Revision 3", R3.2 (author decision 2, engine half). A derived
fluent's definition may read a second pseudo-predicate, `(obliged AIM a1 ... an)`, admitted exactly where `(enabled ...)`
is: inside a `derived` definition, never in a property formula or a rule condition (both are load errors with a clear
message; before this amendment `enabled` in a property was an undeclared-fluent warning lowered as false). `AIM` is a
declared action (an action obligation, must-do) or a declared non-derived fluent (a state obligation, must-be, ADR 0009);
its arity must match, and a derived fluent as `AIM` is an error, as it is as a rule's aim. `(obliged AIM args)` is true at
step t iff `(AIM args)` is an instance (an action instance, typed and attribute-scoped; a fluent tuple inside
`arg_roles`) and some rule instance with deontic `must` on that aim and those args has its condition true at t, free
condition variables existential as for enablement; otherwise false, including for a non-instance.

- Sanctioned and unsanctioned musts count alike: `or_else` plays no part (a duty binds whether or not a sanction backs
  it; whether one does is visible through derived sanction powers). No `obliged_sanctioned` form.
- `may` and `must_not` never oblige; a disability on the same instance does not cancel the obligation (a must and a
  disability on one instance is a deontic conflict; under strict compliance the traces where both conditions hold are
  pruned).
- Independent of `default_capacity` (which changes only `enabled`) and of the compliance mode (obliged reads the rule
  set and the state, not whether the trace complied). Under strict compliance `obliged F and not F` is unreachable for
  every must-be; under `sanctioned` it is reachable for a sanctioned must-be (a breach) and not for an unsanctioned one.
- Defined at every step 0..k, for state and action aims alike. Deleting a `must` makes its instances unobliged;
  `~prohibit` ablation variants touch only `may` rules and never change it.
- Cycles: a derived fluent depends on the conditions of every `must` rule on each aim it asks `obliged` of, so a cycle
  through a must condition is an error. A warning flags an aim no `must` names (constant false), as for an unregulated
  `enabled`.

Both lowerings implement it independently: `rules_lower.Grounded.obliged` and `rules_reference.Reference.obligation`
(rule instances read directly, must only). The dataset exposes it per entry through one derived fluent, `care_obliged`,
not through a property-level pseudo-predicate (reasons: plans/priority-slice2.md R3.2). Tests:
tests/test_rules_obliged.py (O1, O2, O4 a-c, O6), tests/test_rules_meta.py (O3 differential, O4 d-e).
