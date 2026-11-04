# 0009. State obligations: an aim can be a fluent (must-be), not only an action (must-do)

## Context
Standing duties (`husband must maintain(wife) when married`, `owner must feed(animal) when owns`, `parent must cooperate when case open`) were encoded as action obligations, so under one action per step (interleaving semantics, kept as the default because `many` lets `feed` and `transfer` share a step) they fired at every step the condition held: two duties on one state were unsatisfiable (coverture could never marry) and one duty starved every discretionary action (cps could never remove, companion owners could never transfer). check-all sat at 29/36.

## Decision
An ADICO aim is either an action (must-do, may, must_not do) or a fluent (must-be, must-not-be). `Rule.aim_kind` is inferred from the aim's head: a declared action is `action`, a declared fluent is `state`; neither or both is an error, as is `may` on a fluent. `must F when C` lowers to `C(t) => F(t)` at every step 0..k of a compliant trace: no action fires and nothing counts toward the per-step limit; a breach `C and not F` sets `violated_<rule>` and enables `or_else` exactly as an action breach does. `must_not F when C` is the symmetric state prohibition. Because the state must hold at the first step the condition holds, the action that creates the condition establishes the state (marry sets provides_care both ways, acquire and dispatch set provides_care, investigate sets in_home_considered and has_standing) or the state is initial; discretionary actions then restore it and an unregulated action (neglect, refuse) breaks it, which is what gives the rule content. Genuine one-off obligations (dispatch, investigate, contact the mother) stay action rules and consume their trigger or are guarded by their own effect.

## Alternatives rejected
Guarding action obligations with `not F` keeps them one-off but still spends a step per duty, so simultaneous duties stay unsatisfiable. A third step mode counting only discretionary actions hides the semantics in the solver rather than the rule. A one-step grace (`C(t) => F(t+1)`) has the same collision for two duties triggered together.

## Consequences
check-all 36/36 under `one`; `many` is unchanged in code. Rule ids are stable and each converted rule says so in its source string. The establishing-action discipline is a dataset convention the ADR makes explicit; an encoder that forgets it makes the condition unreachable, which the judge must catch. `may` stays action-only, so permission to be in a state has no encoding. Deontic conflicts between must-be and must-not-be on one fluent are reported by the existing conflict check.

## Status
accepted
