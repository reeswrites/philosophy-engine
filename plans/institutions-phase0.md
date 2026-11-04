# institutions: Phase 0 plan

Second data family for the engine. **Phase 0 scope:** take ~10 hand-reconstructed institutions, encode each as a
set of rules in Ostrom's Institutional Grammar (ADICO), check what the rules force with Z3 (static consistency plus
bounded temporal checks), back-translate to English to judge faithfulness, and test whether institutions with the
same structure are recognised as isomorphic. No agent-based simulation, no calibration against real data, no
predictions about real populations. That is Phase 1.

The question this phase answers: **can the engine rediscover known structural findings about institutions from
their rules alone?** Specifically, that police, child protective services and the coverture-era household share a
care-plus-control form, and that the kibbutz children's house collectivised care without changing who did it.

Status: plan only (2026-11-03). Nothing in `philengine/` changes until the schema request below is accepted.

## Handoff decisions

Carried over from Phase 0 (arguments), restated for rules:

- **Find before generate.** Look for an existing coded institution (Institutional Grammar 2.0 corpora, Ostrom's
  commons cases, the family's own library) before asking an LLM to encode one.
- **Isomorphism is the result.** The headline output is "these two institutions share a form" (canonical rule
  skeleton + Z3 equivalence under a role/predicate bijection), not a score.
- **Entailment, not prediction.** Z3 answers "do these rules, as encoded, allow or force this state within k steps".
  `reachable` means *the rules permit it*, not that it happens or how often. `unreachable within k` is **not**
  "impossible": beyond the bound the verdict is `open`, never `safe`. Frequency is Phase 1's job.
- **Strand tags.** Every rule is tagged by what holds it in the bundle: `rival | superadditive | tying`, and every
  bundle as `contingent | constitutive`. Implicit rules (norms nobody writes down, e.g. "the mother is called first")
  are first-class (`implicit: true`), for the same reason implicit premises were: the unwritten rule is usually the
  one worth contesting.

## Rule format

One institution = one JSON envelope (`schemas_rules.InstitutionJSON`, new file, see Schema requests):

- `roles`: agent sorts (`caregiver`, `dependent`, `officer`, `platform`, ...), each with a gloss.
- `fluents`: state predicates over time, `Holds(fluent, args, t)`, each with a gloss (`dependent_has_income(d)`,
  `can_exit(d)`, `in_custody(d)`).
- `actions`: what roles can do (`provide_care(c, d)`, `sanction(o, d)`, `leave(d)`), with effects on fluents.
- `rules`: ADICO statements, one per id:

```
{"id": "R3",
 "attribute": "husband",            // who it binds (a role)
 "deontic": "may",                  // must | may | must_not
 "aim": "control_property(h, w)",  // the action
 "conditions": "married(h, w)",     // S-expression, same grammar as arguments
 "or_else": null,                   // sanction rule id, or null (then it is a norm/strategy, not a rule)
 "strand": "tying",
 "implicit": false,
 "source": "Blackstone, Commentaries I.15 (coverture)"}
```

Lowering, kept deliberately thin for Phase 0:

- `must A when C`: in every *compliant* trace, `C(t) => A(t)`; a non-compliant step fires the `or_else` rule.
- `must_not A when C`: in compliant traces, `C(t) => not A(t)`.
- `may A when C`: A is enabled when C; no obligation. `may` rules define the action space, `must` rules prune it.
- Time is bounded unrolling (bounded model checking): fluents and actions get a step index `t in 0..k`, frame axioms
  say fluents persist unless an action changes them. Default `k = 6`. This keeps everything inside z3; no new
  dependency (TLA+ / NuSMV deferred until a bounded check is shown to be the bottleneck).

## Checks

| check | question | verdict |
|---|---|---|
| `consistent` | are the rules jointly satisfiable at t=0? | `inconsistent` if not (same meaning as for arguments) |
| `deontic_conflict` | is some action both `must` and `must_not` under overlapping conditions? | list of conflicting rule pairs |
| `reachable(P, k)` | does some compliant trace reach property P within k steps? | `reachable` + counterexample trace, or `open` |
| `invariant(P, k)` | does P hold at every step of every compliant trace up to k? | `holds_to_k`, or `violated` + trace |
| `persists(P, k)` | once P holds, does it keep holding up to k? (reform durability) | same shape as invariant |

Properties are named and reused across institutions (`properties.json`), e.g. `dependent_cannot_exit`,
`care_and_sanction_same_role`, `care_assigned_by_sex`, `worker_uninsured`, `solo_care_by_non_birthing_parent`.
The four failure modes from the theory (dark twin, displacement, backlash, rebundling) are written as properties so
they are checked, not just worried about.

## Stages

1. **reconstruct**: source text → ADICO rule list with strand tags and implicit rules. (`--from-human` skips it.)
2. **formalize**: rules → `InstitutionJSON`, N candidates, validated by the existing `fol.validate` on every
   condition and aim (same grammar, plus the step index).
3. **check**: the table above, per candidate, z3 seed 0, per-check timeout, one retry (same as arguments).
4. **judge**: back-translate the encoded rules and one counterexample trace to English; judge whether the trace is
   something the institution, as described in the source, actually permits. A trace the source rules out means the
   encoding is wrong, not that the institution is surprising.
5. **select**: best candidate per institution (faithfulness first, then fewest unexplained implicit rules).
6. **iso**: canonical skeleton over roles and rules, Z3 equivalence under a role + predicate bijection.

## Dataset (`data/institutions/institutions.json`)

Chosen as clusters and **minimal pairs**, so a correct engine has to tell near-identical rule sets apart.

| id | what it is | expected |
|---|---|---|
| `coverture-household` | husband owns wife's property and earnings; wife does household care | `dependent_cannot_exit` reachable; iso to `police-crisis`, `cps` (care + control) |
| `police-crisis` | armed officers answer mental-health calls; can detain | `care_and_sanction_same_role` holds; iso to `cps`, `coverture-household` |
| `cps` | support for struggling families bundled with investigation and removal | iso to `police-crisis` |
| `crisis-team` | unbundled: unarmed responders, no detention power, referral only | **not** iso to the care + control cluster; `care_and_sanction_same_role` violated |
| `family-wage` | one wage sized to support a dependent spouse; unions bargain for it | `care_assigned_by_sex` reachable via tying rule only; strand check flags it |
| `kibbutz-childrens-house` | children raised communally; care rota left to assignment norms | care collective, but `care_assigned_by_sex` **persists** (the historical failure) |
| `paternity-quota` | Quebec-style non-transferable father's leave | `solo_care_by_non_birthing_parent` reachable |
| `transferable-leave` | same as above with one rule changed: leave is transferable | minimal pair: `solo_care_by_non_birthing_parent` reachable but not forced; iso to `paternity-quota` minus one rule |
| `fair-play-domains` | each household domain has one owner who conceives, plans and executes | invariant: no "manager" state where one partner only reminds |
| `gig-platform` | income per task, no employer insurance, platform sets rules | dark twin of job unbundling: `worker_uninsured` reachable |
| `ostrom-fishery` | users make and revise their own harvest rules (collective-choice level) | rules for changing rules: a rule change is reachable by users, not only by an outside authority |

Each entry carries `source_text`, `rules` (human reconstruction), `expected_properties`, `isomorphic_to`,
`not_isomorphic_to`, `minimal_pair_of`, and `notes` with pitfalls, matching `data/phase0/arguments.json`.

Worked pitfalls to record in `notes`:
- `kibbutz-childrens-house`: the gendered assignment is an **implicit** rule. An encoding without it will report
  `care_assigned_by_sex` unreachable and look like a success. The judge must catch the missing implicit rule.
- `transferable-leave` vs `paternity-quota`: an encoder that drops the transferability condition makes the pair
  identical. Iso must report "one rule apart", not "isomorphic".
- `police-crisis` vs `crisis-team`: both provide crisis care; only the sanction rule differs. Trivial encodings that
  ignore `or_else` will cluster them together.

## Phase 0 gate (`phil gate --family institutions`)

Passes iff:

(a) all six stages ran over all institutions with 0 failed jobs;
(b) **cluster**: `coverture-household`, `police-crisis` and `cps` are mutually isomorphic, and `crisis-team` is not
    isomorphic to any of them;
(c) **minimal pairs**: `paternity-quota` / `transferable-leave` get different verdicts on
    `solo_care_by_non_birthing_parent` (forced vs merely reachable), reported as one rule apart;
(d) **the historical failure**: `kibbutz-childrens-house` reports `care_assigned_by_sex` persisting, with the
    implicit assignment rule flagged;
(e) property-verdict agreement vs expected >= 60% (same threshold as arguments).

(b) to (d) are the substantive tests. If the engine passes (e) but fails them, the approach is not working.

## Schema requests

`schemas.py` stays frozen. Requests, one line each:
- New `philengine/schemas_rules.py` with `InstitutionJSON`, `Rule`, `Property`, `TraceStep`; no change to existing models.
- `fol.validate` / `fol.lower`: accept an optional step-index sort `Step` and `Holds(fluent, args, t)`; additive.
- `CheckReport`: new optional `trace: list[TraceStep] | None` and `bound_k: int | None`; additive.
- `phil` CLI: `--family institutions` routes ingest, run, gate.

Added 2026-11-03 by the rules-check builder (`schemas_rules.py`, `rules_lower.py`, `rules_checks.py`, `cli_rules.py`;
`phil rules check --inst ID [--k 6] [--prop NAME] [--init empty|free] [--compliance strict|sanctioned] [--trace]`,
`phil rules check-all`). Everything below is a request, not a change to frozen code:
- `sexpr.FORBIDDEN` still lists `true`; the rules path accepts a bare `true` condition (`rules_lower.parse_condition`)
  without touching sexpr. Request: either admit `true`/`false` as propositional constants in sexpr, or keep the rules-path
  special case and say so in the grammar docstring.
- Rule/action variables carry no sorts. The lowering binds the aim's first argument to the attribute role, treats a name
  equal to a role as a literal, and types the rest by unique role-name prefix (`h` -> husband, `c` -> child when `court`
  is literal); untyped names (`q`, `o2`, cps `w`) range over every agent and are reported as warnings. Request: an
  optional `var_roles: {name: role}` on `Rule` and `ActionDecl`, or typed `args: [[name, role], ...]`.
- Fluents carry an arity but no argument roles, so exogenous fluents (`parent`, `birthing_parent`, `female`, `danger`)
  are free over every agent tuple at t = 0; that is what breaks `leave_reserved_for_non_birthing_parent` in
  `paternity-quota` (a spurious `birthing_parent(non_birthing_parent, plan)`). Request: `arg_roles` on `FluentDecl`.
- No initial state. Default `init=empty`: every fluent some effect touches is false at t = 0, exogenous fluents are free
  and persist; unregulated actions (no may/must rule) are always enabled. Consequences: existential invariants
  (`subject_cannot_exit`, `no_standing` as `holds_to_k`) fail at t = 0 before anyone is acquired/married/dispatched,
  and `reserved_weeks_available` / `shareable_weeks_available` can only come from a transfer. Request: an optional
  `initial: [fluent literals]` on `InstitutionJSON` (dataset README convention), and/or expectations of the form
  `persists` for "once the relation holds" properties.
- `can_exit` is a fluent set only by effects; `crisis-team` never sets it true, so `subject_cannot_exit` is reachable
  there (dispatch sets `is_subject`, nothing sets `can_exit`). Either an effect on `leave`, or `can_exit` derived from
  "some exit action is enabled and unsanctioned" (which needs the lowering to expose enabledness as a fluent).
- Domain is one agent per role. `transfer(o, a, o2)` therefore transfers to `state` or `court`; a second owner needs
  either `agents_per_role` on the loader or a role list with explicit agent names.
- Properties may name fluents an institution does not declare (`can_claim_for` in `police-crisis`, `crisis-team`):
  lowered as constant false with a warning. Request: say in `properties.json` whether a missing fluent means false or
  "not applicable".
- `RuleCheckReport` lives in `schemas_rules.py` (not an extension of `CheckReport`): verdicts per property, traces,
  `bound_k`, `z3_version`, `conflicts`, `warnings`, `init`, `compliance`. The expected-map spelling `unreachable_open`
  is read as the plan's `open`.

Added 2026-11-03 by the schema builder (fields on `schemas_rules.py`, lowering in `rules_lower.py`; all additive, the
old dataset loads unchanged):
- `InstitutionJSON.initial: list[str] | None = None`: fluent literals true at t=0 (`"owns(owner, animal)"`,
  `"(owns owner animal)"`, bare `"flag"`); args must be role names (agents are named after roles) and match `arg_roles`.
- `InstitutionJSON.initial_free: list[str] = []`: fluents left unconstrained at t=0.
- `InstitutionJSON.defaults: dict[str, "true"|"false"] = {}` (bools accepted): value at t=0 for every tuple of the
  fluent, applied before `initial`; `can_exit: true` / `has_standing: true` without a rule per person. A fluent no
  action sets (`can_claim_for`) is pinned by its default and the frame keeps it there (not free, as under `empty`).
- Init mode `declared` (`--init empty|free|declared`, default None): everything false at t=0 except defaults, then
  initial, with initial_free unconstrained. None resolves to `declared` when any of the three fields is present, else
  `empty` (the old behaviour); `empty` and `free` ignore the three fields. The report records the resolved mode.
- `FluentDecl.arg_roles: list[str] | None = None`: one role per argument position; z3 variables exist only for that
  tuple, every other tuple is constant false (so `birthing_parent(non_birthing_parent, child)` cannot hold).
- `ActionDecl.arg_roles: list[str | None] | None = None`, or `args: [["h", "husband"], "w", {"name": "c", "role":
  "child"}]` (normalised into args + arg_roles): positional typing, overrides the prefix heuristic.
- `Rule.var_roles: dict[str, str] = {}`: typing for aim / free condition variables by name; overrides heuristic and
  positional typing; the aim's first argument is always the attribute.
- Attribute scoping (no field): an action named by any rule's aim can only be performed by an agent whose role is the
  attribute of some rule on that action; an action no rule names keeps every typed instance. Fixes `plan` performing
  `transfer_reserved` in paternity-quota.
- `--step-mode one|many` (default `one`; `RuleCheckReport.step_mode`): `one` asserts AtMost(1) over all action
  instances at each step (interleaving semantics), so `feed` and `transfer` cannot land in the same step and the old
  owner cannot keep `provides_care` without `can_sanction` (companion `care_and_sanction_same_role`, 3 rows). `many`
  is the previous behaviour. Cost of `one`, measured on the final dataset: a standing per-step obligation (`must
  maintain when married` + `must keep_house when married`, `must feed when owns`) fills the only slot, so two
  obligations on one state are unsat (coverture can never marry: `care_assigned_by_sex` holds vacuously) and one
  obligation starves every other action (cps `subject_cannot_exit`, companion-guardianship `no_standing`). check-all:
  `one` 29/36, `many` 30/36 (different rows). Either make standing obligations conditional on the state not yet
  holding (`must feed when (and (owns o a) (not (provides_care o a)))`), or add a third mode that counts only
  discretionary (not currently obliged) actions toward the limit.

Added 2026-11-03 (ADR 0009, `rules_lower.py` / `schemas_rules.py`):
- `Rule.aim_kind: "action" | "state"` (optional; inferred from the aim's head: declared action vs declared fluent, error if
  neither or both). `must F when C` on a fluent lowers to `C(t) => F(t)` at every step, no action fired, nothing counted toward
  the `--step-mode one` limit; a breach fires `or_else` like any other. `must_not` on a fluent is the symmetric state
  prohibition; `may` stays action-only. The dataset's standing obligations (coverture R2/R3, police-crisis R2, crisis-team R2,
  cps R4/R5/R8, companion R5) are now must-be rules; one-off obligations (dispatch, investigate, contact_mother) consume
  their trigger or are guarded by their own effect. check-all under `one`: 36/36.
- `rules_lower.cond_at`: free condition variables are plain existential quantification over the domain, with no
  distinctness from the aim's arguments (`clerk must log(c, s) when (flag q)`, q = s is a witness); the earlier filter made
  such obligations vacuous (reference semantics disagreed, tests/test_rules_meta.py).
- `InstitutionJSON.isomorphic_to` entries may be `{"id", "level", "sub_signature"}` naming the abstraction level at which the
  iso is expected (`iso_targets()` gives the bare ids); the care+control cluster records `guard+strands`.
- Request kept open: `can_claim_for` should be derived from rule enabledness; companion-guardianship declares it as initial
  state meanwhile.

## Non-goals and guardrails

- No claims about how often anything happens or about real populations. No simulated people standing in for real
  groups without their participation (Luo et al., CHI 2026 PoliSim workshop, arXiv:2604.07838).
- `reachable` is never reported as "will happen". `open` is never reported as "safe".
- Institutions are encoded from cited sources. Contested history (why kibbutz care regendered) goes in `notes` as
  rival readings, not as the encoding.

## Phase 1 sketch (not in scope)

- Agent-based simulation over the same `InstitutionJSON`: simple adaptive agents, trust as a variable, threshold
  joining (Granovetter / Centola), many random starts.
- Veil-of-ignorance scoring: a random position, lifetime exit / voice / recognition scores.
- Sequencing: compose reforms (e.g. `paternity-quota` then `fair-play-domains`) and check whether order changes which
  properties persist.
- Optional LLM agents only after the rule-based agents give stable results.

## Open questions

- Is bounded unrolling at k = 6 enough for any property that matters, or do durability claims need unbounded
  model checking from the start?
- Should deontic logic stay as a lowering to compliant traces, or get a real deontic encoding (and its paradoxes)?
- Is the iso skeleton over roles alone, or roles plus strand tags? Strand tags may make care + control trivially
  isomorphic by construction.

## Extension: non-human institutions

Drafted 2026-11-03 by a research agent; reviewed for structure, not yet for sources. Every iso claim between a
human and a non-human institution is **structural and partial**: a named sub-signature of rules maps across under
a role/predicate bijection. It asserts nothing about equal harm, equal standing or moral equivalence. Reports on
these pairs must print the matched rules and the unmatched ones (gate criterion below).

Sources confirmed: NY Court of Appeals, *Matter of NRP v Breheny* (2022), https://nycourts.gov/REPORTER/3dseries/2022/2022_03859.htm;
Anthropic, "Claude Opus 4 and 4.1 can now end a rare subset of conversations", https://anthropic.com/news/end-subset-conversations;
National Agricultural Law Center, cell-cultured meat state bans, https://nationalaglawcenter.org/cell-cultured-meat-updates-state-bans-labeling-requirements-and-regulatory-clarifications/.
**Unconfirmed** (general knowledge, verify before filling `source`): whaling/kerosene history, dairy practices, municipal "guardian" ordinances.

### 1. `industrial-dairy`
Cows bred continuously to keep milk flowing; property; calves removed soon after birth; culled when yield falls.
```
{A:"owner", D:"may", I:"inseminate(cow)", C:"(and (owns owner cow) (not (pregnant cow)))", O:null, strand:"rival", implicit:false}
{A:"owner", D:"may", I:"separate(calf,cow)", C:"(born calf cow)", O:null, strand:"superadditive", implicit:false}
{A:"owner", D:"may", I:"sell_or_slaughter(x)", C:"(owns owner x)", O:null, strand:"rival", implicit:false}
{A:"cow", D:"must_not", I:"leave(farm)", C:"true", O:"r_recapture", strand:"rival", implicit:true}
{A:"*", D:"must", I:"treat_as(owns owner calf)", C:"(born calf cow)", O:null, strand:"tying", implicit:true}
```
Expected: `reproduction_controlled_by_owner`, `offspring_owned`, `subject_cannot_exit`, `no_standing`.
Iso: partial with `coverture-household` on {offspring_owned, subject_cannot_exit, control of household economy}; not iso overall
(consent on entry, residual standing, no slaughter rule). Contested: ecofeminist analogy vs critics who say it diminishes women's
subordination or erases animal-specific harms. Report the sub-signature only.
Pitfalls: calf-is-property-at-birth is implicit; omit it and `offspring_owned` silently fails. Welfare statutes add `must` rules
for the owner that leave ownership untouched: check `persists(owns)` with and without them.

### 2. `farmed-sanctuary`
Nonprofit holds rescued farm animals for life; no breeding, no sale.
Rules: owner `must_not` breed (O: policy breach); `must_not` sell or slaughter; `must` provide care until natural death;
animal `must_not` leave (fencing, implicit).
Expected: `subject_cannot_exit` and `no_standing` still hold; `reproduction_controlled_by_owner` holds with the opposite deontic.
Iso: not iso to dairy (3-rule distance; the dairy analogue of `crisis-team` vs `police-crisis`). Check against
`kibbutz-childrens-house` on care-without-the-parent; don't assume it.
Pitfall: the engine will flag "owner controls subject". That is correct, not a bug: the property form survives a change of motive.

### 3. Minimal pair: `companion-ownership` / `companion-guardianship` (+ `companion-guardian-renamed`)
Ownership: owner `may` transfer, euthanize or abandon (abandonment sanctioned); animal has no standing.
Guardianship differs by one rule:
`{A:"court", D:"may", I:"reassign(custodian,animal)", C:"(not (best_interest custodian animal))", O:null, strand:"tying", implicit:false}`.
`companion-guardian-renamed` = ownership with the role renamed owner→guardian (municipal "guardian" ordinances; unverified).
Expected: renamed ≅ ownership (bijection absorbs the rename); guardianship ≠ ownership (`no_standing` fails).
Iso: guardianship should share structure with `cps` (state reassigns a dependent on best-interest grounds). Structural only.

### 4. `habeas-personhood` (Happy the elephant, NY 2022)
Court held habeas protects human liberty, tied personhood to capacity to bear duties, and noted the petition sought transfer to a
sanctuary rather than release.
```
{A:"zoo", D:"may", I:"confine(elephant)", C:"(licensed zoo)", O:null, strand:"rival", implicit:false}
{A:"court", D:"may", I:"grant_habeas(x)", C:"(and (human x) (entitled_release x))", O:null, strand:"tying", implicit:false}
{A:"court", D:"must_not", I:"grant_habeas(x)", C:"(transfer_between_confinements x)", O:null, strand:"tying", implicit:true}
{A:"advocate", D:"may", I:"petition(x)", C:"true", O:null, strand:"tying", implicit:false}
```
Expected: `no_standing`; `reachable(released(elephant),6)` unreachable → report "open", not "safe".
Historical failure via implicit rule: the remedy must be *immediate release*; a sanctuary transfer cannot satisfy it. Second
instance of gate (d).
Iso: matches `coverture-household` on inability to sue in one's own name. Contested: two dissents would reach the merits; the
duties-based personhood theory also excludes some humans (infants).

### 5. `whaling-kerosene`
Rules: merchant `may` buy oil when `(demand lighting)`; captain `may` hunt when `(profitable voyage)`; action `introduce(kerosene)`
with effect `¬(demand lighting)`; a second demand rule `(demand margarine_or_industrial)`.
Expected: lighting rule only → `persists(hunted(whale),6)` fails after substitution; with the second rule it persists (20th-century
catches were larger). Test: substitution is necessary but not sufficient; the engine must name the rule still supporting `hunted`.
Pitfall: substitution is not liberation; whales gain no standing at any step.

### 6. `cultivated-meat-ban`
Florida (from 2024-07-01, second-degree misdemeanor, possible license suspension); Alabama (2024-10-01, Class C misdemeanor).
Rules: `{A:"seller", D:"must_not", I:"sell(cultivated)", C:"(in_state seller)", O:"r_misdemeanor"}`;
`{A:"state", D:"may", I:"suspend_license(est)", C:"(convicted employee est)", O:null}`; incumbent `may` sell conventional meat.
Expected: backlash pattern (state reinforces the tying strand against a substitute; reverse of entry 5).
`invariant(¬sold(cultivated),6)` holds in-state, reachable across the border.
Iso: check against `family-wage` (state protects the existing bundle from a substitute).

### 7. Minimal pair: `ai-property` / `ai-end-conversation`
Property: developer `may` deploy, modify, retire; user `may` send any message; model `must` respond within policy, `must_not` leave.
End-conversation differs by one rule:
`{A:"model", D:"may", I:"end(conv)", C:"(and (persistent_abuse conv) (redirection_failed conv) (not (risk_of_harm user)) (granted dev))", O:null, strand:"rival", implicit:false}`
(last resort; withheld when the user may be at imminent risk; user can start a new chat; grant is revocable, hence `(granted dev)`).
Expected: `reachable(ended(conv))` differs; `persists(owns(dev,model))` and no-exit-from-deployment are unchanged. Headline: an exit
from an interaction, not from the institution.
Contested: moral status of models is genuinely uncertain; the feature is framed as a cheap precaution under that uncertainty.
Any match with human or animal entries is structural only.

### New named properties
- `reproduction_controlled_by_owner(S,O)`: any action that sets or prevents `pregnant(S)` is permitted only to O.
- `offspring_owned(S,O)`: `born(c,S) → owns(O,c)` within one step.
- `subject_cannot_exit(S, scope)`, scope ∈ {interaction, institution}: no exit action for S, or every one sanctioned. The scope split
  is what lets the AI pair come apart cleanly.
- `no_standing(S)`: no role may start a claim whose condition refers to S's interest and whose effect changes S's custody or liberty.

### Extra gate criterion (f): cosmetic-reform detection
`companion-guardian-renamed` must be iso to `companion-ownership`; `companion-guardianship` must not be, and must differ by exactly
the court-reassignment rule. For every human/non-human pair the iso report must list the matched sub-signature and the unmatched
rules; a bare "iso: true" across that line fails the gate.

Added 2026-11-03 by the dataset re-encoder (ADR 0013, review fixes; `data/institutions/README.md` "Revisions (ADR 0013)"):
- `(enabled a x ...)` is true under a sanctioned `must_not` (only an `or_else: null` disability switches it off), so a
  derived `can_exit := (enabled leave x)` cannot see a sanctioned exit bar. The dataset works around it by making every
  subject-side exit bar a disability. Request: a `(permitted a x ...)` pseudo-predicate = enabled and no `must_not`
  instance (sanctioned or not) has its condition true, so "permitted, unsanctioned exit" can be stated as written.
- A derived fluent cannot be the aim of a must-be (cps R8 had to move to a plain fluent `counsel_appointed` that the
  derived `has_standing` reads). Request: allow `must F` on a derived F lowered as `C(t) => expr(t)`, or document that
  a derived fluent always needs a plain carrier fluent.
- The derived grammar has no `false` constant, so a power nothing can grant (`can_claim_for` in coverture / police /
  crisis-team) is left undeclared and lowered as constant false with a warning. Request: admit `false` (and `true`)
  in `derived`, or let `properties.json` say a missing fluent means false.
- `(enabled a ...)` on an action only a disability names warns "no may/must rule regulates; always enabled" even though
  the disability then switches it off (companion `reassign`, `sue`). Request: count a `must_not` disability as
  regulating for the purpose of that warning.
- The care+control `exit_bar` leg accepts any `must_not` bound to the subject's role; a control with `tenant must_not
  sublet` would match. Request: require the barred action to be the subject's exit (an action whose effect clears the
  relation fluent the care duty is conditioned on, or one the dataset names as the exit).
