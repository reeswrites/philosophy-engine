# Skeptical review of the institutions Phase 0 result (2026-11-03)

Independent, read-only review by an agent that had not seen the build. Verdict: **not yet.** Two of three headline claims hold (one-rule minimal pairs are told apart; cosmetic rename is detected); the care+control "rediscovery" is built in. Findings, with severity:

1. **`care_and_sanction_same_role` is true by effects, not rules — BLOCKS.** `can_sanction` is set as a direct effect of marry / dispatch_officer / investigate / acquire (initial in companion-*) and never cleared except by companion transfer. Police-crisis with R3 (may detain) and R5 (may use_force) deleted still gives holds_to_k. crisis-team is "violated" only because `can_sanction` was omitted from dispatch_team's effects. Same pattern for `reproduction_controlled_by_owner` (controls_reproduction bundled with owns in every effect).
2. **Companion ownership/guardianship verdict difference is an initial-state literal — BLOCKS the verdict half.** guardianship declares `(can_claim_for court animal)` in `initial`. With R9 removed it still gives no_standing=violated; ownership with that literal added gives no_standing_persists=fails. Iso distance 1 is syntactic and real; the verdict is not derived from R9.
3. **Four must-be rules are unbreakable — WEAKENS.** police-crisis R2, crisis-team R2, cps R4 (in_home_considered), cps R8 (has_standing): set by the condition-creating action, never cleared. Inert; cps R4 is the "care" leg of the cps match.
4. **Care+control cluster is an artifact of hand strand tags + guard erasure — BLOCKS (b).** The sub-signature needs only a matched superadditive rule and a matched rival `may` on the same attribute. A 5-rule lease (landlord must habitable when leased; may evict when breach) matches police-crisis and coverture at guard+strands. Retagging crisis-team R3 from superadditive to rival makes it match police. rules_gate.py slides exact→guard and never reads the dataset's precommitted level, contradicting ADR 0010.
5. **Expectation drift — WEAKENS.** (a) Gate (c) originally keyed on `solo_care_by_non_birthing_parent` forced vs reachable; both now `reachable`; a new property was added so the pair differs and crit_c was rewritten to accept any difference. (b) `_persists` properties for companions are principled, but guardianship keeps the original form (cherry-picked per entry). (c) police-crisis `no_standing: unreachable_open` is trivially unreachable (nothing clears has_standing; can_claim_for undeclared → constant false).
6. **Vacuity — WEAKENS.** Antecedents are reachable (78/79), but consequents are fixed by construction (1, 3). cps `no_standing: violated` violates at t=0 before any subject exists.
7. Cosmetic: `may` rules are inert under strict compliance; cps default `cooperates` instantiates ill-typed tuples (untyped-variable warnings).

## Required fixes (tracked)
- Derive power fluents (`can_sanction`, `has_standing`, `can_claim_for`, `controls_reproduction`) from rule enabledness, not from effects or initial state.
- A breaker action for every must-be, or the rule is reported inert.
- Negative controls in the gate: a lease (and one more unrelated institution) must NOT match care+control at the precommitted level.
- Gate reads `isomorphic_to.level` from the dataset; a match at any other level is a finding, not a pass.
- Restore gate (c) to its preregistered property or record the change as a drift with reasoning; make `_persists` use uniform across companion entries.
- A vacuity flag on holds_to_k/persists (antecedent reachable? subject exists?).
