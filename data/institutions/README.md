# data/institutions

Hand-reconstructed institutions for the Phase 0 institutions family (`plans/institutions-phase0.md`).

- `institutions.json`: list of 11 entries (`coverture-household`, `police-crisis`, `cps`, `crisis-team`,
  `paternity-quota`, `transferable-leave`, `companion-ownership`, `companion-guardianship`,
  `companion-guardian-renamed`, and the two negative controls `lease`, `public-library`). Each has `roles`, `fluents`, `actions` (with effects as fluent literals),
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
  gone: its verdict now comes from R9 alone. Deleting police R3 and R5 now makes `care_and_sanction_same_role`
  violated, which is the point.
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
- **Expectations that disagree with results (left as expected, not tuned):** police-crisis and cps
  `care_and_sanction_same_role` expected `holds_to_k`, got `violated`. Derived, the sanction power exists only while
  its trigger (`danger`, `immediate_danger`, both exogenous) holds, while the care state persists; the state
  invariant asks for simultaneity, which the old effect-asserted encoding faked. The claim the cluster makes is
  rule-level (the same attribute holds the duty and the power), which the iso sub-signature now carries and the
  state invariant does not. companion-guardianship's bare `isomorphic_to: ["cps"]` is at level exact and reads NO
  (as before: the notes say the iso is partial, on R9 alone).
- Remaining warnings: `can_claim_for` undeclared in coverture / police / crisis-team (constant false: no advocate
  action exists there); `(enabled reassign|sue ...)` in companion-ownership / -renamed names actions only a
  disability regulates (they are enabled-then-disabled, which is the intended reading); untyped `p` in leave R3
  and `o2` in companion R1.
