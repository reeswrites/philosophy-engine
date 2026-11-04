# data/institutions

Hand-reconstructed institutions for the Phase 0 institutions family (`plans/institutions-phase0.md`).

- `institutions.json`: list of 25 entries (`coverture-household`, `police-crisis`, `cps`, `crisis-team`,
  `paternity-quota`, `transferable-leave`, `companion-ownership`, `companion-guardianship`,
  `companion-guardian-renamed`, the negative controls `lease`, `public-library` and `naming-convention`, the gate (d) pair
  `kibbutz-childrens-house`, `kibbutz-childrens-house-no-implicit`, the expected-match control `airline-flight`,
  the six-entry MWPA chain `mwpa-creditor-exemption`, `mwpa-property`, `mwpa-earnings`, `mwpa-sole-trader`,
  `mwpa-suit`, `mwpa-property-narrowed`, the layer-2 gate (a) pair `footbinding`, `footbinding-no-pledge`, and the ectogenesis pair `ectogenesis`, `gestational-surrogacy`). Each has `roles`, `fluents`, `actions` (with effects as fluent literals),
  ADICO `rules`, `source_text`, `expected_properties`, `isomorphic_to`, `not_isomorphic_to`, `minimal_pair_of`, `notes`.
- `properties.json`: named properties reused across entries. The plan's nine plus one extra,
  `leave_reserved_for_non_birthing_parent`, added so the paternity-quota / transferable-leave pair gets
  different verdicts (gate c); `solo_care_by_non_birthing_parent` is reachable in both.
- `_gen_*.py`: the scripts that wrote the two JSON files. Edit the script, rerun, do not hand-edit the JSON.

## Conventions

- Fluent names are shared across entries where they mean the same thing (`is_subject`, `provides_care`,
  `can_sanction`, `can_exit`, `has_standing`, `can_claim_for`, `in_custody`, `owns`, `parent`,
  `birthing_parent`, `female`, ...). Iso is matched on them. `is_subject` is the one fluent for the
  dependent / detainee / child / animal; `dependent_cannot_exit` and `subject_cannot_exit` are the same form.
- Property `formal` is a state formula with the step variable `t` free; `reachable` closes it with
  `exists t`, `invariant` / `persists` with `forall t`. Fluent applications carry `t` as last argument
  (`Holds(f, args, t)` in the plan). Sorts used: `agent`, `step`. `offspring_owned` uses `succ(t, t2)`
  for t+1 because the grammar has no arithmetic.
- Rule `conditions` use the plan's grammar. `true` appears as a condition (as in the plan's examples) but
  `philengine/sexpr.py` currently lists `true` as FORBIDDEN; the schema request for `schemas_rules` should
  admit it or the loader should rewrite it to an empty conjunction.
- Rule variables (`h w`, `o s`, `p q c`, `o a o2`) are bound by the rule's attribute role and the action's
  argument list, not by an explicit quantifier; the formalize stage adds the quantifiers.
- `or_else: null` on a `must_not` means a disability (no power exists), not an unenforced prohibition
  (coverture R4/R7, crisis-team R4, companion-ownership R9, and since ADR 0013 every subject-side exit bar:
  coverture R6, police-crisis R4, cps R10, companion R6). Lowering should not invent a sanctioner.
- Minimal pairs: `crisis-team` ~ `police-crisis` (R3), `transferable-leave` ~ `paternity-quota` (R2),
  `companion-guardianship` ~ `companion-ownership` (R9). `companion-guardian-renamed` is ownership under
  the bijection owner -> guardian.
- Sources: each rule's `source` names the text read, with URL where one was opened. `UNVERIFIED` marks
  rules reconstructed from general knowledge. Verified at writing time: Blackstone I.15 (via NYHS WAMS),
  Cal. WIC 5150 and 306, Cal. Penal Code 597s, QPIP A-29.011 ss. 9/10/16/17, canada.ca EI parental benefits
  and Parental Sharing Benefit, Alaska Stat. 25.24.160(a)(5), R.I. Gen. Laws 4-13-41, Denver STAR (KUNC),
  Boulder 2000 wording change (Westword, secondary).

## Revisions (dataset fixes after the first check-all, 21/36)

- **Owner-derived fluents move together** (superseded by ADR 0013: only `owns` and `provides_care` move now; the powers are derived). Companion `transfer` and `reassign` now move `owns`,
  `controls_reproduction` and `can_sanction` from the old owner to the new one (and clear the old owner's
  `provides_care`); `abandon` clears all four. Before, `reproduction_controlled_by_owner` was violated by a
  transfer that left the old owner controlling reproduction.
- **transferable-leave / paternity-quota.** Reserved weeks were never granted. Both entries now share R8
  (`plan may grant_reserved` to a non-birthing parent) and R9 (`birthing_parent may take_reserved_leave` while holding
  reserved weeks). The pair differs by exactly R2 (`minimal_pair_of` = paternity-quota R2). The quota's R2
  condition is now `true` (transfer is prohibited outright, not only while holding weeks), because a grant and a
  transfer can fire in the same step.
- **Existential invariants on companion-* are the wrong shape.** `subject_cannot_exit` and `no_standing` are
  `exists s` formulas: false at t=0 (no animal acquired yet) and false again after `euthanize` clears `is_subject`,
  so `holds_to_k` could never be the verdict. The intended claim is "once a subject exists, the property holds while
  it is a subject". Added `subject_cannot_exit_persists` and `no_standing_persists` (universal, `is_subject ->`
  form, vacuous before any subject) with expected verdict `persists`; the originals are unchanged and still used
  by the human-institution entries. companion-guardianship keeps `no_standing: violated` (original form).
- **New optional fields** (data ready; the engine may not consume them yet): `initial` (fluent literals true at
  t=0: has_standing/can_exit of the subject for police-crisis and crisis-team; the parent facts for the leave pair;
  one acquired animal for companion-*), `defaults` (fluent -> "true"/"false"; companion-*), and `arg_roles` on
  fluents (role name per argument slot; union-typed slots such as `parent` in the leave pair are left untyped). `initial` entries are strings like `(owns owner animal)`.

## Revisions (ADR 0009: state obligations, 29/36 -> 36/36 under step_mode=one)

- A rule's aim may be a fluent (must-be). Converted: coverture R2/R3 (`provides_care`), police-crisis R2 and crisis-team R2
  (`provides_care`), cps R4 (`in_home_considered(w, c)`), R5 (`cooperates`, default true, `refuse` breaks it), R8
  (`has_standing`), companion-* R5 (`provides_care`; new `neglect` action breaks it, new R10 `may feed` restores it).
  The action that creates the condition establishes the state (marry, dispatch, investigate, acquire; see each rule's source).
- One-off obligations fire once: dispatch / investigate consume `call_received` / `report_received`; cps R6 is guarded by
  `contacted(w, p)`.
- `initial_free` lists the exogenous triggers of police-crisis, crisis-team and cps (under `declared` they were pinned false).
- (superseded by ADR 0013, the literal is gone) companion-guardianship declared `can_claim_for(court, animal)` initially (the claim path R9 opens), so `no_standing` is
  violated by the claim path rather than by a euthanize trace. `reassign(court, o, a)` now takes three arguments, as
  cps `reassign_custody(court, p, c)` does.
- `isomorphic_to` entries of the care+control cluster are `{"id", "level": "guard+strands", "sub_signature": [...]}`.

## Revisions (ADR 0013: power is derived, never asserted; review 2026-11-03)

Every change here answers `docs/reviews/2026-11-03-phase0-skeptical-review.md`; the item numbers are the review's.

- **Derived power fluents (items 1, 2, 5c).** `can_sanction`, `can_exit`, `has_standing`, `can_claim_for` and
  `controls_reproduction` are `derived` (with `params`) in every entry that declares them, and appear in no effect,
  `initial` or `defaults` any more. The definitions read the rules: `can_sanction(o, s) := (or (enabled detain o s)
  (enabled use_force o s))` (police), `(enabled remove w c)` (cps), `(enabled chastise h w)` (coverture),
  `(enabled detain x s)` (crisis-team; the responder's R4 disability makes it false, the officer's R8 true),
  `(or (enabled euthanize o a) (exists x (enabled transfer o a x)))` (companion); `controls_reproduction(o, a) :=
  (enabled breed_or_sterilize o a)`; `can_exit(x) := (enabled leave|vacate x)`; `has_standing(x) := (enabled sue x)`
  (plus `petition_review` for police, `petition` under appointed counsel for cps); `can_claim_for(x, s) :=
  (exists p (enabled reassign[_custody] x p s))`. companion-guardianship's `initial (can_claim_for court animal)` is
  gone: its verdict now comes from R9 alone (run: deleting R9 turns `no_standing_persists` from fails to persists).
  Deleting police R3 and R5 removes `can_sanction` (run, 2026-11-03, after the `enabled` fix below): the old
  care-implies-power shape of `care_and_sanction_same_role` reads violated, the current shape reads holds_to_k
  *vacuous* (antecedent unreachable: nobody holds sanction power), which check-all flags. Before the fix both
  deletions left the verdicts unchanged, because an action no rule named counted as always enabled (second review,
  items 1-2).
- **Exit is a may + a disability.** Each subject gets an implicit `may leave when true` (coverture R8, police R9,
  cps R9, companion R12; crisis-team R5 and public-library R4 already had it) and the bar is a `must_not leave`
  with `or_else: null`. The old `or_else` links (coverture R6 -> R5, police R4 -> R5, companion R6 -> R7) duplicated
  the sanction rule's own trigger (`resists`, `at_large`) and are dropped; companion R6 is conditioned on
  `is_subject`, not `owns`, because reassign / abandon clear `owns` in the one-owner domain and would otherwise read
  as giving the animal an exit. `enabled` ignores sanctioned prohibitions (see the schema request on `permitted`).
- **cps R8** was `court must (has_standing c)`; a must-be cannot bind a derived fluent, so it is now `court must
  (counsel_appointed c) when case_open` and R11 `child may petition when counsel_appointed` is what `has_standing(c)`
  reads. **cps R10** (`child must_not leave when in_custody`, disability) is the exit_bar leg of the cps match: it is
  inferred from WIC 306(a)(2) 'take into and maintain temporary custody'; the section does not address the child's
  conduct, so the inference is stated in the source string. `var_roles` type `w`, `c`, `p` on every cps rule and
  `q` / `p` on leave-pair R2, R6, R8 (R3 `forfeit plan p` stays untyped: either parent may hold the weeks in
  transferable-leave).
- **Breakers (item 3).** Every `load_bearing: true` must-be has an action that makes `C and not F` true: coverture
  R2/R3 (neglect, neglect_house), police R2 and crisis-team R2 (new `withdraw`), cps R4 (new `disregard_in_home`),
  cps R8 (new `relieve_counsel`), companion R5 (neglect). `leave` in both crisis entries also ends `provides_care`
  (the encounter is over). check-all reports 0 inert rules.
- **Negative controls (item 4).** `lease` (Cal. Civ. Code 1941 habitability duty, CCP 1161 eviction on rent
  default, Civ. Code 1946 termination by notice) and `public-library` (Berkeley Patron Suspension Policy: service
  to all, suspension for conduct, patron free to leave) have the care duty and the rival power on the same
  counterparty but no subject-side `must_not`. `not_isomorphic_to_control: ["lease", "public-library"]` on the
  three cluster members; the gate reports `none@guard+strands` for all six pairs. The cluster's `isomorphic_to`
  claims carry three precommitted pairs (care, control, exit_bar). The coverture~police control pair was
  re-preregistered from `R5~R5 chastise~use_force` to `R5~R3 chastise~detain`: the old pair was forced by the
  `or_else` link R6 -> R5, which is gone; restraint of liberty ~ custody is the better reading and matches the
  cps pairing (chastise~remove, detain~remove). Recorded as a change, not a finding.
- **Gate (c) drift, recorded (item 5a).** The plan preregistered `solo_care_by_non_birthing_parent` as the
  property the paternity-quota / transferable-leave pair would differ on (forced vs reachable). In the encoding it
  is `reachable` in both: a quota does not force the father to care, it only reserves weeks nobody else may use,
  and a transferable scheme does not stop him. That is a finding about the preregistration, not about the pair.
  `leave_reserved_for_non_birthing_parent` was added afterwards and is what the pair differs on (holds_to_k vs
  violated); `minimal_pair_of.differs_on` names it so the gate tests exactly that property and lists any other
  difference (care_assigned_by_sex) as a finding. The replacement was made after seeing both verdicts, so it is
  post hoc and is marked as such here.
- **`_persists` uniform (items 5b, 6).** companion-guardianship expects `no_standing_persists: fails` (was
  `no_standing: violated` on the existential form); cps likewise `no_standing_persists: fails` instead of
  `no_standing: violated`, which was violated at t=0 before any child existed. Both are the same claim in the form
  that is vacuous before a subject exists; check-all shows no vacuous flags.
- **Expectations that disagreed with results (superseded 2026-11-03, see the next section):** police-crisis and cps
  `care_and_sanction_same_role` expected `holds_to_k`, got `violated`. Derived, the sanction power exists only while
  its trigger (`danger`, `immediate_danger`, both exogenous) holds, while the care state persists; the state
  invariant asked for simultaneity, which the old effect-asserted encoding faked. companion-guardianship's bare
  `isomorphic_to: ["cps"]` is at level exact and reads NO (as before: the notes say the iso is partial, on R9 alone).
- Remaining warnings: `can_claim_for` undeclared in coverture / police / crisis-team (constant false: no advocate
  action exists there); `(enabled reassign|sue ...)` in companion-ownership / -renamed names actions only a
  disability regulates (never enabled, which is the intended reading); untyped `p` in leave R3
  and `o2` in companion R1.

## Revisions (second review 2026-11-03, `docs/reviews/2026-11-03-phase0-second-review.md`, items 1, 2, 6, 7)

- **`enabled` of an unregulated action is false (items 1, 2; ADR 0013 amendment).** `(enabled a ...)` for an
  action no may/must rule names was constant true, so deleting the rules that grant a power left the derived
  power standing. It is now constant false (a power is what the rules grant); the action can still fire freely in
  traces, which is a separate question (the trace floor) and unchanged. Run: police minus R3+R5 -> `can_sanction`
  unreachable; companion-guardianship minus R9 -> `no_standing_persists` persists (was fails); companion-ownership's
  `(enabled reassign|sue)` reads false as before. Tests: `tests/test_rules_checks.py` (dataset falsifiers),
  `tests/test_rules_lower.py`, `tests/test_rules_meta.py` (reference, independently).
- **`care_and_sanction_same_role` is a post-hoc property-shape change (item 6).** The shape was
  `provides_care(x,y) & is_subject(y) => can_sanction(x,y)`: live sanction power at every step of care. The
  motivating trace (police-crisis, k=6, init declared): step 0 `dispatch_officer` establishes `provides_care(officer,
  subject)` with `danger` false, so `can_sanction(officer, subject)` (= detain or use_force enabled) is false while
  care holds -> violated; cps likewise with `immediate_danger`. The gloss says "bundled in one role", which the
  reviewer's `sanction_only_by_carer` shape states: `is_subject(y) & can_sanction(z,y) & provides_care(x,y) => z = x`
  (no one but the carer holds sanction power). Name, gloss and all expectations are unchanged; the formula was
  replaced **after seeing the verdicts** and is recorded as post hoc here and in the property's `history`. Verdicts
  now: holds_to_k (non-vacuous) on coverture, police, cps, companion-*; violated on crisis-team (R8: the officer
  the team calls holds detain while the responder cares); removing crisis-team R8 makes it hold. Cost of the shape:
  deleting every sanction rule makes it vacuously true rather than violated (the vacuity flag carries that case).
- **Gate (c) wording (item 7).** `minimal_pair_of` on transferable-leave carries `postregistered: true` and
  `supersedes: "solo_care_by_non_birthing_parent"`; the gate prints "post hoc leave_reserved_for_non_birthing_parent"
  (never "preregistered") and lists the original property's verdicts (reachable vs reachable) as a finding.
  `properties.json` entries carry a `history` field (free text; the engine ignores it).

## Batch 2 (2026-11-03): `kibbutz-childrens-house` and its no-implicit pair (gate d)

- Encoded from `plans/institutions-batch2.md` entry 1. Rules: R1 committee `may assign` any `member` (explicit,
  sex-blind); **R2 committee `must_not assign male_member`, `implicit: true`, disability, load_bearing** (the nanny
  "was always a woman's role"); R3 metapelet `must (provides_care metapelet child) when assigned` (must-be,
  load_bearing, breaker `neglect`, or_else R6); R4 child `must_not sleep_home` (disability: communal sleeping);
  R5 male_member `may visit`; R6 committee `may reprimand` (implicit, UNVERIFIED); R7 child `may sleep_home`
  (implicit; carries `can_exit`). Derived: `can_assign := (enabled assign c x)`, `can_sanction := (enabled reprimand
  c x)`, `can_exit := (enabled sleep_home s)`. `female` has `arg_roles [metapelet]`.
- Sources opened: Wikipedia (nanny "always a woman's role"; communal sleeping; 2-3 h/day with parents); JTA
  1997-06-16 (Baram, the last children's house, closed June 1997); SCMP 1997 (first closures ~20 years earlier;
  pressure "particularly from young mothers"); Kirkus review of Tiger & Shepher 1975 (book and sample confirmed).
  UNVERIFIED: Tiger & Shepher's assignment finding itself (not read directly); R6 (committee discipline).
- Deviations from the draft, each stated in the entry's notes: R1 generalized to `(assign committee x) when
  (member x)` (an action instance no may/must rule names is disabled, so the ablation "drop R2" only bites if R1
  covers the man); R4 is a disability per the ADR 0013 exit convention (draft had or_else R6); R6's condition is
  `true` (the or_else link, not a `violated_R3` condition, enables it); `neglect`, not `release`, is R3's breaker.
- **Preregistered before the first run** (in the generator's notes): `care_assigned_by_sex` persists in the
  original, fails in `kibbutz-childrens-house-no-implicit` (same rules minus R2; `minimal_pair_of.differs_on:
  care_assigned_by_sex`); `subject_cannot_exit` reachable; `care_and_sanction_same_role` violated. Result: all six
  as preregistered (check-all 44/44). Gate (d) (`rules_gate.crit_d`, wired 2026-11-03) PASSes: persists, implicit
  rule R2 is the one rule separating the pair, the pair reads fails.
- The 1970s-1990s return to family sleeping is R4's removal, kibbutz by kibbutz; it is recorded in R7's source, not
  encoded as a third entry: the gate (d) claim is that R2 survives it, and the no-implicit variant is the test.

## Third review (2026-11-03, `docs/reviews/2026-11-03-phase0-third-review.md`)

- **Kibbutz R2 re-encoded as a sanctioned norm.** `must_not (assign committee male_member)`, `or_else: R6`, `implicit: true`;
  ids unchanged. The source string says it encodes a documented practice, not a written rule (the reviewer: the sources
  support a practice, not a committee disability). Result: check-all 47/47, gate (d) still PASS (persists vs fails, R2 the one
  separating rule), because gate (d) reads strict compliance. Expectations unchanged. `enabled` ignores sanctioned
  prohibitions, so `can_assign` no longer reads R2; compliant traces still carry it.
- **`airline-flight` is a permanent EXPECTED-MATCH control** (`expected_control_match: true`; 6 rules from the review, strands as
  the reviewer tagged them: care superadditive, restrain rival, exit bar rival/disability). Preregistered before the run: it matches
  police-crisis, cps and coverture-household at guard+strands (`partial(care+control)`; none at exact), a structural match
  (in-flight custody). Confirmed. Gate (b) fails on any control match and has no expected-match mode (philosophy-engine is not
  edited here), so airline is deliberately NOT in any `not_isomorphic_to_control`; it is in the dataset only, and `crit_b` does not
  run it. Its expectations are copied from police-crisis minus `no_standing` and hold. Retagging its care rule to tying removes
  every match (reviewer's run, not repeated here): strand tags are load-bearing human inputs.

## MWPA backtest chain (2026-11-03, `plans/backtest-mwpa.md`)

- Six entries off `coverture-household`, a path of pairs (`minimal_pair_of` with `differs_on`): `mwpa-creditor-exemption`
  (1839-50 debtor-relief form, the plan's dark twin: +R10 creditor may attach [implicit, UNVERIFIED], +R11 creditor
  must_not attach the wife's acquired property [disability; Chused 1984], +R12 husband may transfer_to_wife [implicit,
  UNVERIFIED]; R1 kept; distance 3), `mwpa-property` (R1 -> R13 wife may hold_property; distance 1), `mwpa-earnings`
  (+R14 may keep_earnings), `mwpa-sole-trader` (R7 -> R15 may contract), `mwpa-suit` (R4 -> R16 may sue while married),
  and the branch `mwpa-property-narrowed` (backlash: +R17 court may construe_narrowly, +R18 R1 reinstated under
  `narrowed`; R13 carries `(not (narrowed w))`; distance 2). Statute texts were not opened; every MWPA rule's source
  is the plan's secondary literature (GLT, Khan, Chused 1984) and is marked [R] / UNVERIFIED where the plan is.
- Coverture itself: rules unchanged; `controls_property` is now derived from R1 (ADR 0013: marry no longer asserts it),
  and `controls_own_property`, `owns_earnings`, `can_contract` are declared (derived) with the actions `hold_property`
  and `keep_earnings`, which no coverture rule names (the "never enabled" warning is the finding). Coverture's old
  verdicts are unchanged; five expectations were added.
- New properties: `financial_dependence`, `financial_dependence_unpropertied`, `cannot_contract` (invariants),
  `double_burden` (DI), `creditor_shield` (DT), `backlash` (BL) (reachability). All verdicts PREREGISTERED in the
  generator's notes and in the plan before the first run; check-all 106/106, gate PASS, no vacuity flags.
  Relabelled by ADR 0016 (2026-11-03): `creditor_shield` DT -> Capture, the `narrowed` branch BL -> Erosion; property
  names and verdicts unchanged. The Erosion relabel was reverted on 2026-11-04 by the ADR's council-pass amendment (the
  branch adds rules, which is backlash); `double_burden` was relabelled partial reform (no mode) the same day.
- Matcher note: on `mwpa-creditor-exemption ~ mwpa-property` the matcher pairs the exemption's R1 with the property
  act's R12 (same skeleton: husband may X when married) and reports R12 vs R13 unmatched; the distance is 1 either way.
- Not expressed: a ranking of failure modes (the plan's "top-ranked risk" criterion; the engine returns verdicts, not
  ranks); dower trade-offs (RB, [R]); divorce reform (`can_exit` is unchanged by construction); the trace floor
  (`control_property` still fires in traces after R1 is deleted, with no power behind it, ADR 0013 amendment).

## Footbinding (2026-11-04, layer-2 gate (a); `plans/layer2-abm.md`, ADR 0015 A1/A3/A6)

- `footbinding` (Mackie 1996, the marriage-market convention) and its pair `footbinding-no-pledge` (same entry minus the
  pledge actions `leave_unbound_pledge` / `accept_match_pledge` and their rules R4 / R10). Roles `family`, `daughter` (subject), `suitor` (the market
  counterparty). Rules: R1 family may bind; R2 family may leave_unbound (implicit); **R3 family must_not leave_unbound,
  or_else R5, implicit, tying** (the sanctioned norm); R4 may leave_unbound_pledge (A3 stand-in, effect `pledged(family)`); R10
  suitor may accept_match_pledge (the pledge's son half, effect `pledged(suitor)`; added 2026-11-04, encoding review
  finding 2); R5 suitor may reject_match while unbound and neither side pledged (the market sanction, which either
  pledge lifts); R6 suitor may accept_match when bound or either side pledged; R7 family may marry_off when bound or pledged (`marriageable(f, d)` is derived
  from it, ADR 0013); R8/R9 the daughter's exit (may refuse_binding, barred by a disability: `can_exit`). `initial`:
  `is_subject(daughter)`, `bound(daughter)`, so `binding_practised` holds at t=0 (the ABM gate excludes seeds where it
  does not).
- New properties: `binding_practised` (exists a bound subject; the gate's `A_PROP`) and `marriage_requires_binding`
  (marriageable implies bound or pledged; flagged `by_construction` 2026-11-04 after the encoding review, finding 3: it
  restates R7, so its holds_to_k is information, kept as the preregistration for the record).
- **Sources: no page could be opened from the session** (jstor paywalled; semanticscholar, wikipedia, cambridge.org and
  two PDF mirrors unreachable). Mackie's abstract sentences came back verbatim in a search-index snippet and are quoted
  as [F]; the pledge wording (daughters not bound, sons not married to bound women; Heavenly Foot Society 1874, Tian Zu
  Hui 1895) is from Wikipedia snippets [R]; Brown et al. 2012 is its abstract [R]. Every rule says what was read and
  the reconstructed ones carry UNVERIFIED.
- **Preregistered before the first run** (in the generator's notes): identical layer-1 verdicts in both entries:
  `binding_practised` persists, `marriage_requires_binding` holds_to_k, `subject_cannot_exit` / `dependent_cannot_exit`
  reachable; `minimal_pair_of.differs_on` null by design (the pair differs only at layer 2). Result: all 8 as
  preregistered (check-all 114/114, `phil rules gate` PASS, no vacuity flags). Information runs, not expectations:
  under `--compliance sanctioned` `binding_practised` fails in both (leave_unbound fires and pays R5), as the notes said
  it should; `phil abm run --inst footbinding --seeds 5 --steps 60` (material only) keeps `bound` at 1.0 in every seed
  (persistence), with `pledged` flipping to 1.0 role-wide as soon as one family pledges (the A2 coarseness noted above).
- **Encoding review 2026-11-04** (`docs/reviews/2026-11-04-footbinding-naming-encoding-review.md`): the suitor pledge R10
  was preregistered and committed (b6f48aa) before its first run: no layer-1 verdict changes in either entry. Result: no
  drift (check-all 115/115, gate PASS, 15 tests); ABM information run (material+coordination, 5 seeds, 60 steps): `bound`
  1.0 in every seed, `pledged` 0.667 (true on the family and suitor role tuples, the A2 coarseness now on both sides).
  Also from the review: `marriage_requires_binding` flagged by construction (finding 3, kept for the record); one-cohort
  note and a deferred `new_cohort` action (finding 4); R9 implicit, rival tags on R5/R8/R9 marked as by analogy (finding
  6); the naming band reworded (finding 9); source_text notes that plans/layer2-abm.md lists Mackie and Centola as opened
  by the planning session.
- Extra fields the engine ignores: `payoffs` (bind and leave_unbound 1.0, the A1 default made explicit so the gate can
  sweep them) and an ASSUMED `coordinated: [bind, leave_unbound]` list, because `ActionDecl` has no action tag yet; the
  notes tell the coordination-module author which actions are coordinated and that role-level `pledged` plus set-true-wins
  in `Reference.successor` mean one pledge flips every family and collapse needs every family to leave unbound in one step.
## Layer-2 gate (b): `naming-convention` (2026-11-04)

- Centola, Becker, Brackbill & Baronchelli 2018 (Science 360(6393):1116-1119) naming game, encoded as the calibration
  entry `philengine/abm/gate.py` crit_b reads: one role `member`, fluents `uses_old` / `uses_new`, actions `use_old` /
  `use_new`, two `may ... when true` rules (ADR 0015 A6), no must / must_not (the game has no sanction), `payoffs`
  block `{use_old: 1.0, use_new: 1.0}` (A1: the payoff is the matching reward, so the names are symmetric),
  `initial (uses_old member)`. A pure coordination game, not a liberation case and not a historical institution
  (ADR 0004: no forward claim; ADR 0011: the agents stand in for experimental subjects, not a real population).
  `committed_minority` is a model parameter the entry's notes record (Centola's band ~ 25%: largest failing minority ~21%,
  smallest succeeding ~25%, UNVERIFIED, from memory; reworded 2026-11-04 per the encoding review), never a rule. The paper could not be opened from the encoding session (every host refused), so its figures
  and quotations are marked UNVERIFIED in the entry.
- New property `new_convention_adopted`: `(forall m (and (uses_new m t) (not (uses_old m t))))`, new-and-not-old so
  that a committed minority's own use of the new name does not read as adoption on the ABM's shared role-level state
  (where set-true wins over set-false in the successor).
- Added to `CONTROLS` (`not_isomorphic_to_control` on the three care+control members): it must match nothing.
- **Preregistered before the first run** (entry notes): reachable; none@guard+strands against all three cluster
  members; no inert rule; layer-2 material-only rate coin-flip-shaped. Result: all as preregistered (check-all 107/107,
  `phil rules gate` PASS with the three new control pairs none@guard+strands, 15 tests pass; `phil abm run --seeds 5`
  material only, before the reserved keys below: last-step `use_new` share 0.8 / 0.4 / 0.9 / 0.7 / 0.0 over seeds,
  mean 0.56, a coin flip as expected; with `initial_practice: use_old` every member stays on the old name, 5/5 seeds).
- The payoffs block also carries the engine's slice-4 RESERVED keys (`philengine/abm/model.py RESERVED_PAYOFF_KEYS`,
  ASSUMED; added concurrently on 2026-11-04 after the first material-only run showed agents bootstrapping practice
  from a payoff tie by rng and ignoring `initial`): `coordinated: [use_old, use_new]`, `committed_action: use_new`,
  `initial_practice: use_old`. Hand inputs like the numbers (A1); none names a tipping location.
- **Layer-2 drift, recorded not edited.** Engine slice-4 crit_b reads the member role's last-step share of
  `committed_action` (not the property: a property mean cannot express a population share under shared role state).
  At 30 seeds, share by `committed_minority` 0.05..0.50 = [0.05, 0.10, 0.15, 0.20, 0.35, 0.54, 0.70, 0.80, 0.90, 0.97]:
  equal to the committed share through 0.20, above it from 0.25 on (tipping begins at 0.20 -> 0.25, inside Centola's
  band), but graded: max adjacent jump 0.19, not > 0.5, so (b) FAILs under both coordination configurations. The
  entry carries no threshold; what grades the curve (the > 0.5 criterion, thresholds U(0, threshold_max), the 20-agent
  graph) is an engine question. `new_convention_adopted` stays the layer-1 property (reachable, as preregistered).

## Ectogenesis pair (2026-11-04)

- `ectogenesis` (Firestone 1970: gestation in a device, nobody is the birthing parent) and `gestational-surrogacy`
  (control: the rival input moves to another body), encoded from the preregistration `plans/ectogenesis.md` (never edited).
  Roles `intended_parent`, `child` (subject), `provider`, `registry`; `gestator` in surrogacy only. Seven rules each, five
  shared (R1 provider may start_gestation; R4 parent may provide_care; **R5 implicit tying must provide_care when
  `female(p)`, or_else R6**; R6 registry may reprimand; R7 registry may register_parentage with no birth condition). R2/R3
  are the substitution: surrogacy `implant` (may) and `give_birth` (gestator must, or_else R6), ectogenesis
  `transfer_to_device` (may) and `decant` (provider must, or_else R6), both hand-tagged `superadditive`. `initial_free`
  `female` (so a non-female carer is reachable); `is_subject` is set only by a birth action.
- New properties `birth_labor_rival` and `care_decoupled_from_birth`, formulas as in the plan, both flagged
  `by_construction: true` in advance (the same mechanism as `marriage_requires_binding`: a property key plus a `history`
  line; the engine ignores it). The flag was written before any run.
- **ASSUMED author decisions** (from the encoder's brief, recorded in both entries' notes): R2+R3 substitution counts as a
  minimal pair (recorded on `ectogenesis`, `differs_on birth_labor_rival`); R2/R3 tagged `superadditive`; R7 no birth
  condition; R5 on `female(p)`; no leave action, so the plan's `leave_reserved_for_non_birthing_parent` row is dropped;
  neither entry in `CONTROLS`; gestator consent out of scope.
- Deviations from the plan: `gestates` is not declared in `ectogenesis` (plan: surrogacy only), so the property lowers it
  as constant false and the engine warns; `reprimand(registry, x)` has an untyped `x` (as kibbutz R6); source_text and
  statute citations are UNVERIFIED throughout (no page opened).
- **Verdicts, observed vs preregistered** (layer 1, k=6, strict, init declared): 7 of 8 as preregistered.
  ectogenesis: `birth_labor_rival` violated, `care_decoupled_from_birth` reachable, `solo_care_by_non_birthing_parent`
  reachable, `care_assigned_by_sex` violated. gestational-surrogacy: `care_decoupled_from_birth` unreachable_open,
  `solo_care_by_non_birthing_parent` reachable, `care_assigned_by_sex` violated.
- **DRIFT 1 (verdict, recorded not edited):** `gestational-surrogacy` `birth_labor_rival` is **violated**, preregistered
  holds_to_k. The plan's own skeleton causes it: `start_gestation` (R1) sets `in_gestation(c)` before `implant` sets
  `gestates`, so the first step after R1 has a gestation held by no body (trace: start_gestation, implant, give_birth,
  start_gestation). The invariant therefore does not separate the pair: it is violated in both, and the headline
  difference the plan names (`differs_on birth_labor_rival`) does not appear at layer 1 as encoded. Cause is the
  property/skeleton pairing, not the engine. Not tuned; a repaired property (guard on implant having fired) or a combined
  start-and-implant action would be a new preregistration.
- **DRIFT 2 (iso, recorded not edited):** ectogenesis ~ surrogacy was preregistered iso at `guard`; observed NOT iso at
  guard, with strands on or off (distance 2, matched 5 of 7: R2 and R3 unmatched). So it is not the strand tag that
  separates them, as the plan guessed: the aim skeletons differ (surrogacy `implant` and `give_birth` have a gestator
  argument; the role-vs-variable aim pattern differs from `transfer_to_device` / `decant`). Not iso at exact, as
  preregistered. Against `coverture-household` (distance 9, matched 0), `police-crisis` (10, 0), `cps` (11, 0),
  `kibbutz-childrens-house` (guard 5, matched 3; guard+strands 6, matched 2): not iso, as preregistered, for both entries.
  Against `transferable-leave` / `paternity-quota`: preregistered a guess of partial at guard+strands (about 40%); observed
  none, matched 0, distance 9, at every level, for both entries (no `partial` claim is expressible in `isomorphic_to`, so
  this is in the notes and here only).
- Checks: `phil rules check-all` 122/123 (was 115/115; the one miss is DRIFT 1); `phil rules gate` PASS (criteria a to f;
  25 institutions, 0 inert); pytest 15 passed. `phil abm gate` not run (a full run was in progress elsewhere).
- Layer 2 not required by the plan. Failure modes (ADR 0016) as in the plan section 5.

**Revision 2 (2026-11-04; plans/ectogenesis.md "Revision 2", preregistered before the rerun, v1 unedited).**
- Change, `gestational-surrogacy` only: R1 and `start_gestation` removed; `implant(provider, gestator, child)` now sets
  `in_gestation` and `gestates` in one step; R2 keeps id and rival strand, condition `(in_gestation child)` -> `true`;
  R3-R7 unchanged (six rules). `ectogenesis` untouched. `minimal_pair_of` is now rule "R1,R2,R3". Note line added to the entry.
- `phil rules check-all`: 123/123 (was 122/123 in v1; the miss was DRIFT 1). `phil rules gate`: PASS (a to f; 25 institutions).
- v2 verdicts, preregistered / observed (layer 1, k=6, strict, init declared): all 8 as preregistered.

| Property | surrogacy | ectogenesis |
|---|---|---|
| `birth_labor_rival` | holds_to_k / holds_to_k | violated / violated |
| `care_decoupled_from_birth` | unreachable_open / unreachable_open | reachable / reachable |
| `solo_care_by_non_birthing_parent` | reachable / reachable | reachable / reachable |
| `care_assigned_by_sex` | violated / violated | violated / violated |

  `birth_labor_rival` now separates the pair at layer 1 (by construction, as flagged in advance).
- Iso, ectogenesis ~ surrogacy (`phil rules iso --pair ectogenesis gestational-surrogacy [--cond guard] [--with-strands]`):
  guard: not iso, distance 2, matched 5; guard+strands: not iso, distance 3, matched 4; exact: not iso, distance 3,
  matched 4 (R4 to R7; unmatched ectogenesis R1, R2, R3, surrogacy R2, R3). Preregistered: not iso at all three (met).
- **DRIFT 3 (iso, recorded not tuned):** preregistered distance about 3 and matched 4 held at guard+strands and exact but
  not at guard, where the observed distance is 2 and matched 5. Not-iso verdicts unaffected. Other-institution
  comparisons were not rerun beyond the gate (PASS); no change claimed.

## Property kinds (2026-11-04, plans/priority.md slice 1)

Every property in `properties.json` now carries a `kind` key (decision 1 of "Decisions waiting on the author"). The engine ignores it; the ablation reads it to decide what is counted. 24 properties.

- `freedom` (counted in load_freedom): dependent_cannot_exit, subject_cannot_exit, subject_cannot_exit_persists, no_standing, no_standing_persists, financial_dependence, financial_dependence_unpropertied, cannot_contract, worker_uninsured, binding_practised, marriage_requires_binding, care_assigned_by_sex, reproduction_controlled_by_owner, offspring_owned, and the new `female_parent_care_persists` (15 in all).
- `goods` (counted in load_goods): none yet; slice 2 writes them.
- `structure` (diagnostic, listed not counted): care_and_sanction_same_role, solo_care_by_non_birthing_parent, leave_reserved_for_non_birthing_parent, new_convention_adopted, birth_labor_rival, care_decoupled_from_birth.
- `failure_mode` (listed not counted): double_burden, creditor_shield, backlash.

New property `female_parent_care_persists` (kind `freedom`, check `persists`): formula and gloss from plans/ectogenesis.md "Revision 2" section 5, so that ectogenesis R5 has a freedom property to carry. It is not in any entry's `expected_properties` (ablation reads it regardless), so `check-all` does not run it and the count stays 123/123.
