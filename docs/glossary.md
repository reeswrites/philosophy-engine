# Glossary

Wording follows `plans/institutions-phase0.md`. Structural terms describe encodings, not moral standing.

- **bundle**: the set of rules that together make up one institution or one arrangement of rights and duties.
- **strand**: one rule or thread in a bundle, tagged by what holds it there (`rival | superadditive | tying`).
- **rival input**: a strand only one party or one body can supply at a time (one bed, one pregnancy); it resists unbundling as a scheduling fact, not a value.
- **superadditive**: a strand whose good exists only as a product of the bundle (being known by one person who is also housemate and co-parent); unbundling is possible but costs legibility.
- **tying**: a strand glued to the bundle by law, wages or norm with no production link to the rest; it exists to protect a monopoly and is the strand liberation removes first.
- **contingent bundle**: held together by economics or law, not by the goods themselves; unbundling frees the parts.
- **constitutive bundle**: the good exists only because the parts come together; unbundling deletes the good instead of freeing it, so the honest move is choosing bundles, not escaping them.
- **material floor**: care, health, housing and income provided regardless of any relationship, so that no one's survival depends on being chosen; built first because losing care is the real danger of unbundling.
- **equal standing (exit, voice, recognition)**: a subject can leave (exit), contest rules (voice), and be counted as a party to claims (recognition).
- **real freedom**: the practical ability to act on a permitted option, not only its formal permission.
- **non-domination**: no party holds a rule-backed power to interfere arbitrarily with another's choices.
- **dark twin**: unbundling done by capital rather than by the subject: the labor is kept and the protections stripped (the gig economy for jobs; agribusiness owning the meat substitutes).
- **displacement**: control or burden moved to another party or place rather than removed.
- **backlash**: a rule added to reinforce the existing bundle against a change or substitute.
- **rebundling**: the same strands recombined under new names or roles, so the structure returns.
- **cosmetic reform**: a change (such as a role rename) that leaves the structure isomorphic to the original.
- **implicit rule**: a norm nobody writes down (`implicit: true`), encoded because it is often the one worth contesting.
- **ADICO**: Ostrom's Institutional Grammar statement form: Attribute, Deontic, aIm, Conditions, Or else.
- **fluent**: a state predicate that varies over time, written `Holds(fluent, args, t)`.
- **bounded unrolling**: giving fluents and actions a step index 0..k (default k = 6) with frame axioms, inside Z3.
- **reachable**: some compliant trace reaches the property within k steps (a permission, not a prediction).
- **open**: the solver did not find a trace, or timed out; beyond the bound this is never read as safe.
- **holds_to_k**: the property holds at every step of every compliant trace up to k.
- **violated**: a compliant trace breaks the property; a counterexample trace is returned.
- **persists**: once the property holds, it keeps holding up to k (reform durability).
- **isomorphism (structural)**: equivalence of canonical rule skeletons under a role and predicate bijection, reported with matched sub-signature and unmatched rules; never moral equivalence.
- **minimal pair**: two institutions differing by one rule, used to test that near-identical encodings are told apart.
- **gate**: the set of criteria an encoding run must pass, including rediscovery of known findings, before results are used.
- **backtest**: checking the engine's verdicts against historical cases with known outcomes before any forward claim.
