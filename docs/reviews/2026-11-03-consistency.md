# Consistency review (2026-11-03)

Read-only review of the documents: `docs/intent.md`, `docs/theory.md`, `docs/glossary.md`, `docs/decisions/*`,
`docs/reviews/2026-11-03-phase0-skeptical-review.md`, `plans/*`, `data/institutions/README.md`, `CONTRIBUTING.md`,
`README.md`. The dataset JSON was being re-encoded while this was written (ADR 0013); findings judge the documents, and the
JSON only where its field names bear on a document's claim. Severity: **contradiction** (two documents cannot both be
right), **drift** (a later result or decision changed the meaning and an earlier text was not updated), **ambiguity**
(one term, two readings), **stale** (a status or number that is no longer true).

## Findings

1. **Care+control "rediscovery" claimed and undercut in the same table.** `docs/theory.md`, rules-engine table: "Isomorphism
   as headline | Same: care bundled with control across police, CPS and the coverture-era household", and the Phase 0
   test "(1) clusters police, CPS and the coverture household". The roadmap row then says "care+control rediscovery is
   built in (power fluents asserted in effects ...; a 5-rule lease matches at the same level)". The skeptical review:
   "Care+control cluster is an artifact of hand strand tags + guard erasure — BLOCKS (b)". The headline is still stated
   as a result two sections above the retraction. **contradiction**

2. **ADR 0010 says the strand-tag question is answered; the review says the opposite.** ADR 0010, Consequences: "The open
   question is answered: strand tags alone do not make care + control isomorphic; condition abstraction does."
   Review finding 4: "Retagging crisis-team R3 from superadditive to rival makes it match police", and the match "needs
   only a matched superadditive rule and a matched rival `may` on the same attribute". `plans/institutions-phase0.md`
   still lists the same question as open ("Strand tags may make care + control trivially isomorphic by construction").
   Three states of one question. **contradiction**

3. **Roadmap status says the gate passes; the plan says a gate that skips (d) is not a pass.** `docs/theory.md` roadmap:
   "36/36 verdicts match, gate passes (kibbutz test deferred)". `plans/institutions-phase0.md`: "(b) to (d) are the
   substantive tests. If the engine passes (e) but fails them, the approach is not working." `rules_gate.py` reports (d)
   as `deferred`, and (b) fails per the review. `CONTRIBUTING.md` calls the gate "informational for now"; ADR 0007 and the
   glossary make it a precondition "before results are used". **stale / contradiction**

4. **36/36 is quoted as current after a decision that invalidates it.** ADR 0009 Consequences: "check-all 36/36 under
   `one`"; `data/institutions/README.md`: "29/36 -> 36/36"; roadmap: "36/36 verdicts match". ADR 0013 Consequences: "The
   dataset must be re-encoded; verdicts may change, which is the point." No document says which verdicts survive. **stale**

5. **Gate (c) is stated four ways.** Plan: "`paternity-quota` / `transferable-leave` get different verdicts on
   `solo_care_by_non_birthing_parent` (forced vs merely reachable)". Dataset README: "`leave_reserved_for_non_birthing_parent`,
   added so the ... pair gets different verdicts (gate c); `solo_care_by_non_birthing_parent` is reachable in both".
   ADR 0013 / `rules_gate.py`: "gate (c) at the preregistered `differs_on` property", and the dataset's `minimal_pair_of`
   entries carry no `differs_on` (the gate then prints "must be preregistered"). Theory: "(2) separates Quebec-style
   non-transferable paternity leave from transferable leave, which differ by one rule" (iso distance only). The review
   calls the change "expectation drift"; no document records it as a preregistration change with reasoning. **drift**

6. **"Expectations before runs" vs. documented post-hoc expectation edits.** `docs/intent.md`: "expectations written
   down before runs"; `CONTRIBUTING.md` 5: "Do not edit expected verdicts to match results. If the engine disagrees,
   record the disagreement". `data/institutions/README.md`, Revisions: `_persists` properties "Added ... with expected
   verdict `persists`" after "the first check-all, 21/36", and `leave_reserved_for_non_birthing_parent` added "so the
   pair gets different verdicts". The README describes exactly what CONTRIBUTING forbids, without calling it a
   disagreement. **contradiction**

7. **Floor-first: hypothesis, sequence step 2, or definition?** `docs/intent.md`: "floor-first may be one path among
   several (property acts and no-fault divorce gave standing before any floor)" and "Backtests must be chosen to test
   the ordering, not assume it." `docs/theory.md`, Sequence: "1. Preconditions ... 2. The floor ... 3. Collective
   power ..." stated as the order; roadmap layer 5 pass test: "Finds that floor-before-standing beats
   standing-before-floor in backtests" (a pass test that presupposes the result). `docs/glossary.md`, material floor:
   "built first because losing care is the real danger of unbundling". `plans/backtest-data-inventory.md` ranks the
   Married Women's Property Acts second precisely because "standing before any labour floor". **contradiction**

8. **`or_else: null` means two different things.** Plan, rule format: "`or_else`: sanction rule id, or null (then it
   is a norm/strategy, not a rule)". Dataset README: "`or_else: null` on a `must_not` means a disability (no power
   exists), not an unenforced prohibition"; ADR 0013 builds `enabled` on that reading ("no `must_not` disability
   (`or_else: null`)"). Under the plan's reading a null-or-else `must_not` is a mere norm and should not disable
   anything. **ambiguity**

9. **"Isomorphic" covers equivalence and partial form-match.** Glossary: "equivalence of canonical rule skeletons under
   a role and predicate bijection"; ADR 0005: "canonical rule skeleton plus Z3 equivalence", reported "with the matched
   sub-signature and the unmatched rules". ADR 0010 and the dataset's `isomorphic_to` entries record a two-pair
   `sub_signature` at `guard+strands`, and `rules_gate.py` accepts "full iso, or the care + control form ... whose pairs
   include the claim's sub_signature". A two-rule overlap at guard level is being called isomorphism; the review's
   lease counterexample is what that reading lets in. The glossary has no entry for abstraction level, sub-signature or
   negative control. **ambiguity**

10. **ADR 0006's bundle tag does not exist.** ADR 0006: "Every bundle is tagged `contingent | constitutive`." Neither
    `schemas_rules.py` nor any dataset entry has a bundle-type field (entry keys: `roles, fluents, actions, rules,
    expected_properties, isomorphic_to, ...`). The plan also requires it ("every bundle as `contingent | constitutive`").
    Theory's farming table tags strands "Constitutive, but substitutable", a value the schema does not admit. **contradiction**

11. **ADR 0005 and gate (f) forbid a bare cross-line iso claim; the dataset makes one.** ADR 0005: "A bare 'iso: true'
    across the human/non-human line fails the gate." Plan, extension 3: "guardianship should share structure with `cps`"
    with no sub-signature; `companion-guardianship.isomorphic_to` is the bare id `["cps"]` while the human cluster uses
    `{id, level, sub_signature}`. `rules_gate.py` silently defaults a bare claim to `guard+strands`. **contradiction**

12. **ADR 0011's status contradicts its body and its index entry.** Index: "0011 ... proposed". Body, Status: "Accepted
    2026-11-03: public repo, permissive license ... Apache-2.0". Body, Decision and Consequences: "GPL-3.0 is what IG-Parser
    uses; the choice stays open here" and "The license decision is deferred and needs its own ADR". `README.md`,
    `CONTRIBUTING.md` and `LICENSE` are Apache-2.0. The ADR README format allows only `proposed | accepted | superseded`.
    **stale**

13. **ADR 0012 is "proposed", yet CONTRIBUTING enforces it and batch 2 grows the dataset without it.** ADR 0012: "Before
    the dataset grows past Phase 0, add a coding step in which people who live under an institution review its
    encoding"; "The schema needs a request for `contested` alternatives". `CONTRIBUTING.md` presents the review step as
    policy ("(The ADR is still 'proposed'.)"). `plans/institutions-batch2.md` drafts five more institutions with
    "Rival reading (contested, notes only)" and no `contested` list; `schemas_rules.py` has no `contested` field.
    **drift**

14. **Plan still describes the pre-0009 lowering and the pre-0013 fluents.** `plans/institutions-phase0.md`, Rule format:
    `"aim": "control_property(h, w)", // the action`; Lowering: "`must A when C`: in every compliant trace, `C(t) => A(t)`"
    (action only). ADR 0009 makes aims fluents. The plan's step-mode paragraph still ends with the superseded request
    ("Either make standing obligations conditional ... or add a third mode"), and the "Request kept open: `can_claim_for`
    should be derived ...; companion-guardianship declares it as initial state meanwhile" is now forbidden by ADR 0013
    ("A derived fluent ... cannot appear in ... `initial`"). The plan's own header says "Status: plan only ... Nothing in
    `philengine/` changes", under four dated code-change appendices. **stale**

15. **Dataset README's revision history conflicts with ADR 0013.** README conventions: fluents "`can_sanction`,
    `can_exit`, `has_standing`, `can_claim_for`" are shared effect-set fluents; Revisions: "Companion `transfer` and
    `reassign` now move `owns`, `controls_reproduction` and `can_sanction`"; "companion-guardianship declares
    `can_claim_for(court, animal)` initially". ADR 0013 names those four fluents as the ones that must be derived and
    never appear in effects or `initial`. The README has no ADR 0013 section and no `derived` convention; the JSON
    sampled today still has `derived: []` everywhere. **stale** (in flux; the README must change with the re-encode)

16. **Gate (a) has three definitions.** Plan: "(a) all six stages ran over all institutions with 0 failed jobs"
    (reconstruct, formalize, check, judge, select, iso); ADR 0001: the family reuses "the judge, select and iso stages";
    ADR 0004 relies on "judge-stage traces ... checked against the source". `rules_gate.py` (a): "institutions load and
    parse; N inert must-be rule(s), none load-bearing". `cli_rules.py` has `check`, `check-all`, `iso`, `gate` and no
    reconstruct/formalize/judge/select. The judge that ADR 0009 says "must catch" a forgotten establishing action does
    not exist for institutions. **drift**

17. **ADR 0007's gate list includes a case no gate criterion covers.** ADR 0007: "the kibbutz children's house and Happy
    the elephant as failures explained by implicit rules". Plan gate (d) names only the kibbutz; `habeas-personhood` is
    "Second instance of gate (d)" in the unreviewed extension, is not in the dataset, and `rules_gate.py` (d) is
    `deferred`. `docs/intent.md` kill switch names "the kibbutz regendering via its implicit rule, police vs crisis team,
    cosmetic reform", a third list. **ambiguity**

18. **Which backtest cases, and how many.** Roadmap layer 3: "Encode 6–8 cases ... (footbinding, Quebec quota, Dutch
    buyouts, whaling, cage-free pledges, kibbutz)". `plans/layer2-abm.md`: "backtest four historical cases". `plans/
    backtest-data-inventory.md` ranks whaling, Married Women's Property Acts, US unilateral divorce, Dutch buyouts;
    cage-free is "runner-up", footbinding and kibbutz are "Difficulty: High" with non-public data. **drift**

19. **Freedom is scored without non-domination.** `docs/intent.md`: "Freedom (exit, voice, recognition, non-domination)
    plus flourishing". `plans/layer2-abm.md`, Scoring: "Freedom: ... (exit) ... (voice) ... (recognition)"; no
    non-domination term, though the glossary and theory define it separately from standing ("no one can interfere with
    you at will, even if they never do"). **drift**

20. **Simulating gendered roles vs. the participation guardrail.** ADR 0008/0011 and CONTRIBUTING: "no simulated
    populations standing in for real marginalized groups without their participation"; layer 2: "roles are
    institutional sorts, not demographics". But layer 2 gate (c) runs `kibbutz-childrens-house`, whose batch-2 encoding
    has roles `metapelet (female member)`, `male_member` and fluent `female(x)`, and the footbinding case is about
    girls. Whether a sex-tagged role is a "demographic" is undecided. **ambiguity**

21. **Private-instance encoding vs. "no named private individuals".** `docs/intent.md`: the author's arrangements "may
    be encoded as test institutions in a private `me/` family"; ADR 0012: "The cheapest faithfulness test is encoding
    the author's own arrangements". ADR 0011: "This project does not encode named private individuals." Whether the
    limit binds the private instance, or only the public repo, is not stated. **ambiguity**

22. **ADR 0002's one-to-one mapping to IG Script tags is not what the schema does.** ADR 0002: "We borrow IG Script's
    component tags (A, D, I, Bdir, Bind, Cac, Cex, O) ... so our JSON maps one-to-one." The rule object has
    `attribute, deontic, aim, conditions, or_else`: no object (Bdir/Bind) component and one undivided `conditions`
    (Cac/Cex). ADR 0009's `aim_kind` has no IG Script counterpart. **drift**

23. **Glossary says it follows the plan; neither covers the current semantics.** Glossary header: "Wording follows
    `plans/institutions-phase0.md`." Missing from both: must-be / state obligation (ADR 0009), derived fluent and
    `enabled` (ADR 0013), `inert`, vacuity flag, `load_bearing`, abstraction level `exact | guard` (ADR 0010),
    `differs_on`, negative control, `pure_rename`. The glossary's `tying` entry ("the strand liberation removes first")
    is a sequencing claim inside a document that says "Structural terms describe encodings, not moral standing". **drift**

24. **Dataset README's `true` note is stale.** README: "`philengine/sexpr.py` currently lists `true` as FORBIDDEN; the
    schema request ... should admit it or the loader should rewrite it". Plan appendix: "the rules path accepts a bare
    `true` condition (`rules_lower.parse_condition`) without touching sexpr". **stale**

25. **Dataset size and membership.** Plan table: 11 institutions ("about ten"). Dataset README and roadmap: 9, three of
    them the companion trio from the extension; `family-wage`, `kibbutz-childrens-house`, `fair-play-domains`,
    `gig-platform`, `ostrom-fishery` are in the plan's table and only drafted in batch 2. The plan's table is presented
    as the dataset, not as a target. **stale**

26. **Arguments family: "Phase 0 done" vs. the README's own last gate result.** README top: "Arguments (`data/phase0`):
    Phase 0 done." README, "Re-run after fixes": "Gate: **FAIL** on criterion (b) only ... needs restating", followed by
    "Fix round 2: Gate (b) redefined" with no later gate result quoted. **stale**

27. **"Public repo from the start" vs. the working tree.** `docs/intent.md`: "public repo from the start, reproducible
    runs"; "a methods write-up as the first public document". `git status`: `docs/`, `data/institutions/`,
    `CONTRIBUTING.md`, `LICENSE`, `CITATION.cff`, `.github/` are all untracked; the last commit predates the institutions
    family. No methods write-up exists under `docs/`. **drift**

28. **Theory snapshot warns it will be overwritten.** `docs/theory.md` header: "the Claude doc is the editing surface and
    this file is a snapshot; edits here will be overwritten on the next export." The roadmap row that records the
    skeptical review lives only in this snapshot; if the source doc was not updated the retraction is lost on export.
    `docs/intent.md` says "Every later decision is checked against this file", but no ADR cites it except 0011. **ambiguity**

## Counts

28 findings: contradiction 7 (1, 2, 3, 6, 7, 10, 11) · drift 8 (5, 13, 16, 18, 19, 22, 23, 27) · ambiguity 6 (8, 9, 17, 20, 21, 28) · stale 7 (4, 12, 14, 15, 24, 25, 26).

## Five fixes that remove the most inconsistency

1. **One status paragraph, in one place.** Replace the roadmap row's prose and the "36/36 / gate passes" phrases in
   ADR 0009, the dataset README and theory with a pointer to `docs/claims.md`, which carries status per claim. Mark the
   care+control headline in theory's rules-engine table and Phase 0 test as `weakened` until the re-encode passes
   (fixes 1, 3, 4, 26).

2. **Define the gate once.** Put criteria (a)–(f) in `plans/institutions-phase0.md` only, in their current form (load +
   inert check, precommitted level, negative controls, `differs_on`, deferred (d), cosmetic (f)); have CONTRIBUTING,
   the dataset README, ADR 0007 and theory cite it. Record the gate (c) change as a dated preregistration amendment with
   reasoning, and add `differs_on` to every `minimal_pair_of` (fixes 5, 6, 16, 17).

3. **Rewrite the plan's semantics sections and the glossary to post-0013 terms.** Rule format and Lowering gain must-be
   aims, `derived` fluents and `enabled`, `or_else: null` as disability; delete the superseded step-mode and
   `can_claim_for` requests; the glossary gains level, sub-signature, negative control, inert, vacuous, load-bearing,
   must-be, derived; split "isomorphic" into full iso and form match (fixes 8, 9, 14, 15, 23, 24).

4. **Either add the bundle tag and `contested` list to the schema or supersede the sentences that promise them**
   (ADR 0006, ADR 0012), and fix ADR 0011's status/index and license text (fixes 10, 12, 13).

5. **Make the ordering claims hypotheses everywhere.** Rewrite theory's Sequence and the layer 5 pass test as "which
   order wins in backtests" (not "finds that floor-before-standing beats"), drop "built first" from the glossary's floor
   entry, add non-domination to layer 2's freedom vector, and fix one backtest case list (fixes 7, 18, 19).
