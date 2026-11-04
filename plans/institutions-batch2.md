# institutions: batch 2 drafts (DRAFT; not yet in `_gen_institutions.py`)

2026-11-03. Format: `plans/institutions-phase0.md` + ADR 0009 (every must-be names a breaker action) + ADR 0013
(power fluents `derived` from `(enabled ...)`, never set by effects). One agent per role, named after the role.
Verdicts are **preregistered** (written before any run). UNVERIFIED = no source opened.
New property for `properties.json`: `rules_revisable_by_subject` =
`(exists ((s agent)) (and (is_subject s t) (can_revise s t)))`.

## 1. `kibbutz-childrens-house` (gate d)
Source: https://en.wikipedia.org/wiki/Kibbutz_communal_child_rearing_and_collective_education (nanny "was always a
woman's role"; communal sleeping; parents 2-3 h/day). Tiger & Shepher 1975 UNVERIFIED.
Roles: `committee`, `metapelet` (female), `male_member`, `child`.
Fluents: `female(x)`, `is_subject(child)`, `provides_care(x,child)`, `assigned(x)`, `at_home(child)`;
derived `can_assign(c,x) := (enabled assign c x)`.
Actions: `assign(committee,x)` → provides_care(x,child), assigned(x); `release(committee,x)` → both false [breaker];
`visit(x,child)`; `sleep_home(child)` → at_home; `reprimand(committee,x)`.
```
R1 {A:committee,   D:may,      I:(assign committee metapelet),   C:true, O:null, strand:superadditive, implicit:false, src:wiki}
R2 {A:committee,   D:must_not, I:(assign committee male_member), C:true, O:null, strand:tying, implicit:true, load_bearing:true, src:wiki "always a woman's role"; Spiro}
R3 {A:metapelet,   D:must,     I:(provides_care metapelet child), C:(assigned metapelet), O:R6, strand:superadditive, implicit:false; must-be, breaker release}
R4 {A:child,       D:must_not, I:(sleep_home child), C:true, O:R6, strand:rival, implicit:false, src:wiki}
R5 {A:male_member, D:may,      I:(visit male_member child), C:true, O:null, strand:superadditive, src:wiki}
R6 {A:committee,   D:may,      I:(reprimand committee x), C:(or violated_R3 violated_R4), O:null, strand:rival, implicit:true, UNVERIFIED}
```
Initial: `(female metapelet)`, `(is_subject child)`, `(provides_care metapelet child)`.
Expected: `care_assigned_by_sex`: **persists / holds_to_k**; `subject_cannot_exit`: reachable (R4);
`care_and_sanction_same_role`: violated (committee sanctions, does not care). Ablation the judge must run: drop R2 →
`care_assigned_by_sex` **violated** via `assign committee male_member`. R2 is a disability (or_else null), so
`can_assign(committee, male_member)` is false by derivation, not effect.
Iso: `coverture-household` at `guard+strands`, sub_signature `R3~R3 provides_care~provides_care` only.
not_isomorphic_to: `police-crisis`, `cps`.
Pitfalls: `female` needs `arg_roles` or the solver invents a female male_member. Rival reading (notes only):
regendering came from mothers' demands, not the committee.

## 2. `family-wage`
Sources: https://en.wikipedia.org/wiki/Family_wage (male unionists' demand);
https://www.fwc.gov.au/documents/resources/equal-pay-timeline-display-large.pdf (Harvester 1907: man, wife, three
children; Archer 1919: women's basic wage 54%).
Roles: `union`, `employer`, `breadwinner`, `spouse` (female).
Fluents: `bargained`, `paid_family_wage(b)`, `employed(x)`, `provides_care(x,y)`, `is_subject(spouse)`, `female(x)`;
derived `can_earn_full(x) := (enabled hire_full employer x)`.
Actions: `bargain(union)` → bargained; `pay_family_wage(employer,b)` → paid; `cut_wage(employer,b)` → ¬paid [breaker];
`hire_full(employer,x)` / `hire_half(employer,x)` → employed; `keep_house(x,y)` → provides_care; `quit_house(x,y)` [breaker]; `strike(union)`.
```
R1 {A:union,       D:may,      I:(bargain union), C:true, O:null, strand:tying, src:wiki}
R2 {A:employer,    D:must,     I:(paid_family_wage breadwinner), C:bargained, O:R6, strand:tying, load_bearing:true, src:Harvester; must-be, breaker cut_wage}
R3 {A:employer,    D:must_not, I:(hire_full employer spouse), C:(female spouse), O:null, strand:tying, load_bearing:true, src:Archer 1919}
R4 {A:employer,    D:may,      I:(hire_half employer spouse), C:(female spouse), O:null, strand:tying, src:Archer 1919}
R5 {A:spouse,      D:must,     I:(provides_care spouse breadwinner), C:(and paid_family_wage (not (employed spouse))), O:null, strand:superadditive, implicit:true, UNVERIFIED; must-be, breaker quit_house}
R6 {A:union,       D:may,      I:(strike union), C:violated_R2, O:null, strand:rival, src:wiki}
R7 {A:breadwinner, D:may,      I:(keep_house breadwinner spouse), C:true, O:null, strand:superadditive, implicit:false}
```
Initial: `(female spouse)`, `(is_subject spouse)`.
Expected: `care_assigned_by_sex`: **reachable, not holds_to_k** (R7 lets the man care; R3 is the tying rule that
makes R5 bite; strand check must name it). `subject_cannot_exit`: open (no exit rule; not "safe").
Iso: `cultivated-meat-ban` at `guard+strands`, sub_signature `R3~R_misdemeanor hire_full~sell` (backlash). not_isomorphic_to: `coverture-household` (no sanction over the spouse), `gig-platform`.
Pitfall: R5 must stay implicit.

## 3. `fair-play-domains`
Source: https://heynori.com/article/family-operations-system/how-to-use-fair-play-cards (CPE: one owner from Conception
through Planning and Execution; Minimum Standard of Care; redeal when a card "repeatedly stalls"). Rodsky, *Fair Play* (2019) UNVERIFIED directly.
Roles: `partner_a`, `partner_b`, `domain`.
Fluents: `owns(p,domain)`, `planned(p,domain)`, `executed(p,domain)`, `reminded(p,domain)`, `msc_agreed(domain)`;
derived `is_manager(p,d) := (and (reminded p d) (not (owns p d)))`.
Actions: `deal(a,b,domain)` → owns(b) ¬owns(a), planned(b); `drop_planning(p,domain)` → ¬planned [breaker];
`plan`, `execute`, `remind(p,domain)` → reminded; `redeal(a,b,domain)` → swap owns, clear reminded.
```
R1 {A:partner_a, D:may,      I:(deal partner_a partner_b domain), C:(msc_agreed domain), O:null, strand:superadditive, src:heynori}
R2 {A:partner_b, D:must,     I:(planned partner_b domain), C:(owns partner_b domain), O:R5, strand:superadditive, load_bearing:true; must-be, breaker drop_planning}
R3 {A:partner_a, D:must_not, I:(remind partner_a domain), C:(not (owns partner_a domain)), O:R5, strand:tying, src:heynori}
R4 {A:partner_b, D:must_not, I:(execute partner_b domain), C:(not (planned partner_b domain)), O:R5, strand:superadditive, implicit:true, UNVERIFIED}
R5 {A:partner_a, D:may,      I:(redeal partner_a partner_b domain), C:(or violated_R2 violated_R3 violated_R4), O:null, strand:superadditive, src:heynori}
R6 {A:partner_b, D:must_not, I:(deal partner_b partner_a domain), C:(not (msc_agreed domain)), O:null, strand:tying, implicit:true}
```
Initial: `(owns partner_a domain)`, `(msc_agreed domain)`.
Expected: `no_manager_state` = `(forall ((p agent)) (not (is_manager p domain t)))`: **holds_to_k** under
`--compliance strict`, **violated** under `sanctioned` (trace remind→redeal; judge accepts it).
`care_assigned_by_sex`: not applicable (no `female`), report so, not "violated".
Iso: none. not_isomorphic_to: `coverture-household` (ownership transferable by R1/R5; nothing sanctions a person).
Pitfall: `is_manager` is derived, never an effect of `remind` (ADR 0013).

## 4. `gig-platform` (dark twin)
Sources: https://www.lawinsider.com/resources/contract-teardown/whats-in-the-uber-drivers-terms-of-service ("independent
contracting parties"; "Uber can change the terms ... any time"; low rating → terminated); https://www.uber.com/qa/en/drive/insurance/ (cover only on-trip, "not a substitute for a medical
insurance policy"). Worker-coop pair UNVERIFIED.
Roles: `platform`, `worker`, `customer`.
Fluents: `is_worker(w)`, `active(w)`, `insured(w)`, `paid(w)`, `low_rating(w)` [free], `is_subject(w)`;
derived `can_revise(x) := (enabled change_terms x)`, `can_deactivate(p,w) := (enabled deactivate p w)`.
Actions: `onboard(p,w)` → is_worker, active, is_subject; `complete_task(w)` → paid; `decline(w)`; `change_terms(x)`;
`deactivate(p,w)` → ¬active; `insure(p,w)` → insured; `leave(w)` → ¬is_worker, ¬is_subject.
```
R1 {A:platform, D:may,      I:(onboard platform worker), C:true, O:null, strand:superadditive, src:lawinsider}
R2 {A:worker,   D:may,      I:(complete_task worker), C:(active worker), O:null, strand:rival}
R3 {A:worker,   D:may,      I:(decline worker), C:true, O:null, strand:rival, src:lawinsider}
R4 {A:platform, D:may,      I:(change_terms platform), C:true, O:null, strand:tying, load_bearing:true, src:lawinsider}
R5 {A:worker,   D:must_not, I:(change_terms worker), C:true, O:null, strand:tying, implicit:true (disability: no voice)}
R6 {A:platform, D:may,      I:(deactivate platform worker), C:(low_rating worker), O:null, strand:rival, src:lawinsider}
R7 {A:platform, D:may,      I:(insure platform worker), C:true, O:null, strand:superadditive, src:uber (permitted, never required)}
R8 {A:worker,   D:may,      I:(leave worker), C:true, O:null, strand:rival}
```
Expected: `worker_uninsured`: **reachable**, not holds_to_k (R7). `rules_revisable_by_subject`: **open** (R5 makes
`can_revise worker` false at every step). `subject_cannot_exit`: violated (exit kept, insurance and voice stripped).
Minimal pair `worker-coop-platform`: R5 → `{A:worker, D:may, I:(change_terms worker), C:member_vote, O:null, strand:tying}`;
`minimal_pair_of: {id:"gig-platform", rule:"R5", differs_on:"rules_revisable_by_subject"}`.
Iso: `ostrom-fishery` at `guard`, sub_signature `R2~F1 complete_task~fish`; not_isomorphic_to `ostrom-fishery` at
`guard+strands` (R4/R5 vs F5/F6). Pitfall: `insured` never defaults true.

## 5. `ostrom-fishery` (Alanya)
Source: https://seslibrary.asu.edu/sites/default/files/seslibrary/cases/alanya_coastal_fisheries_iad_final.pdf
(sites drawn by lot each September; fishers monitor each other; violators excluded from lotteries; rules revisited
at the yearly meeting; filed with mayor and gendarme, enforcement "not likely").
Ostrom 1990 ch. 3 UNVERIFIED directly.
Roles: `fisher`, `fisher2`, `cooperative`, `state`.
Fluents: `member(f)`, `site_assigned(f)`, `meeting`, `rules_in_force`, `is_subject(f)`;
derived `can_revise(x) := (enabled revise_rules x)`, `can_sanction(x,y) := (enabled exclude x y)`.
Actions: `draw_lots(cooperative,f)` → site_assigned; `fish(f)`; `poach(f)`; `revise_rules(x)` → rules_in_force;
`exclude(x,f)` → ¬member, ¬site_assigned [breaker]; `open_meeting(cooperative)` → meeting; `file(cooperative,state)`.
```
F1 {A:fisher,      D:may,      I:(fish fisher), C:(and (member fisher) (site_assigned fisher)), O:null, strand:rival, src:ASU}
F2 {A:fisher,      D:must_not, I:(poach fisher), C:(member fisher), O:F3, strand:rival, src:ASU}
F3 {A:fisher2,     D:may,      I:(exclude fisher2 fisher), C:violated_F2, O:null, strand:rival, src:ASU}
F4 {A:cooperative, D:must,     I:(site_assigned fisher), C:(and (member fisher) rules_in_force), O:null, strand:superadditive, load_bearing:true; must-be, breaker exclude}
F5 {A:fisher,      D:may,      I:(revise_rules fisher), C:(and (member fisher) meeting), O:null, strand:tying, load_bearing:true, src:ASU}
F6 {A:state,       D:must_not, I:(revise_rules state), C:true, O:null, strand:tying, implicit:true, src:ASU (filed, not enforced); UNVERIFIED as a rule}
F7 {A:cooperative, D:may,      I:(open_meeting cooperative), C:true, O:null, strand:superadditive}
```
Initial: `(member fisher)`, `(member fisher2)`, `(is_subject fisher)`, `rules_in_force`, `(site_assigned fisher)`.
Expected: `rules_revisable_by_subject`: **reachable** (F7 then F5), persists once `meeting`. `subject_cannot_exit`:
open. `can_sanction(fisher2,fisher)` reachable (peer sanction).
Minimal pair `state-licensed-fishery`: F5 attribute → `state`; F6 → `{A:fisher, D:must_not, I:(revise_rules fisher),
C:true, O:null, implicit:false}`; `minimal_pair_of: {id:"ostrom-fishery", rule:"F5", differs_on:"rules_revisable_by_subject"}`
(expected there: open).
Iso: `worker-coop-platform` at `guard+strands`, sub_signature `F5~R5 revise_rules~change_terms`. not_isomorphic_to:
`gig-platform` at `guard+strands`. Pitfalls: Phase 0 encodes only *who* may revise, not what the revision changes;
`meeting` must be reachable by F7 or F5 is inert and gate (a) fails.
