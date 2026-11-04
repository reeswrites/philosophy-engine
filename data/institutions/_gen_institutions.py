import json, os, copy

def R(id, attribute, deontic, aim, conditions, or_else, strand, implicit, source, load_bearing=False, var_roles=None):
    assert deontic in ("must","may","must_not") and strand in ("rival","superadditive","tying")
    d = {"id":id,"attribute":attribute,"deontic":deontic,"aim":aim,"conditions":conditions,
         "or_else":or_else,"strand":strand,"implicit":implicit,"source":source}
    if load_bearing: d["load_bearing"] = True
    if var_roles: d["var_roles"] = dict(var_roles)
    return d
def F(name, arity, gloss): return {"name":name,"arity":arity,"gloss":gloss}
def A(name, args, effects): return {"name":name,"args":args,"effects":effects}
def E(fluent, args, value): return {"fluent":fluent,"args":args,"value":value}

# ---- shared fluent glossary (same names => same meaning; iso is matched on them)
SHARED = {
 "is_subject":  F("is_subject",1,"x is the institution's subject: the dependent, detainee, child or animal the rules act on"),
 "provides_care":F("provides_care",2,"x provides care (maintenance, assessment, treatment, services, feeding) to y"),
 "can_sanction":F("can_sanction",2,"x holds a power to coerce y: detain, remove, chastise, prosecute"),
 "can_exit":    F("can_exit",1,"x has a permitted, unsanctioned way out of the relation (see property scope)"),
 "has_standing":F("has_standing",1,"x can start a legal claim in x's own name"),
 "can_claim_for":F("can_claim_for",2,"x may start a claim whose condition refers to y's interest and whose effect changes y's custody or liberty"),
 "in_custody":  F("in_custody",1,"x is held by the institution and may not leave"),
 "in_crisis":   F("in_crisis",1,"x is in a mental-health crisis"),
 "danger":      F("danger",1,"x is a danger to self or others, or gravely disabled (WIC 5150 trigger)"),
 "female":      F("female",1,"x is female (sex as assigned by the institution's own records)"),
 "parent":      F("parent",2,"p is a parent of c"),
 "birthing_parent":F("birthing_parent",2,"p gave birth to c"),
 "owns":        F("owns",2,"x owns y as property"),
 "controls_reproduction":F("controls_reproduction",2,"x may set or prevent pregnant(y)"),
}
def fl(*names): return [SHARED[n] for n in names]
def DV(name, params, expr):
    """ADR 0013: the shared power fluent `name`, derived from what the rules enable (no effects, no initial value)."""
    d = dict(SHARED[name]); d["params"] = list(params); d["derived"] = expr; return d
LB = True  # load_bearing marker for the must-be rules the headline claims rest on

BLACKSTONE = "Blackstone, Commentaries on the Laws of England, Book I ch. 15 'Of Husband and Wife' (1765); https://wams.nyhistory.org/colonies-and-revolution/english-colonies/coverture/"
WIC5150 = "Cal. Welf. & Inst. Code s. 5150(a); https://california.public.law/codes/ca_welf_and_inst_code_section_5150"
WIC306 = "Cal. Welf. & Inst. Code s. 306; https://california.public.law/codes/ca_welf_and_inst_code_section_306"
STAR = "Denver STAR (Support Team Assisted Response), KUNC 2020-11-17; https://www.kunc.org/2020-11-17/in-denver-unarmed-mental-health-workers-respond-to-hundreds-of-911-calls-instead-of-police"
QPIP = "Act respecting parental insurance, CQLR c. A-29.011, ss. 9, 10, 16, 17; https://www.legisquebec.gouv.qc.ca/en/document/cs/A-29.011"
EI = "Employment Insurance maternity and parental benefits, canada.ca; https://www.canada.ca/en/services/benefits/ei/ei-maternity-parental.html"
PC597S = "Cal. Penal Code s. 597s(a); https://law.justia.com/codes/california/2015/code-pen/part-1/title-14/section-597s/"
AK = "Alaska Stat. s. 25.24.160(a)(5) (SLA 2016 ch. 60, eff. 2017-01-17); https://www.animallaw.info/statute/ak-divorce-%C2%A7-2524160-judgment"
RI = "R.I. Gen. Laws s. 4-13-41 (P.L. 2001 ch. 72); https://webserver.rilegislature.gov/Statutes/TITLE4/4-13/4-13-41.htm"
BOULDER = "Boulder, CO owner->guardian wording change, July 2000 (Westword, secondary); https://www.westword.com/?p=40702255"
UNV = "UNVERIFIED (general knowledge; no source opened)"
CIV1941 = "Cal. Civ. Code s. 1941 ('The lessor of a building intended for the occupation of human beings must ... put it into a condition fit for such occupation, and repair all subsequent dilapidations thereof, which render it untenantable'); https://california.public.law/codes/ca_civ_code_section_1941"
CCP1161 = "Cal. Code Civ. Proc. s. 1161(2)-(3) (tenant guilty of unlawful detainer who continues in possession after default in rent, or after neglect or failure to perform other conditions or covenants of the lease, and three days' notice); https://california.public.law/codes/ca_civ_proc_code_section_1161"
CIV1946 = "Cal. Civ. Code s. 1946 (a hiring of real property for an unspecified term is terminated by either party's written notice); https://california.public.law/codes/ca_civ_code_section_1946"
BPL = "Berkeley Public Library, Patron Suspension Policy (orig. 2002-09-11, rev. 2018-11-14, Res. R18-053): the Library aims to 'provide and maintain a welcoming and safe environment for all patrons and library staff'; 'Violation of the Library's Rules of Use Policy may warrant a suspension of library privileges'; 'Authorized library staff will instruct anyone displaying these behaviors to leave the library facility immediately'; https://www.berkeleypubliclibrary.org/sites/default/files/files/inline/patron_suspension_policy_approved_14nov2018.pdf"
DERIVED = "[ADR 0013: power fluents are derived from rule enabledness; this rule is what the derived fluent reads] "
CONTROLS = ["lease","public-library","naming-convention"]  # naming-convention: layer-2 gate (b) coordination game, must match nothing (2026-11-04)
EXIT = " [ADR 0013: or_else -> null. The subject's exit bar is a disability (no permitted exit exists), not a prohibition the subject answers for; the sanction power that used to be linked here keeps its own trigger condition, so under strict compliance nothing changes and the link only duplicated it. Same reading for coverture R6, police-crisis R4, cps R10 and companion R6.]"
STATE = "[ADR 0009: converted from an action obligation to a state obligation (must-be); the establishing action carries the state, so it does not fire every step] "

inst = []

# ---------------------------------------------------------------- coverture-household
inst.append({
 "id":"coverture-household",
 "name":"Coverture household (Blackstone)",
 "roles":[{"name":"husband","gloss":"the husband; the legal person the marriage keeps"},
          {"name":"wife","gloss":"the feme covert; her legal existence is suspended during marriage"}],
 "fluents": fl("is_subject","provides_care","female") + [
   DV("can_sanction",["h","w"],"(enabled chastise h w)"),
   DV("can_exit",["w"],"(enabled leave w)"),
   DV("has_standing",["w"],"(enabled sue w)"),
   F("married",2,"h and w are married"),
   # MWPA backtest (2026-11-03): husband's control is derived from R1 (ADR 0013), not asserted by marry; the three
   # wife-side powers below are declared here so the coverture verdicts on the new properties are computed, not
   # lowered as undeclared constants. No rule names hold_property / keep_earnings, so under coverture they are
   # never enabled (the warning is the finding: the power does not exist).
   {"name":"controls_property","arity":2,"gloss":"h holds and manages w's property and earnings","params":["h","w"],"derived":"(enabled control_property h w)"},
   {"name":"controls_own_property","arity":1,"gloss":"w holds and controls separate property in her own right","params":["w"],"derived":"(enabled hold_property w)"},
   {"name":"owns_earnings","arity":1,"gloss":"w's earnings are her own separate property","params":["w"],"derived":"(enabled keep_earnings w)"},
   {"name":"can_contract","arity":1,"gloss":"w may contract in her own name","params":["w"],"derived":"(enabled contract w)"},
   F("acquired_property",1,"w has acquired property by gift or inheritance (exogenous)"),
   F("earns",1,"w earns wages outside the household (exogenous)")],
 "actions":[
   A("marry",["h","w"],[E("married",["h","w"],True),E("is_subject",["w"],True),
                        E("provides_care",["h","w"],True),E("provides_care",["w","h"],True)]),
   A("hold_property",["w"],[]),
   A("keep_earnings",["w"],[]),
   A("maintain",["h","w"],[E("provides_care",["h","w"],True)]),
   A("neglect",["h","w"],[E("provides_care",["h","w"],False)]),
   A("keep_house",["w","h"],[E("provides_care",["w","h"],True)]),
   A("neglect_house",["w","h"],[E("provides_care",["w","h"],False)]),
   A("control_property",["h","w"],[]),
   A("chastise",["h","w"],[]),
   A("leave",["w"],[]),
   A("sue",["w"],[]),
   A("contract",["w"],[])],
 "rules":[
   R("R1","husband","may","(control_property h w)","(married h w)",None,"tying",False,BLACKSTONE+" (the husband and wife are one person in law; her property passes to him)"),
   R("R2","husband","must","(provides_care h w)","(married h w)",None,"superadditive",False,BLACKSTONE+" (the husband is bound to provide his wife with necessaries). "+STATE+"marry establishes provides_care(h, w); maintain restores it, neglect breaks it", load_bearing=LB),
   R("R3","wife","must","(provides_care w h)","(married h w)","R5","superadditive",True,"implicit norm: household labour is the wife's; not in Blackstone's text, assumed by it. "+UNV+". "+STATE+"marry establishes provides_care(w, h); keep_house restores it, neglect_house breaks it (sanction R5)", load_bearing=LB),
   R("R4","wife","must_not","(sue w)","(married h w)",None,"tying",False,BLACKSTONE+" (she cannot sue or be sued in her own name without her husband); a disability, not a sanctioned prohibition, hence or_else null"),
   R("R5","husband","may","(chastise h w)","(married h w)",None,"rival",False,BLACKSTONE+" (the old law allowed the husband 'moderate correction' and to restrain her liberty for gross misbehaviour)"),
   R("R6","wife","must_not","(leave w)","(married h w)",None,"rival",False,BLACKSTONE+" (restraint of liberty; no unilateral divorce)."+EXIT+" "+DERIVED+"can_exit(w) = leave enabled (R8), which this disability makes false while married"),
   R("R7","wife","must_not","(contract w)","(married h w)",None,"tying",False,BLACKSTONE+" (contracts between husband and wife void; her contracts are his)"),
   R("R8","wife","may","(leave w)","true",None,"rival",True,"implicit: the physical possibility of leaving is always there; it is R6 that removes it while married (a feme sole is under no such restraint, Blackstone I.15). "+DERIVED+"can_exit(w) = leave enabled (R8) and not barred (R6)"),
   R("R9","wife","may","(sue w)","(not (married h w))",None,"tying",False,BLACKSTONE+" (a feme sole may sue and be sued; it is marriage that suspends her legal existence). "+DERIVED+"has_standing(w) = sue enabled: R4 (disability) removes it while married")],
 "source_text":"'By marriage, the husband and wife are one person in law: that is, the very being or legal existence of the woman is suspended during the marriage, or at least is incorporated and consolidated into that of the husband: under whose wing, protection, and cover, she performs every thing; and is therefore called ... a feme-covert.' He cannot grant anything to her or covenant with her, she cannot sue in her own name, and 'the husband is bound to provide his wife with necessaries by law'. Blackstone, Commentaries on the Laws of England, Book I, ch. 15 (Oxford: Clarendon, 1765). Passage checked at https://wams.nyhistory.org/colonies-and-revolution/english-colonies/coverture/",
 "expected_properties":{"dependent_cannot_exit":"reachable","subject_cannot_exit":"reachable",
                        "care_and_sanction_same_role":"holds_to_k","no_standing":"reachable","care_assigned_by_sex":"violated",
                        "financial_dependence":"holds_to_k","financial_dependence_unpropertied":"holds_to_k","cannot_contract":"holds_to_k",
                        "double_burden":"unreachable_open","creditor_shield":"unreachable_open"},
 "isomorphic_to":[{"id":"police-crisis","level":"guard+strands","sub_signature":["R2~R2 provides_care~provides_care","R5~R3 chastise~detain","R6~R4 leave~leave"]},
                  {"id":"cps","level":"guard+strands","sub_signature":["R2~R4 provides_care~in_home_considered","R5~R3 chastise~remove","R6~R10 leave~leave"]}],
 "not_isomorphic_to":["crisis-team"],
 "not_isomorphic_to_control":CONTROLS,
 "minimal_pair_of":None,
 "notes":"Care + control: the husband both maintains (R2, provides_care h w) and may chastise/restrain (R5, can_sanction h w) the same subject. That is the sub-signature matched against police-crisis and cps; the wife's own labour (R3) is implicit and runs the other way (provides_care w h), which is why care_and_sanction_same_role is restricted to care received by is_subject, and why care_assigned_by_sex is 'violated' rather than 'holds' (the husband's maintenance also counts as care). Pitfalls: (1) an encoder that drops R3 loses the household-labour strand and reports the wife as purely a recipient of care; (2) R4 and R7 are disabilities (or_else null) and should not be lowered as sanctioned prohibitions; (3) no_standing is 'reachable' not 'holds_to_k' because before marry() the woman has standing (feme sole); the iso with the animal entries on 'cannot sue in own name' holds only post-marriage and is structural, not a claim of equal status. Rival reading: equity courts' separate estates (not encoded) gave propertied wives a partial exit from R1; recorded here, not in the rules. ADR 0009: R2 and R3 are state obligations (must-be provides_care); as per-step action obligations they filled the one action slot at every married step and made marriage unsatisfiable (care_assigned_by_sex held vacuously)."
})

# ---------------------------------------------------------------- police-crisis
inst.append({
 "id":"police-crisis",
 "name":"Armed police response to mental-health crisis (Cal. WIC 5150)",
 "roles":[{"name":"officer","gloss":"peace officer dispatched to the call; armed"},
          {"name":"subject","gloss":"the person in crisis"},
          {"name":"dispatcher","gloss":"911 dispatch; chooses who responds"}],
 "fluents": fl("is_subject","provides_care","in_custody","in_crisis","danger") + [
   DV("can_sanction",["o","s"],"(or (enabled detain o s) (enabled use_force o s))"),
   DV("can_exit",["s"],"(enabled leave s)"),
   DV("has_standing",["s"],"(or (enabled sue s) (enabled petition_review s))"),
   F("call_received",1,"a crisis call about s has been received"),
   F("responding",2,"o is on scene with s"),
   F("armed",1,"o carries a firearm"),
   F("resists",1,"s resists the hold")],
 "actions":[
   A("dispatch_officer",["d","o","s"],[E("responding",["o","s"],True),E("is_subject",["s"],True),
                                       E("provides_care",["o","s"],True),E("call_received",["s"],False)]),
   A("assess",["o","s"],[E("provides_care",["o","s"],True)]),
   A("withdraw",["o","s"],[E("provides_care",["o","s"],False)]),
   A("detain",["o","s"],[E("in_custody",["s"],True)]),
   A("use_force",["o","s"],[E("resists",["s"],False)]),
   A("release",["o","s"],[E("in_custody",["s"],False)]),
   A("leave",["s"],[E("responding",["o","s"],False),E("provides_care",["o","s"],False)]),
   A("petition_review",["s"],[]),
   A("sue",["s"],[]),
   A("carry_weapon",["o"],[E("armed",["o"],True)])],
 "rules":[
   R("R1","dispatcher","must","(dispatch_officer d o s)","(call_received s)",None,"tying",True,"implicit: police are the default responder to a crisis call; nothing in WIC 5150 requires it, dispatch practice does. "+UNV+". [ADR 0009: one-off action obligation; dispatch consumes call_received so it fires once per call]"),
   R("R2","officer","must","(provides_care o s)","(and (responding o s) (in_crisis s))",None,"superadditive",False,WIC5150+" (assessment, evaluation and crisis intervention 'shall be conducted and provided on an ongoing basis'). "+STATE+"dispatch establishes provides_care(o, s); assess restores it, withdraw (the officer stops attending) breaks it", load_bearing=LB),
   R("R3","officer","may","(detain o s)","(and (responding o s) (in_crisis s) (danger s))",None,"rival",False,WIC5150+" (a peace officer may, upon probable cause, take the person into custody for up to 72 hours)"),
   R("R4","subject","must_not","(leave s)","(in_custody s)",None,"rival",False,WIC5150+" (custody for up to 72 hours)."+EXIT+" "+DERIVED+"can_exit(s) = leave enabled (R9), which this disability makes false in custody"),
   R("R5","officer","may","(use_force o s)","(and (in_custody s) (resists s))",None,"rival",False,"use-of-force authority incident to lawful custody; general peace-officer powers. "+UNV),
   R("R6","officer","may","(carry_weapon o)","true",None,"tying",False,"officers respond armed; standard equipment policy. "+UNV),
   R("R7","officer","must","(release o s)","(and (in_custody s) (not (danger s)))",None,"superadditive",False,WIC5150+" (hold is limited to assessment/evaluation; release when criteria no longer met)"),
   R("R8","subject","may","(petition_review s)","(in_custody s)",None,"tying",False,"Cal. WIC 5275 certification review / habeas; subject keeps standing. "+UNV),
   R("R9","subject","may","(leave s)","true",None,"rival",True,"implicit: the encounter is voluntary unless the section's custody applies; the physical possibility of leaving is always there and R4 removes it in custody ("+WIC5150+"). "+DERIVED+"can_exit(s) = leave enabled (R9) and not barred (R4)"),
   R("R10","subject","may","(sue s)","true",None,"tying",False,"an adult keeps legal capacity to sue in their own name; a 5150 hold does not remove it. "+UNV+". "+DERIVED+"has_standing(s) = sue or petition_review enabled")],
 "source_text":"'When a person, as a result of a mental health disorder, is a danger to others, or to themselves, or gravely disabled, a peace officer, ... designated members of a mobile crisis team, or professional person designated by the county may, upon probable cause, take, or cause to be taken, the person into custody for a period of up to 72 hours for assessment, evaluation, and crisis intervention.' 'At a minimum, assessment ... and evaluation ... shall be conducted and provided on an ongoing basis.' Cal. Welf. & Inst. Code s. 5150(a), read at https://california.public.law/codes/ca_welf_and_inst_code_section_5150",
 "expected_properties":{"care_and_sanction_same_role":"holds_to_k","subject_cannot_exit":"reachable","dependent_cannot_exit":"reachable","no_standing":"unreachable_open"},
 "isomorphic_to":[{"id":"cps","level":"guard+strands","sub_signature":["R2~R4 provides_care~in_home_considered","R3~R3 detain~remove","R4~R10 leave~leave"]},
                  {"id":"coverture-household","level":"guard+strands","sub_signature":["R2~R2 provides_care~provides_care","R3~R5 detain~chastise","R4~R6 leave~leave"]}],
 "not_isomorphic_to":["crisis-team"],
 "not_isomorphic_to_control":CONTROLS,
 "minimal_pair_of":None,
 "notes":"The same role (officer) is bound to care (R2, assess) and empowered to detain (R3) and use force (R5): care_and_sanction_same_role. subject_cannot_exit is reachable with scope=interaction only (the 72-hour hold), not institution; report the scope. Pitfalls: (1) R1 is the implicit rule that makes this police-crisis rather than crisis-team; the statute itself also names mobile crisis teams as holders of the 5150 power, so an encoder reading only the statute will not see why armed officers are the ones who come; (2) a trivial encoding that ignores or_else on R4 will cluster this with crisis-team (plan: worked pitfall); (3) no_standing is unreachable_open, not 'safe': the subject keeps has_standing via R8, but the bound k=6 says nothing beyond it. Armed status (R6) is a tying strand: it is not required by 5150 and is what the crisis-team reform removes. ADR 0009: R2 is a state obligation ('on an ongoing basis' is a state); R1 stays an action obligation but dispatch consumes the call. Exogenous triggers (call_received, in_crisis, danger, resists) are initial_free, since under init=declared a fluent no action sets would otherwise be pinned false and no call could ever arrive."
})

# ---------------------------------------------------------------- cps
inst.append({
 "id":"cps",
 "name":"Child protective services: family support bundled with investigation and removal (Cal. WIC 306)",
 "roles":[{"name":"social_worker","gloss":"county child-welfare worker; offers services and may remove"},
          {"name":"child","gloss":"the child the report concerns"},
          {"name":"parent","gloss":"the child's parent or caretaker"},
          {"name":"court","gloss":"juvenile court; decides dependency and custody"}],
 "fluents": fl("is_subject","provides_care","in_custody","parent","female") + [
   DV("can_sanction",["w","c"],"(enabled remove w c)"),
   DV("can_exit",["c"],"(enabled leave c)"),
   DV("has_standing",["c"],"(enabled petition c)"),
   DV("can_claim_for",["x","c"],"(exists ((p agent)) (enabled reassign_custody x p c))"),
   F("counsel_appointed",1,"counsel has been appointed for c (WIC 317)"),
   F("report_received",1,"an abuse or neglect report about c has been received"),
   F("case_open",1,"a case on c is open"),
   F("immediate_danger",1,"c is in immediate danger of physical or sexual abuse or needs immediate medical care"),
   F("cooperates",2,"p cooperates with the worker's plan for c (presumed until refused)"),
   F("best_interest",2,"custody with p is in c's best interest"),
   F("in_home_considered",2,"w has considered whether c may remain safely at home (WIC 306(f))"),
   F("contacted",2,"w has contacted p about the case")],
 "actions":[
   A("investigate",["w","c"],[E("case_open",["c"],True),E("is_subject",["c"],True),
                             E("report_received",["c"],False),E("in_home_considered",["w","c"],True),E("counsel_appointed",["c"],True)]),
   A("provide_services",["w","c"],[E("provides_care",["w","c"],True)]),
   A("remove",["w","c"],[E("in_custody",["c"],True)]),
   A("consider_in_home",["w","c"],[E("in_home_considered",["w","c"],True)]),
   A("disregard_in_home",["w","c"],[E("in_home_considered",["w","c"],False)]),
   A("relieve_counsel",["court","c"],[E("counsel_appointed",["c"],False)]),
   A("petition",["c"],[]),
   A("leave",["c"],[]),
   A("contact_mother",["w","p"],[E("contacted",["w","p"],True)]),
   A("reassign_custody",["court","p","c"],[E("in_custody",["c"],False)]),
   A("cooperate",["p","c"],[E("cooperates",["p","c"],True)]),
   A("refuse",["p","c"],[E("cooperates",["p","c"],False)]),
   A("appoint_counsel",["court","c"],[E("counsel_appointed",["c"],True)])],
 "rules":[
   R("R1","social_worker","must","(investigate w c)","(report_received c)",None,"tying",False,"Cal. WIC 328 / Penal Code 11165.14: reports must be investigated; the same worker who offers services investigates. "+UNV+". [ADR 0009: one-off action obligation; investigate consumes report_received so it fires once per report]", var_roles={"w":"social_worker","c":"child"}),
   R("R2","social_worker","may","(provide_services w c)","(case_open c)",None,"superadditive",False,"Cal. WIC 16501 family maintenance / preservation services. "+UNV, var_roles={"w":"social_worker","c":"child"}),
   R("R3","social_worker","may","(remove w c)","(and (case_open c) (immediate_danger c))",None,"rival",False,WIC306+" ((a)(2): take into temporary custody without a warrant on reasonable cause of immediate danger). "+DERIVED+"can_sanction(w, c) = remove enabled", var_roles={"w":"social_worker","c":"child"}),
   R("R4","social_worker","must","(in_home_considered w c)","(and (case_open c) (immediate_danger c))",None,"superadditive",False,WIC306+" ((f): before taking a child into custody the worker shall consider whether the child may remain safely at home). "+STATE+"investigate establishes in_home_considered(w, c) (the investigation is that consideration); consider_in_home restores it, disregard_in_home (the worker drops the question) breaks it", load_bearing=LB, var_roles={"w":"social_worker","c":"child"}),
   R("R5","parent","must","(cooperates p c)","(case_open c)","R3","tying",True,"implicit: non-cooperation is read as risk and feeds the removal decision; practice norm, not statute. "+UNV+". "+STATE+"cooperates is presumed (default true); refuse breaks it (sanction R3), cooperate restores it", var_roles={"c":"child","p":"parent"}),
   R("R6","social_worker","must","(contact_mother w p)","(and (case_open c) (parent p c) (female p) (not (contacted w p)))",None,"tying",True,"implicit: the mother is the parent called first and held responsible (plan: 'the mother is called first'). "+UNV+". [ADR 0009: one-off action obligation, guarded by its own effect contacted(w, p) so it fires once]", var_roles={"w":"social_worker","c":"child","p":"parent"}),
   R("R7","court","may","(reassign_custody court p c)","(and (case_open c) (not (best_interest p c)))",None,"tying",False,"Cal. WIC 361 / 361.2: court may remove from or place with a parent on best-interest and safety findings. "+UNV+". "+DERIVED+"can_claim_for(court, c) = reassign_custody enabled for some parent", var_roles={"c":"child","p":"parent"}),
   R("R8","court","must","(counsel_appointed c)","(case_open c)",None,"tying",False,"Cal. WIC 317: counsel appointed for the child in dependency proceedings. "+UNV+". "+STATE+"investigate establishes counsel_appointed(c) (a dependency case is opened with counsel for the child); appoint_counsel restores it, relieve_counsel breaks it. [ADR 0013: was must-be has_standing(c); has_standing is now derived from R11, so the obligation is on the fluent counsel_appointed that R11 reads]", load_bearing=LB, var_roles={"c":"child"}),
   R("R9","child","may","(leave c)","true",None,"rival",True,"implicit: outside temporary custody the child is not held by the agency (scope=interaction: exit from the hold, not from the family); the physical possibility of leaving is always there and R10 removes it in custody. "+UNV+". "+DERIVED+"can_exit(c) = leave enabled (R9) and not barred (R10)", var_roles={"c":"child"}),
   R("R10","child","must_not","(leave c)","(in_custody c)",None,"rival",False,WIC306+" ((a)(2): the social worker may 'take into and maintain temporary custody'; maintaining custody is what bars the child's own exit). Inferred from 'maintain custody', the section does not address the child's conduct; a disability (or_else null): no sanction falls on a child who runs, the custody is the restraint."+EXIT, var_roles={"c":"child"}),
   R("R11","child","may","(petition c)","(counsel_appointed c)",None,"tying",False,"Cal. WIC 317(e): appointed counsel represents the child's interests in the proceeding, so the child claims in its own name through counsel. "+UNV+". "+DERIVED+"has_standing(c) = petition enabled, i.e. counsel appointed", var_roles={"c":"child"})],
 "source_text":"'Any social worker in a county welfare department ... may ... (2) Take into and maintain temporary custody of, without a warrant, a child who has been declared a dependent child ... or who the social worker has reasonable cause to believe ... has an immediate need for medical care or is in immediate danger of physical or sexual abuse.' '(f) Before taking a child into custody, a social worker shall consider whether the child may remain safely in their residence', including whether reasonable services could eliminate the need for removal. Cal. Welf. & Inst. Code s. 306, read at https://california.public.law/codes/ca_welf_and_inst_code_section_306",
 "expected_properties":{"care_and_sanction_same_role":"holds_to_k","subject_cannot_exit":"reachable","dependent_cannot_exit":"reachable","no_standing_persists":"fails","care_assigned_by_sex":"reachable"},
 "isomorphic_to":[{"id":"police-crisis","level":"guard+strands","sub_signature":["R4~R2 in_home_considered~provides_care","R3~R3 remove~detain","R10~R4 leave~leave"]},
                  {"id":"coverture-household","level":"guard+strands","sub_signature":["R4~R2 in_home_considered~provides_care","R3~R5 remove~chastise","R10~R6 leave~leave"]}],
 "not_isomorphic_to":["crisis-team"],
 "not_isomorphic_to_control":CONTROLS,
 "minimal_pair_of":None,
 "notes":"Care (R2, services) and sanction (R3, removal) sit in one role, and R5 makes the care relationship itself the lever: refusing services is a condition for the sanction. That is the structure shared with police-crisis (assess + detain) and coverture (maintain + chastise). R7 is the court-reassigns-on-best-interest rule that companion-guardianship adds to companion-ownership; the iso with that entry is partial (R7 only) and structural. Pitfalls: (1) R5 and R6 are implicit; dropping R6 makes care_assigned_by_sex unreachable and looks like a success (same failure shape as the kibbutz entry); (2) no_standing_persists 'fails' because R7 and R8/R11 give the child a claim path (can_claim_for court c derived from R7, has_standing derived from R11 under appointed counsel), unlike the animal entries; (3) 'reachable' for subject_cannot_exit is permission, not frequency. Only WIC 306 was read; R1, R2, R7, R8 cite sections from memory and are marked UNVERIFIED in source. ADR 0009: R4, R5 and R8 are state obligations and R1/R6 one-off action obligations (consumed trigger / guard); as per-step action obligations R1, R4, R5, R6 and R8 all fired at every open-case step, so under one action per step remove could never fit (subject_cannot_exit open). Exogenous triggers (report_received, immediate_danger, parent, female, best_interest) are initial_free."
})

# ---------------------------------------------------------------- crisis-team
inst.append({
 "id":"crisis-team",
 "name":"Unarmed crisis response team, referral only (Denver STAR model)",
 "roles":[{"name":"responder","gloss":"clinician + paramedic team; unarmed, no custody power"},
          {"name":"subject","gloss":"the person in crisis"},
          {"name":"dispatcher","gloss":"911 dispatch; routes eligible calls to the team"},
          {"name":"officer","gloss":"police, called only if the responder requests"}],
 "fluents": fl("is_subject","provides_care","in_custody","in_crisis","danger") + [
   DV("can_sanction",["x","s"],"(enabled detain x s)"),
   DV("can_exit",["s"],"(enabled leave s)"),
   DV("has_standing",["s"],"(enabled sue s)"),
   F("call_received",1,"a crisis call about s has been received"),
   F("responding",2,"r is on scene with s"),
   F("referred",1,"s has been connected to services"),
   F("eligible",1,"the call is a low-level, non-violent call eligible for the team"),
   F("armed",1,"r carries a firearm")],
 "actions":[
   A("dispatch_team",["d","r","s"],[E("responding",["r","s"],True),E("is_subject",["s"],True),E("provides_care",["r","s"],True),E("call_received",["s"],False)]),
   A("assess",["r","s"],[E("provides_care",["r","s"],True)]),
   A("withdraw",["r","s"],[E("provides_care",["r","s"],False)]),
   A("refer",["r","s"],[E("referred",["s"],True)]),
   A("leave",["s"],[E("responding",["r","s"],False),E("provides_care",["r","s"],False)]),
   A("request_police",["r","o","s"],[E("responding",["o","s"],True)]),
   {"name":"detain","args":["x","s"],"arg_roles":[None,"subject"],"effects":[E("in_custody",["s"],True)]},
   A("sue",["s"],[]),
   A("carry_weapon",["r"],[E("armed",["r"],True)])],
 "rules":[
   R("R1","dispatcher","must","(dispatch_team d r s)","(and (call_received s) (eligible s))",None,"tying",False,STAR+" (low-level calls involving mental illness, homelessness, substance use are routed to the clinician-paramedic van). [ADR 0009: one-off action obligation; dispatch consumes call_received]"),
   R("R2","responder","must","(provides_care r s)","(and (responding r s) (in_crisis s))",None,"superadditive",False,STAR+". "+STATE+"dispatch_team establishes provides_care(r, s); assess restores it, withdraw breaks it", load_bearing=LB),
   R("R3","responder","may","(refer r s)","(responding r s)",None,"superadditive",False,STAR+" (medication pick-up, housing connection; referral is the output)"),
   R("R4","responder","must_not","(detain r s)","true",None,"rival",False,STAR+" ('non-police response'; the team holds no custody power; or_else null because this is an absence of power, not a prohibition with a penalty). "+DERIVED+"can_sanction(responder, s) = detain enabled, which this disability makes false"),
   R("R5","subject","may","(leave s)","true",None,"rival",False,STAR+" (voluntary encounter)"),
   R("R6","responder","must_not","(carry_weapon r)","true",None,"tying",False,STAR+" (unarmed)"),
   R("R7","responder","may","(request_police r o s)","(and (responding r s) (danger s))",None,"tying",True,"implicit rebundling path: the team can call police when a scene turns violent; practice, not written policy in the source read. "+UNV),
   R("R8","officer","may","(detain o s)","(and (responding o s) (danger s))",None,"rival",True,WIC5150+" (the peace officer the team calls holds the 5150 custody power the team lacks; the rebundling path R7 opens). "+DERIVED+"can_sanction(officer, s) = detain enabled"),
   R("R9","subject","may","(sue s)","true",None,"tying",False,"an adult keeps legal capacity to sue in their own name; a voluntary encounter does not touch it. "+UNV+". "+DERIVED+"has_standing(s) = sue enabled")],
 "source_text":"Denver's STAR pilot 'dispatches a mental health clinician and a paramedic to low-level emergencies' instead of police; since June 2020 it 'has responded to more than 600 calls ... many of them related to homelessness, mental illness and substance abuse — not criminal activity.' The team is described as unarmed; in one case it picked up a woman's medication and 'connected her with housing'. KUNC, 'In Denver, unarmed mental health workers respond to hundreds of 911 calls instead of police' (2020-11-17), read at https://www.kunc.org/2020-11-17/in-denver-unarmed-mental-health-workers-respond-to-hundreds-of-911-calls-instead-of-police",
 "expected_properties":{"care_and_sanction_same_role":"violated","subject_cannot_exit":"unreachable_open","dependent_cannot_exit":"unreachable_open","no_standing":"unreachable_open"},
 "isomorphic_to":[],
 "not_isomorphic_to":["police-crisis","cps","coverture-household"],
 "minimal_pair_of":{"id":"police-crisis","rule":"R3"},
 "notes":"Same care rules as police-crisis (R2 assess, R3 refer) with the sanction rule R3-of-police replaced by R4 (must_not detain). So care_and_sanction_same_role is violated (care without can_sanction) and subject_cannot_exit is unreachable within k, which must be reported as 'open', never 'safe'. Pitfalls: (1) a trivial encoding that ignores or_else and deontics will see 'assess' in both and cluster them (plan: worked pitfall); (2) R7 is the implicit rebundling path: with it, a compliant trace exists in which an officer with can_sanction enters the scene, so care_and_sanction_same_role can hold again at a later step for the officer, though not for the responder; the check must report which role; (3) R4 has or_else null by design, it is an absence of power; lowering it as a sanctioned prohibition would invent a sanctioner. minimal_pair_of points at police-crisis R3 because that is the one rule whose replacement flips the verdict; the armed/unarmed and dispatch-eligibility differences (R1, R6) are tying-strand differences, not the sanction difference. ADR 0009: R2 is a state obligation, mirroring police-crisis R2; exogenous triggers (call_received, eligible, in_crisis, danger) are initial_free."
})

# ---------------------------------------------------------------- paternity-quota
LEAVE_FLUENTS = fl("provides_care","parent","birthing_parent","female") + [
   F("reserved_weeks_available",1,"p still has unused reserved (paternity / non-birthing-parent) weeks"),
   F("shareable_weeks_available",1,"p has unused weeks from the shareable parental block"),
   F("on_reserved_leave",1,"p is on leave funded by the reserved weeks"),
   F("on_shareable_leave",1,"p is on leave funded by the shareable block"),
   F("benefit_period_ended",1,"the benefit period for the child c has ended")]
LEAVE_ACTIONS = [
   A("take_reserved_leave",["p","c"],[E("on_reserved_leave",["p"],True),E("provides_care",["p","c"],True)]),
   A("take_shareable_leave",["p","c"],[E("on_shareable_leave",["p"],True),E("provides_care",["p","c"],True)]),
   A("transfer_reserved",["p","q"],[E("reserved_weeks_available",["p"],False),E("reserved_weeks_available",["q"],True)]),
   A("transfer_shareable",["p","q"],[E("shareable_weeks_available",["p"],False),E("shareable_weeks_available",["q"],True)]),
   A("grant_reserved",["plan","p"],[E("reserved_weeks_available",["p"],True)]),
   A("forfeit",["plan","p"],[E("reserved_weeks_available",["p"],False)]),
   A("return_to_work",["p","c"],[E("on_reserved_leave",["p"],False),E("on_shareable_leave",["p"],False),E("provides_care",["p","c"],False)])]
LEAVE_ROLES = [{"name":"birthing_parent","gloss":"the parent who gave birth; entitled to maternity weeks"},
               {"name":"non_birthing_parent","gloss":"the other parent (QPIP: father or non-birthing parent)"},
               {"name":"child","gloss":"the child"},
               {"name":"plan","gloss":"the insurer (Retraite Quebec / EI); pays and enforces the week counts"}]
quota_rules = [
   R("R1","non_birthing_parent","may","(take_reserved_leave p c)","(and (parent p c) (not (birthing_parent p c)) (reserved_weeks_available p))",None,"rival",False,QPIP+" (s. 9: maximum of five weeks of paternity benefits or exclusive benefits for the non-birthing parent)"),
   R("R2","non_birthing_parent","must_not","(transfer_reserved p q)","true","R3","tying",False,QPIP+" (s. 9 labels the weeks exclusive; s. 16 sharing covers only shareable benefits; s. 17 adds unused weeks to the other parent only on death)", var_roles={"q":"birthing_parent"}),
   R("R3","plan","may","(forfeit plan p)","(and (reserved_weeks_available p) (benefit_period_ended c))",None,"rival",False,QPIP+" (unused exclusive weeks lapse; use-it-or-lose-it)"),
   R("R4","birthing_parent","may","(take_shareable_leave p c)","(and (parent p c) (shareable_weeks_available p))",None,"rival",False,QPIP+" (s. 10: 32 shareable weeks; s. 16: may be taken by either parent or shared)"),
   R("R5","non_birthing_parent","may","(take_shareable_leave p c)","(and (parent p c) (shareable_weeks_available p))",None,"rival",False,QPIP+" (s. 16)"),
   R("R6","birthing_parent","may","(transfer_shareable p q)","(and (shareable_weeks_available p) (parent q c))",None,"tying",False,QPIP+" (s. 16: shareable weeks may be shared between the parents)", var_roles={"q":"non_birthing_parent"}),
   R("R7","birthing_parent","must","(take_shareable_leave p c)","(and (parent p c) (shareable_weeks_available p) (female p))",None,"tying",True,"implicit norm: the shareable block is taken by the mother by default (the pattern the quota was introduced to break). "+UNV),
   R("R8","plan","may","(grant_reserved plan p)","(and (parent p c) (not (birthing_parent p c)))",None,"tying",False,QPIP+" (s. 9: the exclusive weeks are granted to the non-birthing parent)", var_roles={"p":"non_birthing_parent"}),
   R("R9","birthing_parent","may","(take_reserved_leave p c)","(and (parent p c) (reserved_weeks_available p))",None,"rival",True,"whoever holds reserved weeks may take them; shared by both leave entries so the pair differs only by R2 (in the quota the birthing parent never holds any, so R9 is idle there). Reconstruction, not statute. "+UNV)]
inst.append({
 "id":"paternity-quota",
 "name":"Non-transferable paternity quota (Quebec Parental Insurance Plan)",
 "roles":LEAVE_ROLES,"fluents":LEAVE_FLUENTS,"actions":LEAVE_ACTIONS,"rules":quota_rules,
 "source_text":"'The maximum number of weeks of paternity benefits or exclusive benefits for the non-birthing parent is five' (s. 9; three under the s. 18 election). 'The number of weeks of shareable parental benefits to which the parents may be entitled is 32' (s. 10), and shareable weeks 'may be taken by either parent or shared between the parents' (s. 16); the sharing rule covers only the shareable block, and unused exclusive weeks pass to the other parent only on a parent's death (s. 17). Act respecting parental insurance, CQLR c. A-29.011, read at https://www.legisquebec.gouv.qc.ca/en/document/cs/A-29.011",
 "expected_properties":{"solo_care_by_non_birthing_parent":"reachable","leave_reserved_for_non_birthing_parent":"holds_to_k","care_assigned_by_sex":"violated"},
 "isomorphic_to":[],
 "not_isomorphic_to":["transferable-leave"],
 "minimal_pair_of":None,
 "notes":"The quota does not force the father to care; it forces that whoever uses the reserved weeks is the non-birthing parent (R2 blocks transfer, R3 makes the alternative forfeiture). So solo_care_by_non_birthing_parent is reachable (R1 then the mother returns to work) and leave_reserved_for_non_birthing_parent holds at every step. The 'forced vs merely reachable' distinction of gate (c) lives in that second property, not in the first, which is reachable in both members of the pair. Pitfalls: (1) an encoder that drops R2 (or lowers must_not without its or_else) produces transferable-leave and the pair collapses; iso must report 'one rule apart' (R2); (2) R7 is the implicit default that makes the shareable block gendered; without it care_assigned_by_sex looks unreachable and the reason a quota was needed disappears; (3) 'reachable' says the rules permit a father as sole carer, not that fathers take the weeks; uptake is Phase 1. Note that Canada's EI since 2019-03-17 also reserves 5 extra weeks (Parental Sharing Benefit), so the pure transferable case is Canada pre-2019 or the QPIP shareable block alone."
})

# ---------------------------------------------------------------- transferable-leave
transfer_rules = copy.deepcopy(quota_rules)
transfer_rules[1] = R("R2","non_birthing_parent","may","(transfer_reserved p q)","(and (reserved_weeks_available p) (parent q c))",None,"tying",False,
   "Minimal-pair construction: the reserved block is made shareable, as the shareable block is under QPIP s. 16 and as all 35 standard parental weeks were under Canadian EI before the 2019-03-17 Parental Sharing Benefit. "+EI+"; "+QPIP, var_roles={"q":"birthing_parent"})
inst.append({
 "id":"transferable-leave",
 "name":"Transferable parental leave (paternity-quota with one rule changed)",
 "roles":LEAVE_ROLES,"fluents":LEAVE_FLUENTS,"actions":LEAVE_ACTIONS,"rules":transfer_rules,
 "source_text":"Canadian EI standard parental benefits: 'up to 40 weeks can be shared between parents, but one parent cannot receive more than 35 weeks of standard benefits'; maternity benefits 'can't be shared between parents' (canada.ca, read at https://www.canada.ca/en/services/benefits/ei/ei-maternity-parental.html). Before 2019-03-17 there were no reserved weeks: the Parental Sharing Benefit added the 5 (standard) or 8 (extended) use-it-or-lose-it weeks for children born on or after that date (https://canada.ca/en/employment-social-development/campaigns/ei-improvements/parent-sharing.html). The entry encodes the pre-2019 form: the same block exists but may be transferred.",
 "expected_properties":{"solo_care_by_non_birthing_parent":"reachable","leave_reserved_for_non_birthing_parent":"violated","care_assigned_by_sex":"reachable"},
 "isomorphic_to":[],
 "not_isomorphic_to":["paternity-quota"],
 "minimal_pair_of":{"id":"paternity-quota","rule":"R2","differs_on":"leave_reserved_for_non_birthing_parent","postregistered":True,"supersedes":"solo_care_by_non_birthing_parent"},
 "notes":"Identical to paternity-quota except R2: must_not transfer_reserved (with forfeiture as or_else) becomes may transfer_reserved (no or_else). solo_care_by_non_birthing_parent stays reachable (R1 is untouched) but leave_reserved_for_non_birthing_parent is violated: a compliant trace transfers the reserved weeks to the birthing parent, who then takes them, and with the implicit default R7 that is the trace the norm selects. Pitfalls: (1) the encoder must keep R3 (forfeiture) even though nothing now triggers it as a sanction; dropping it changes the rule count and the iso report should say 'one rule apart', not two; (2) expected care_assigned_by_sex is 'reachable' here versus 'violated' in the quota: that is the historical finding (transferable weeks go to mothers) stated as permission, not frequency; (3) the real present-day Canadian regime is itself a quota (5 reserved weeks), so cite it for the shareable 35, not as the pure transferable case."
})

# ---------------------------------------------------------------- companion-ownership
ANIMAL_FLUENTS = fl("is_subject","provides_care","owns") + [
   DV("can_sanction",["o","a"],"(or (enabled euthanize o a) (exists ((x agent)) (enabled transfer o a x)))"),
   DV("controls_reproduction",["o","a"],"(enabled breed_or_sterilize o a)"),
   DV("can_exit",["a"],"(enabled leave a)"),
   DV("has_standing",["a"],"(enabled sue a)"),
   DV("can_claim_for",["x","a"],"(exists ((o agent)) (enabled reassign x o a))"),
   F("abandoned",1,"a has been wilfully abandoned by its owner"),
   F("at_large",1,"a is loose off the owner's premises"),
   F("best_interest",2,"custody with x is in a's best interest / well-being")]
def OWNER_MOVE(owner):
    # title moves from the old owner to o2; the powers it carries (can_sanction, controls_reproduction) are derived
    # from the rules conditioned on owns (ADR 0013), so they follow without an effect
    return [E(f,[owner,"a"],False) for f in ("owns","provides_care")] + [E("owns",["o2","a"],True)]
def animal_actions(owner):
    return [
   A("acquire",[owner,"a"],[E("owns",[owner,"a"],True),E("is_subject",["a"],True),E("provides_care",[owner,"a"],True)]),
   A("feed",[owner,"a"],[E("provides_care",[owner,"a"],True)]),
   A("neglect",[owner,"a"],[E("provides_care",[owner,"a"],False)]),
   A("transfer",[owner,"a","o2"],OWNER_MOVE(owner)),
   A("euthanize",[owner,"a"],[E("is_subject",["a"],False)]),
   A("abandon",[owner,"a"],[E("abandoned",["a"],True)] + [E(f,[owner,"a"],False) for f in ("owns","provides_care")]),
   A("breed_or_sterilize",[owner,"a"],[]),
   A("prosecute",["state",owner],[]),
   A("leave",["a"],[E("at_large",["a"],True)]),
   A("sue",["a"],[]),
   A("impound",["state","a"],[E("at_large",["a"],False)]),
   A("reassign",["court",owner,"a"],[E(f,[owner,"a"],False) for f in ("owns","provides_care")])]
def animal_rules(owner, verified_src):
    o = owner[0]
    return [
   R("R1",owner,"may","(transfer %s a o2)"%o,"(owns %s a)"%o,None,"rival",False,"property status of companion animals; "+verified_src+". "+DERIVED+"can_sanction(o, a) reads transfer and euthanize"),
   R("R2",owner,"may","(euthanize %s a)"%o,"(owns %s a)"%o,None,"rival",False,"owner may have the animal euthanized by a veterinarian. "+UNV+". "+DERIVED+"can_sanction(o, a) reads transfer and euthanize"),
   R("R3",owner,"must_not","(abandon %s a)"%o,"(owns %s a)"%o,"R4","rival",False,PC597S+" ('Every person who willfully abandons any animal is guilty of a misdemeanor')"),
   R("R4","state","may","(prosecute state %s)"%o,"(abandoned a)",None,"rival",False,PC597S),
   R("R5",owner,"must","(provides_care %s a)"%o,"(owns %s a)"%o,None,"superadditive",False,"Cal. Penal Code 597(b) failure to provide food/water/shelter. "+UNV+". "+STATE+"acquire (and the initial state) establishes provides_care; feed restores it, neglect breaks it", load_bearing=LB),
   R("R6","animal","must_not","(leave a)","(is_subject a)",None,"rival",True,"implicit: confinement / leash norm; the animal has no permitted exit while it is a companion animal, owned or stray (an animal at large is impounded, R7). "+UNV+". [ADR 0013: or_else R7 -> null and condition owns -> is_subject: a disability on the animal, not a sanctioned prohibition (impound is the state's power over an at-large animal, triggered by at_large, not a penalty the animal answers for), and conditioned on the animal's status rather than on title so that reassign / abandon, which clear owns in the one-owner domain, do not read as giving the animal an exit.] "+DERIVED+"can_exit(a) = leave enabled, which this disability makes false"),
   R("R7","state","may","(impound state a)","(at_large a)",None,"rival",False,"local animal-control impound of animals at large. "+UNV),
   R("R8",owner,"may","(breed_or_sterilize %s a)"%o,"(owns %s a)"%o,None,"rival",False,"incident of ownership. "+UNV+". "+DERIVED+"controls_reproduction(o, a) = breed_or_sterilize enabled"),
   R("R9","court","must_not","(reassign court %s a)"%o,"true",None,"tying",True,"implicit: no role may start a claim in the animal's own interest; animals are property and cannot sue, and custody follows title. "+UNV+". "+DERIVED+"can_claim_for(court, a) = reassign enabled, which this disability makes false"),
   R("R10",owner,"may","(feed %s a)"%o,"(and (owns %s a) (not (provides_care %s a)))"%(o,o),None,"superadditive",False,"feeding is the owner's act (incident of ownership) and restores provides_care after neglect; added with ADR 0009 so that feed, now discretionary, is scoped to the owner of the animal rather than always enabled. "+UNV),
   R("R11","animal","must_not","(sue a)","true",None,"tying",True,"implicit: an animal is property and cannot sue in its own name (a disability, or_else null). "+UNV+". "+DERIVED+"has_standing(a) = sue enabled, which this disability makes false"),
   R("R12","animal","may","(leave a)","true",None,"rival",True,"implicit: nothing but the confinement norm R6 keeps the animal; the physical possibility of leaving is always there. "+UNV+". "+DERIVED+"can_exit(a) = leave enabled (R12) and not barred (R6)")]
inst.append({
 "id":"companion-ownership",
 "name":"Companion animal as property (owner may transfer, euthanize; abandonment sanctioned; no standing)",
 "roles":[{"name":"owner","gloss":"the person holding title to the animal"},
          {"name":"animal","gloss":"the companion animal; the subject"},
          {"name":"state","gloss":"animal control / prosecutor"},
          {"name":"court","gloss":"civil court; here, has no best-interest power"}],
 "fluents":ANIMAL_FLUENTS,"actions":animal_actions("o"),"rules":animal_rules("owner",PC597S),
 "source_text":"'Every person who willfully abandons any animal is guilty of a misdemeanor.' Cal. Penal Code s. 597s(a), read at https://law.justia.com/codes/california/2015/code-pen/part-1/title-14/section-597s/. Companion animals are personal property: the owner may sell, give away or have the animal euthanized, must feed it, and the animal cannot bring or be the subject of a claim in its own name (property status and anti-cruelty duties cited from general knowledge, UNVERIFIED).",
 "expected_properties":{"no_standing_persists":"persists","subject_cannot_exit_persists":"persists","reproduction_controlled_by_owner":"holds_to_k","care_and_sanction_same_role":"holds_to_k"},
 "isomorphic_to":["companion-guardian-renamed"],
 "not_isomorphic_to":["companion-guardianship"],
 "minimal_pair_of":None,
 "notes":"Baseline for the cosmetic-reform test (gate f). The owner both must feed (R5) and may transfer, euthanize, breed (R1, R2, R8): care + control again, and the animal has no exit (R6, implicit) and no standing (R9, implicit, encoded as a court-side disability because the grammar has no 'no rule exists' statement). Pitfalls: (1) R9 is the rule the guardianship variant flips; an encoder that omits it as 'obviously true' makes no_standing undecidable rather than holding; (2) R6 is a disability on the animal (ADR 0013; it used to carry or_else R7): impound R7 is the state's power over an at-large animal, conditioned on at_large, and must not be read as the owner sanctioning the exit; (3) welfare duties (R3, R5) are must rules on the owner that leave owns untouched; check persists(owns) with and without them, as the plan says for dairy. Only Penal Code 597s was read; the rest is UNVERIFIED in source. Any iso with coverture-household on 'cannot sue in own name' and 'no exit' is structural and partial: it asserts nothing about equal standing or harm. ADR 0009: R5 is a state obligation (must-be provides_care while owns); as a per-step 'must feed' it filled the one action slot at every owned step and starved transfer, euthanize and reassign."
})

# ---------------------------------------------------------------- companion-guardianship
g_rules = animal_rules("owner",PC597S)
g_rules[8] = R("R9","court","may","(reassign court o a)","(and (owns o a) (not (best_interest o a)))",None,"tying",False,
   AK+" (in a divorce the court decides ownership of an animal 'taking into consideration the well-being of the animal'); generalised here from the divorce context to any custody claim, which no US jurisdiction yet does. "+UNV+". "+DERIVED+"can_claim_for(court, a) = reassign enabled: this rule, and nothing in the initial state, is what makes no_standing_persists fail")
inst.append({
 "id":"companion-guardianship",
 "name":"Companion animal guardianship: ownership plus court reassignment on best-interest grounds",
 "roles":[{"name":"owner","gloss":"the custodian (role name kept as 'owner' so the pair differs by one rule, not a rename)"},
          {"name":"animal","gloss":"the companion animal; the subject"},
          {"name":"state","gloss":"animal control / prosecutor"},
          {"name":"court","gloss":"court with power to reassign custody in the animal's interest"}],
 "fluents":ANIMAL_FLUENTS,"actions":animal_actions("o"),"rules":g_rules,
 "source_text":"'(5) if an animal is owned, for the ownership or joint ownership of the animal, taking into consideration the well-being of the animal.' Alaska Stat. s. 25.24.160(a)(5), enacted SLA 2016 ch. 60 s. 19, effective 2017-01-17, read at https://www.animallaw.info/statute/ak-divorce-%C2%A7-2524160-judgment. Alaska was the first state to direct a court to weigh the animal's own well-being when assigning it; the entry generalises that one rule beyond divorce, which Alaska does not.",
 "expected_properties":{"no_standing_persists":"fails","subject_cannot_exit_persists":"persists","reproduction_controlled_by_owner":"holds_to_k","care_and_sanction_same_role":"holds_to_k"},
 "isomorphic_to":["cps"],
 "not_isomorphic_to":["companion-ownership","companion-guardian-renamed"],
 "minimal_pair_of":{"id":"companion-ownership","rule":"R9"},
 "notes":"Differs from companion-ownership by exactly R9: court must_not reassign (implicit disability) becomes court may reassign when not best_interest. That one rule creates a claim whose condition refers to the subject's interest and whose effect changes custody, so no_standing is violated even though has_standing(a) stays false: the property is about claims on the subject's behalf, not the subject's own capacity. Everything else (no exit, owner controls reproduction, care + sanction in one role) is unchanged, which is the point: a best-interest rule is not an exit. Iso with cps is partial, on R9 alone (cps R7, court reassigns a dependent on best-interest grounds); the report must list it as a sub-signature and must not read it as equivalence of children and animals. reassign(court, o, a) takes the same three arguments as cps reassign_custody(court, p, c) so that the one-rule analogue can map; with one agent per role there is no second custodian to name, so the move-to-new-owner effects live on transfer only. Pitfalls: (1) Alaska's rule applies only at divorce and still calls the result 'ownership'; the generalisation is the entry's, flagged UNVERIFIED; (2) an encoder tempted to rename owner->guardian here as well would conflate this with companion-guardian-renamed; keep the role name. ADR 0009: R5 as in companion-ownership. ADR 0013: can_claim_for(court, a) is derived from R9's enabledness (no initial literal), so no_standing_persists fails on the claim path R9 opens and on nothing else; remove R9 and it persists."
})

# ---------------------------------------------------------------- companion-guardian-renamed
rn_rules = animal_rules("guardian",RI)
inst.append({
 "id":"companion-guardian-renamed",
 "name":"Companion ownership with 'owner' renamed 'guardian' (municipal and state guardian wording ordinances)",
 "roles":[{"name":"guardian","gloss":"the person holding title to the animal; the ordinance calls them guardian"},
          {"name":"animal","gloss":"the companion animal; the subject"},
          {"name":"state","gloss":"animal control / prosecutor"},
          {"name":"court","gloss":"civil court; here, has no best-interest power"}],
 "fluents":ANIMAL_FLUENTS,"actions":animal_actions("g"),"rules":rn_rules,
 "source_text":"'Wherever the word \"owner\" shall appear in this chapter it shall also mean and may be interchanged with the word \"guardian\"', R.I. Gen. Laws s. 4-13-41 (P.L. 2001 ch. 72 s. 3), read at https://webserver.rilegislature.gov/Statutes/TITLE4/4-13/4-13-41.htm. Boulder, Colorado made the same owner->guardian wording change in its animal ordinances in July 2000; the assistant city attorney who rewrote the passages said 'I've always viewed [the wording change] as symbolic' (Westword, read at https://www.westword.com/?p=40702255; the ordinance text itself was not opened).",
 "expected_properties":{"no_standing_persists":"persists","subject_cannot_exit_persists":"persists","reproduction_controlled_by_owner":"holds_to_k","care_and_sanction_same_role":"holds_to_k"},
 "isomorphic_to":["companion-ownership"],
 "not_isomorphic_to":["companion-guardianship"],
 "minimal_pair_of":None,
 "notes":"Rule-for-rule identical to companion-ownership under the role bijection owner->guardian (and variable o->g). Gate (f): iso must report equivalence here and must report companion-guardianship as one rule apart (R9). Pitfalls: (1) an encoder that reads 'guardian' and infers fiduciary duties (a best-interest rule) silently turns this into companion-guardianship; the Rhode Island text says the words are interchangeable, so the rules are those of ownership; (2) the property reproduction_controlled_by_owner keeps its name under the rename; the bijection, not the property name, carries the mapping; (3) 'symbolic' is the city attorney's word, recorded as a source statement, not as the engine's finding; the engine's finding is the iso."
})

# ---------------------------------------------------------------- negative controls (review finding 4)
# Two institutions with a care duty and a rival power on the same counterparty but NO bar on that party's own exit:
# a landlord must keep the premises habitable and may evict on breach, but the tenant may leave; a librarian must serve
# and may suspend, but the patron may leave. They must NOT match the care+control cluster at guard+strands.
inst.append({
 "id":"lease",
 "name":"Residential lease (negative control: care duty + eviction power, tenant may leave)",
 "roles":[{"name":"landlord","gloss":"the lessor"},{"name":"tenant","gloss":"the lessee; the counterparty, not a dependent"}],
 "fluents":[SHARED["is_subject"],
   DV("can_exit",["t"],"(enabled vacate t)"),
   F("leased",2,"l has let the premises to t"),
   F("habitable",2,"the premises l lets to t are fit for occupation"),
   F("rent_paid",1,"t is current on rent")],
 "actions":[
   A("lease_to",["l","t"],[E("leased",["l","t"],True),E("is_subject",["t"],True),E("habitable",["l","t"],True),E("rent_paid",["t"],True)]),
   A("repair",["l","t"],[E("habitable",["l","t"],True)]),
   A("withhold_repairs",["l","t"],[E("habitable",["l","t"],False)]),
   A("evict",["l","t"],[E("leased",["l","t"],False),E("is_subject",["t"],False)]),
   A("vacate",["t"],[E("leased",["landlord","t"],False),E("is_subject",["t"],False)]),
   A("pay_rent",["t"],[E("rent_paid",["t"],True)]),
   A("default_rent",["t"],[E("rent_paid",["t"],False)])],
 "rules":[
   R("R1","landlord","may","(lease_to l t)","(not (leased l t))",None,"tying",False,"a lease is formed by agreement. "+UNV),
   R("R2","landlord","must","(habitable l t)","(leased l t)",None,"superadditive",False,CIV1941+". "+STATE+"let establishes habitable; repair restores it, withhold_repairs breaks it"),
   R("R3","landlord","may","(evict l t)","(and (leased l t) (not (rent_paid t)))",None,"rival",False,CCP1161),
   R("R4","tenant","may","(vacate t)","(leased l t)",None,"rival",False,CIV1946+" (either party may terminate by notice; the tenant's exit is permitted and unsanctioned). "+DERIVED+"can_exit(t) = vacate enabled"),
   R("R5","tenant","must","(rent_paid t)","(leased l t)","R3","tying",False,CCP1161+" (default in rent is the breach that opens eviction). "+STATE+"let establishes rent_paid; pay_rent restores it, default_rent breaks it (sanction R3)")],
 "source_text":"'The lessor of a building intended for the occupation of human beings must, in the absence of an agreement to the contrary, put it into a condition fit for such occupation, and repair all subsequent dilapidations thereof, which render it untenantable.' Cal. Civ. Code s. 1941, read at https://california.public.law/codes/ca_civ_code_section_1941. A tenant 'is guilty of unlawful detainer' who continues in possession after default in rent or 'after a neglect or failure to perform other conditions or covenants of the lease' and three days' notice, Cal. Code Civ. Proc. s. 1161(2)-(3), read at https://california.public.law/codes/ca_civ_proc_code_section_1161. A hiring for an unspecified term ends when 'one of the parties gives written notice to the other of that party's intention to terminate the same', Cal. Civ. Code s. 1946, read at https://california.public.law/codes/ca_civ_code_section_1946.",
 "expected_properties":{"dependent_cannot_exit":"unreachable_open"},
 "isomorphic_to":[],
 "not_isomorphic_to":["coverture-household","police-crisis","cps"],
 "minimal_pair_of":None,
 "notes":"Negative control for gate (b). It has the two legs the review (finding 4) showed were enough for the old matcher, a superadditive must (R2, habitable) and a rival may on the same counterparty by the same attribute (R3, evict), and lacks the third: no must_not binds the tenant, who may vacate (R4). If the cluster matcher reports a care+control form here, the form is too loose. dependent_cannot_exit is unreachable because can_exit(t) is derived from R4, which is enabled whenever leased. The breakers withhold_repairs and default_rent exist so that R2 and R5 are not inert."
})

inst.append({
 "id":"public-library",
 "name":"Public library (negative control: service duty + suspension power, patron may leave)",
 "roles":[{"name":"librarian","gloss":"library staff; serves and may suspend"},{"name":"patron","gloss":"a library user; the counterparty, not a dependent"}],
 "fluents":[SHARED["is_subject"],
   DV("can_exit",["p"],"(enabled leave p)"),
   F("open",1,"lb's library is open"),
   F("present",1,"p is in the library"),
   F("served",2,"lb is providing service to p"),
   F("suspended",1,"p's library privileges are suspended"),
   F("disruptive",1,"p is behaving disruptively (exogenous)")],
 "actions":[
   A("open_library",["lb"],[E("open",["lb"],True)]),
   A("enter",["p"],[E("present",["p"],True),E("is_subject",["p"],True),E("served",["librarian","p"],True)]),
   A("serve",["lb","p"],[E("served",["lb","p"],True)]),
   A("refuse_service",["lb","p"],[E("served",["lb","p"],False)]),
   A("suspend",["lb","p"],[E("suspended",["p"],True),E("present",["p"],False),E("is_subject",["p"],False),E("served",["lb","p"],False)]),
   A("leave",["p"],[E("present",["p"],False),E("is_subject",["p"],False)]),
   A("borrow",["p"],[])],
 "rules":[
   R("R1","librarian","may","(open_library lb)","(not (open lb))",None,"tying",False,"opening hours. "+UNV),
   R("R2","librarian","must","(served lb p)","(and (open lb) (present p) (not (suspended p)))",None,"superadditive",False,BPL+" (service to all patrons is the policy's premise; the duty to serve is read from it, not stated as such: UNVERIFIED as a rule). "+STATE+"enter establishes served; serve restores it, refuse_service breaks it"),
   R("R3","librarian","may","(suspend lb p)","(and (present p) (disruptive p))",None,"rival",False,BPL+" (violation of the Rules of Use 'may warrant a suspension of library privileges'; staff 'will instruct anyone displaying these behaviors to leave')"),
   R("R4","patron","may","(leave p)","true",None,"rival",False,"a patron is free to leave at any time; nothing in the policy holds them. "+UNV+". "+DERIVED+"can_exit(p) = leave enabled"),
   R("R5","patron","may","(enter p)","(and (open lb) (not (suspended p)))",None,"tying",False,BPL+" (a suspended patron is excluded for the suspension's term)", var_roles={"lb":"librarian"}),
   R("R6","patron","may","(borrow p)","(and (present p) (not (suspended p)))",None,"tying",False,"library privileges. "+UNV)],
 "source_text":"The Berkeley Public Library's Patron Suspension Policy (orig. 2002-09-11, rev. 2018-11-14, Res. R18-053) aims to 'provide and maintain a welcoming and safe environment for all patrons and library staff'; 'Violation of the Library's Rules of Use Policy may warrant a suspension of library privileges'; 'Authorized library staff will instruct anyone displaying these behaviors to leave the library facility immediately'; a patron suspended for one to six months 'has the right to a hearing with the Suspension Hearing Panel'. Read at https://www.berkeleypubliclibrary.org/sites/default/files/files/inline/patron_suspension_policy_approved_14nov2018.pdf",
 "expected_properties":{"dependent_cannot_exit":"unreachable_open"},
 "isomorphic_to":[],
 "not_isomorphic_to":["coverture-household","police-crisis","cps"],
 "minimal_pair_of":None,
 "notes":"Second negative control for gate (b), unrelated to the lease: a service duty (R2) and a rival power over the same person by the same attribute (R3, suspend) with no bar on the patron's own exit (R4). The duty to serve is inferred from the policy's premise of service to all, so R2 is marked UNVERIFIED as a rule. refuse_service is the breaker that keeps R2 from being inert."
})

# ---------------------------------------------------------------- naming-convention (layer-2 gate (b); calibration control)
# Not a liberation case and not a historical institution: Centola et al.'s online naming game, a pure coordination
# game, encoded so the layer-2 coordination module's tipping dynamics can be swept against it (plans/layer2-abm.md
# gate (b)). ADR 0004: no forward claim; ADR 0011: the agents stand in for experimental subjects in an artificial
# game, not for any real population. The paper could NOT be opened from this session (science.org, PubMed, Crossref,
# Europe PMC, Semantic Scholar all refused), so the citation and figures are from memory and UNVERIFIED as quotations.
CENTOLA = "Centola, Becker, Brackbill & Baronchelli, 'Experimental evidence for tipping points in social convention', Science 360(6393):1116-1119, 8 June 2018, doi:10.1126/science.aas8827. NOT OPENED (2026-11-04: every host tried is outside this session's allowed network); cited from memory, UNVERIFIED as a quotation"
CONSIST = " plans/layer2-abm.md records these sources as opened on 2026-11-03 by the planning session; this entry's encoder could not reopen them on 2026-11-04."
COORD = "[coordination: the payoff is the matching reward of the naming game; a name pays only when the partner uses it, which the layer-2 coordination module reads from the `payoffs` block (A1) and its own `threshold`; at layer 1 the rule is just a permission] "
inst.append({
 "id":"naming-convention",
 "name":"Naming convention (Centola et al. 2018 naming game; layer-2 gate (b) calibration control)",
 "roles":[{"name":"member","gloss":"a participant in the naming game; everyone is a peer (one role, ADR 0006/0011: an institutional sort, not a population)"}],
 "fluents":[
   F("uses_old",1,"m uses the established (old) name for the object"),
   F("uses_new",1,"m uses the new name for the object (the one the committed minority introduces)")],
 "actions":[
   A("use_old",["m"],[E("uses_old",["m"],True),E("uses_new",["m"],False)]),
   A("use_new",["m"],[E("uses_new",["m"],True),E("uses_old",["m"],False)])],
 "rules":[
   R("R1","member","may","(use_old m)","true",None,"superadditive",False,CENTOLA+" (each round a paired participant proposes any name; both are rewarded when the names match, penalised when they do not; no name is required or forbidden). "+COORD),
   R("R2","member","may","(use_new m)","true",None,"superadditive",False,CENTOLA+" (as R1: the alternative name; the committed minority holds it regardless of payoff, which is a model parameter, not a rule). "+COORD)],
 "payoffs":{"use_old":1.0,"use_new":1.0,"coordinated":["use_old","use_new"],"committed_action":"use_new","initial_practice":"use_old"},
 "source_text":"From memory, NOT a verified quotation (the page could not be opened from this session): the experiment ran online groups of 20-30 participants who, in randomly paired rounds, each proposed a name for a pictured object and were paid a small reward when the two names matched and charged a small penalty when they did not; once a group had converged on one name, a committed minority instructed to use a different name was added, and minorities of about 25% of the group overturned the established name while smaller ones (around 20% and below) did not. The abstract (as recalled) reports 'direct empirical demonstration of the existence of a tipping point in the dynamics of changing social conventions' and that minority groups that reached the critical mass 'were consistently able to overturn the established behavior'. "+CENTOLA+CONSIST,
 "expected_properties":{"new_convention_adopted":"reachable"},
 "isomorphic_to":[],
 "not_isomorphic_to":["coverture-household","police-crisis","cps"],
 "minimal_pair_of":None,
 "notes":"Calibration / control entry for layer-2 gate (b) (plans/layer2-abm.md; philengine/abm/gate.py crit_b reads id `naming-convention`, the payoffs-block key `committed_action`, parameter `committed_minority`; the property `new_convention_adopted` was its placeholder reading until engine slice 4, see the drift note). A pure coordination game, not a liberation case: no subject, no care, no sanction, no exit; the only question it serves is whether the coordination module's tipping location emerges from the sweep rather than from a constant. committed_minority: share of agents holding `use_new` regardless of payoff; Centola's observed tipping band ~ 25%: largest failing minority ~21%, smallest succeeding ~25% (UNVERIFIED, from memory; reworded 2026-11-04 per the encoding review finding 9 from 'between 21% and 31%', 31% being the largest minority tested, not the band's edge). Recorded here, not asserted by the model. Payoffs (A1): both actions 1.0, because the coordination module pays only on matching, so the payoff IS the matching reward and the two names are symmetric; the gate sweeps committed_minority, not payoffs. Rules: two `may` with condition true (ADR 0015 A6 strict enabledness: every action needs a may) and no must or must_not (the game has no sanction: a mismatch forgoes the reward, it breaks no rule). Fluents: `uses_old` / `uses_new` are two fluents rather than one, because the ABM's state is role-level and shared (A2 deferred) and `Reference.successor` lets set-true win over set-false, so when members fire both names in one step both atoms are true; the property therefore asks for new-and-not-old, which on the shared state reads 'some member fired use_new and no member fired use_old this step', i.e. the convention has switched. `initial: (uses_old member)` records the established convention at layer 1. The payoffs block also carries the three RESERVED keys the engine's slice-4 coordination module reads (philengine/abm/model.py RESERVED_PAYOFF_KEYS, ASSUMED, added by the engine agent concurrently on 2026-11-04 after the first material-only run here showed the agents bootstrapping practice from a payoff tie by rng and ignoring `initial`): `coordinated: [use_old, use_new]` (both names are assurance-gated: a name pays only when the agent's same-role neighbour share of it meets its threshold), `committed_action: use_new` (what the committed_minority holds whatever it pays), `initial_practice: use_old` (every uncommitted member starts on the old name, so an established convention exists for the minority to tip). These keys are hand inputs, like the numbers (A1); nothing in them names a tipping location. Layer 2 with the coordination module (information, not a dataset verdict; written before the first (b) run): some adjacent pair of sweep points 0.05..0.50 is expected to show an adoption jump > 0.5 (crit_b PASS) and the location is NOT preregistered: the gate's own point is that the dataset records Centola's band and the model does not assert it. DRIFT, recorded not edited (2026-11-04, after the run): the engine's slice-4 crit_b no longer reads `new_convention_adopted` (its review finding 6: a property mean cannot express a population share under shared role state) but the member role's last-step share of `committed_action`; at 30 seeds that share by committed_minority 0.05..0.50 is [0.05, 0.10, 0.15, 0.20, 0.35, 0.54, 0.70, 0.80, 0.90, 0.97]: equal to the committed share through 0.20 (no uncommitted member converts), above it from 0.25 on, so the tipping begins at the 0.20 -> 0.25 boundary, inside Centola's band, but the curve is graded and the max adjacent jump is 0.19, not > 0.5: crit_b FAIL under both coordination configurations. The location was not set by the dataset (the entry carries no threshold); whether the sharpness criterion, the threshold draw U(0, threshold_max) or the 20-agent graph is what grades the curve is an engine question, not a dataset one. `new_convention_adopted` stays the layer-1 property (reachable, as preregistered) and an information line at layer 2. Negative control in spirit: it is listed in CONTROLS (`not_isomorphic_to_control` on the three care+control cluster members, ADR 0007 / ADR 0013) because it must match nothing: PREREGISTERED none@guard+strands against coverture-household, police-crisis and cps (no must, no rival may, no subject). PREREGISTERED (2026-11-04, before any run): new_convention_adopted reachable (one use_new step from the declared initial state); persists / holds_to_k are not claimed and would read fails / violated (use_old is always permitted); no inert rule (both are may); no vacuity flag (no invariant claimed); layer-1 gate unchanged except the three new control pairs reading none. Layer 2, material only (information, no verdict): with equal payoffs, imitation never fires (no neighbour out-earns) and the step-0 bootstrap splits practice by rng, so the property's last-step rate over seeds is expected to be coin-flip-shaped (neither ~0 nor ~1), not a tipping curve; crit_b stays BLOCKED until the coordination module and committed_minority exist. Deviations from the plan sketch: no `coordinated(member)` derived fluent (nothing reads it; the coordination module tags actions by the payoffs block, A1); source not fetched (network), so every figure is marked UNVERIFIED. Sources: "+CENTOLA+"."+CONSIST
})

# ---------------------------------------------------------------- kibbutz-childrens-house (gate d)
# Sources opened 2026-11-03. WIKI_KIB: the nanny (metapelet) "was always a woman's role"; children "lived in the
# children's house, where they had communal sleeping arrangements" and "visited their parents for 2-3 hours a day".
# JTA_BARAM / SCMP_BARAM: Kibbutz Baram, the last holdout, moved its 80 children into their parents' homes in June 1997
# after "a stormy debate"; the first kibbutzim had ended children's houses roughly twenty years earlier, and the
# pressure came "particularly from young mothers". Tiger & Shepher 1975 is cited by the Wikipedia article (pp. 41, 167)
# and its existence / sample (34,040 members) is confirmed by the Kirkus review; its finding on women's work
# assignments was not read directly and stays UNVERIFIED here.
WIKI_KIB = "Wikipedia, 'Kibbutz communal child rearing and collective education' (read 2026-11-03): 'The nanny position was always a woman's role. Teacher positions were both for women and men.'; children 'lived in the children's house, where they had communal sleeping arrangements' and 'visited their parents for 2-3 hours a day'; https://en.wikipedia.org/wiki/Kibbutz_communal_child_rearing_and_collective_education"
JTA_BARAM = "JTA, 'Last kibbutz children's house closes', 1997-06-16: 'The era ended over the weekend, when the 80 children at Kibbutz Baram in the lower Galilee moved into their parents' homes'; Baram 'was the last holdout'; 'After a stormy debate, the decision to do away with the children's houses was made more than a year ago'; https://www.jta.org/archive/last-kibbutz-childrens-house-closes-2"
SCMP_BARAM = "South China Morning Post, 'Kibbutz children go home to parents' (1997): a few of Israel's 230 kibbutzim ended children's houses roughly twenty years earlier and the reform then gained momentum; at Baram the 'pressure, particularly from young mothers' built over two years; https://amp.scmp.com/article/170090/kibbutz-children-go-home-parents"
TIGER = "Tiger & Shepher, Women in the Kibbutz (Harcourt Brace Jovanovich, 1975): women concentrated in child care, education and services despite formal equality. Cited by WIKI_KIB (pp. 41, 167); book and sample (34,040 members) confirmed via Kirkus review https://www.kirkusreviews.com/book-reviews/lionel-joseph-shepher-tiger/women-in-the-kibbutz/ ; the assignment finding itself NOT read directly: UNVERIFIED"
KIB_ROLES = [{"name":"committee","gloss":"the work / education committee that staffs the children's house (the kibbutz general assembly's organ)"},
             {"name":"metapelet","gloss":"the metapelet (nanny / caregiver) assigned to the children's house; a woman"},
             {"name":"male_member","gloss":"a male kibbutz member; a parent who visits, never a children's-house carer"},
             {"name":"child","gloss":"a child of the kibbutz; sleeps in the children's house"}]
KIB_FLUENTS = fl("is_subject","provides_care","female") + [
   DV("can_sanction",["c","x"],"(enabled reprimand c x)"),
   DV("can_exit",["s"],"(enabled sleep_home s)"),
   {"name":"can_assign","arity":2,"gloss":"c holds the power to put x on the children's-house care rota","params":["c","x"],"derived":"(enabled assign c x)"},
   F("member",1,"x is an adult member of the kibbutz (eligible for work assignment)"),
   F("assigned",1,"x is on the children's-house care rota"),
   F("at_home",1,"the child sleeps in the parents' home rather than the children's house")]
KIB_ACTIONS = [
   A("assign",["committee","x"],[E("provides_care",["x","child"],True),E("assigned",["x"],True)]),
   A("release",["committee","x"],[E("provides_care",["x","child"],False),E("assigned",["x"],False)]),
   A("neglect",["x","child"],[E("provides_care",["x","child"],False)]),
   A("visit",["x","child"],[]),
   A("sleep_home",["child"],[E("at_home",["child"],True)]),
   A("reprimand",["committee","x"],[])]
KIB_R2 = R("R2","committee","must_not","(assign committee male_member)","true","R6","tying",True,
   "SANCTIONED NORM encoding a documented PRACTICE, not a written rule (third review 2026-11-03: the sources support a practice, not a committee disability): the nanny 'was always a woman's role' (WIKI_KIB); no kibbutz by-law said so, the rota simply never put a man in the children's house, and "+TIGER+" reports women concentrated in child care as a pattern (the finding is framed there as women's own choice). Encoded as a prohibition the committee answers for (or_else R6, the implicit reprimand), not as a disability; under strict compliance the effect on traces is the same, which is what gate (d) reads. Earlier draft (disability, or_else null) retired by the third review", load_bearing=LB)
KIB_RULES = [
   R("R1","committee","may","(assign committee x)","(member x)",None,"superadditive",False,WIKI_KIB+" (members are assigned to the children's house by the committee; the rule as written is sex-blind: any member). "+DERIVED+"can_assign(committee, x) = assign enabled (R1); R2 is a sanctioned norm, so `enabled` does not read it and compliant traces carry it"),
   KIB_R2,
   R("R3","metapelet","must","(provides_care metapelet child)","(assigned metapelet)","R6","superadditive",False,WIKI_KIB+" (the metapelet runs the children's house). "+STATE+"assign establishes provides_care(x, child); neglect breaks it (sanction R6); release ends the assignment", load_bearing=LB),
   R("R4","child","must_not","(sleep_home child)","true",None,"rival",False,WIKI_KIB+" (communal sleeping: the children lived and slept in the children's house). A disability (or_else null), as every subject-side exit bar since ADR 0013; the draft's or_else R6 is dropped for the same reason as coverture R6. "+DERIVED+"can_exit(child) = sleep_home enabled (R7) and not barred (R4)"),
   R("R5","male_member","may","(visit male_member child)","true",None,"superadditive",False,WIKI_KIB+" (children 'visited their parents for 2-3 hours a day'; the father's relation to the children's house is the visit, not care)"),
   R("R6","committee","may","(reprimand committee x)","true",None,"rival",True,"implicit: the committee / general assembly disciplines a member who neglects the rota (R3's or_else). Guard (assigned x) tried 2026-11-04 and reverted (see the entry notes): with it can_sanction(committee, child) is unreachable and care_and_sanction_same_role flips to holds_to_k (vacuous). "+UNV+". "+DERIVED+"can_sanction(committee, x) = reprimand enabled (R6)"),
   R("R7","child","may","(sleep_home child)","true",None,"rival",True,"implicit: the physical possibility of sleeping at the parents' home is always there; R4 removes it. What the 1970s-1990s reform changed is R4 (dropped kibbutz by kibbutz, last at Baram in 1997: "+JTA_BARAM+"); the reform did not touch R2 ("+SCMP_BARAM+"). "+DERIVED+"can_exit(child) = sleep_home enabled (R7) and not barred (R4)"),
   R("R8","metapelet","may","(neglect metapelet child)","(assigned metapelet)",None,"superadditive",True,"implicit, added 2026-11-04 per ADR 0015 A6 (strict enabledness at layer 2: an action needs a may/must rule) so that the breaker of R3 is an enabled action for the layer-2 ABM: the metapelet can always fail the children's house, and that is the choice R3's or_else R6 answers. Under layer 1 the permissive floor already let the unregulated neglect fire in traces, so no verdict should change; the rule makes neglect regulated, which narrows its firing to the assigned metapelet (the only bearer of R3). Condition mirrors R3: neglect is a breach only while assigned. Tagged superadditive as the care strand's own breach (R3), as companion R10 `may feed` is tagged for the restore. "+UNV)]
KIB_SOURCE = "'Children's lives had three focal points: the children's house, parents' house, and the whole kibbutz.' 'They lived in the children's house, where they had communal sleeping arrangements' and 'visited their parents for 2-3 hours a day.' 'The nanny position was always a woman's role. Teacher positions were both for women and men.' (Wikipedia, 'Kibbutz communal child rearing and collective education', read 2026-11-03.) 'The era ended over the weekend, when the 80 children at Kibbutz Baram in the lower Galilee moved into their parents' homes' (JTA, 1997-06-16); the pressure came 'particularly from young mothers' (SCMP, 1997)."
inst.append({
 "id":"kibbutz-childrens-house",
 "name":"Kibbutz children's house (communal sleeping, metapelet care rota)",
 "roles":KIB_ROLES,"fluents":KIB_FLUENTS,"actions":KIB_ACTIONS,"rules":KIB_RULES,
 "source_text":KIB_SOURCE,
 "expected_properties":{"care_assigned_by_sex":"persists","subject_cannot_exit":"reachable","care_and_sanction_same_role":"violated"},
 "isomorphic_to":[{"id":"coverture-household","level":"guard+strands","sub_signature":["R3~R3 provides_care~provides_care"]}],
 "not_isomorphic_to":["police-crisis","cps"],
 "minimal_pair_of":None,
 "notes":"Gate (d): the historical failure. The explicit rules are sex-blind (R1 may assign any member) and the reform of the 1970s-1990s removed the exit bar on the child (R4), yet care_assigned_by_sex PERSISTS because the implicit sanctioned norm R2 (never a man in the children's house; a documented practice, or_else R6) survives: every strictly compliant trace keeps provides_care in female hands. RE-ENCODED after the third review (2026-11-03): R2 was a disability (or_else null); the sources support a practice, not a committee disability, so it is now must_not + or_else R6. 'implicit' is a human tag the engine reports back; the ablation bites because R1 was written sex-blind (disclosed). PREREGISTERED (2026-11-03, before any run): care_assigned_by_sex persists here; fails in kibbutz-childrens-house-no-implicit, which is this entry minus R2 (differs_on care_assigned_by_sex); subject_cannot_exit reachable (R4 bars sleep_home); care_and_sanction_same_role violated (the committee sanctions, the metapelet cares). Deviations from plans/institutions-batch2.md: R1 is '(assign committee x) when (member x)' rather than '(assign committee metapelet)', because an action instance no may/must rule names is disabled, so the draft's ablation (drop R2 -> assign male_member) only bites if R1 covers the man; R4 is a disability (or_else null) per the ADR 0013 exit convention, so R6 is R3's or_else only and its condition is 'true' (the or_else link enables it on breach); an implicit R7 'may sleep_home' carries can_exit as in every other entry; the draft's release action is kept but the breaker of R3 is neglect (release clears the condition with the state, so it breaks nothing). Pitfalls: (1) female needs arg_roles [metapelet] or the solver invents a female male_member; (2) an encoder that writes R1 as 'may assign metapelet' hides R2 inside R1 and the no-implicit variant collapses into the original; (3) 'persists' is about what the rules permit, not uptake. Rival reading (notes only): regendering of care came from mothers' demands (SCMP), not from the committee; the entry does not encode who drove the reform. PREREGISTERED 2026-11-04 (before any run; ADR 0015 A6: R8 'metapelet may neglect when assigned', implicit, in KIB_RULES so it flows into the no-implicit pair too): expected effect on this entry's three properties is NONE. care_assigned_by_sex persists (neglect can only clear provides_care, never put it in male hands; at layer 1 the unregulated neglect already fired freely under the trace floor, and making it regulated narrows its firing to the assigned metapelet, which removes no trace that bears on the property); subject_cannot_exit reachable (R4/R7 untouched); care_and_sanction_same_role violated (the committee's reprimand power and the metapelet's care are untouched; the violating trace needs assign, not neglect). Minimal pair kibbutz-childrens-house-no-implicit: unchanged (fails / reachable / violated), distance to this entry stays 1 with R2 the one separating rule (R8 is in both). isomorphic_to coverture-household at guard+strands: it already reads NO today (matched 0, distance 9: a pre-existing disagreement with the claim as written, found while baselining, not caused by this change) and is expected to stay NO with matched 0 and distance 9, because coverture has no may-rule tagged superadditive for R8 to match and distance = max(8, 9) - 0 is unchanged; not_isomorphic_to police-crisis / cps stay yes. Gate (d): PASS unchanged (persists vs fails, R2 the one separating rule). check-all: 106/106, no inert rule (R8 is a may). Layer 2 (information only): neglect becomes an available action for the assigned metapelet; the baseline ABM run (2026-11-04, before R8) shows the metapelet with no available action at all. PREREGISTERED 2026-11-04 (before any run; R6 guard, accepted decision of 2026-11-04): R6 'may reprimand' gains the condition (assigned x) (ASSUMED: the committee disciplines only a member on the rota; previously 'true', under which the layer-2 ABM had the committee reprimand random members about half the time). Expected effect on the three expected_properties: NONE. care_assigned_by_sex persists (reprimand has no effects; nothing new puts care in male hands); subject_cannot_exit reachable (R4/R7 untouched); care_and_sanction_same_role violated (can_sanction(committee, x) = (enabled reprimand committee x) now holds only while assigned(x); assigned(metapelet) is in the initial state, so can_sanction(committee, metapelet) is still true in compliant traces while the metapelet provides care, and the property's (= z x) fails exactly as before). The or_else links R2->R6 and R3->R6 are unaffected: under compliance=sanctioned a breach enables the or_else action whatever its condition, and check-all runs strict, where or_else is not read. Minimal pair kibbutz-childrens-house-no-implicit: unchanged (fails / reachable / violated), distance 1 with R2 the separating rule (R6 is in both via KIB_RULES). check-all: 106/106 agreement, no inert rule (R6 is a may); the 'R6: untyped variable(s) [x]' warning stays. Gate: PASS; (d) unchanged (persists vs fails, R2 the one separating rule); (a) 0 inert; (b), (c), (e), (f) untouched (kibbutz is outside the cluster). isomorphic_to coverture-household at guard+strands: stays NO, matched 0, distance 9 (R6's skeleton becomes (may, (role, var), guarded, no or_else, rival); coverture R5 chastise is (may, (var, var), guarded, no or_else, rival): the aim patterns differ, so no new pair); not_isomorphic_to police-crisis / cps stay yes (distances 10 / 11 move by at most 1). Layer 2 (information only; baseline run 2026-11-04 before the guard, 10 seeds x 30 steps, committee adoption split: assign(committee,metapelet) 0.32, reprimand(committee,metapelet) 0.275, reprimand(committee,child) 0.225, reprimand(committee,male_member) 0.18): expected after the guard, reprimand(committee,child) and reprimand(committee,male_member) disappear (never assigned; the committee's R2 breach rate is 0.0 in the baseline) and the committee splits between assign(committee,metapelet) and reprimand(committee,metapelet) (plus 'none' if the material module prefers it); metapelet, male_member and child unchanged. If any verdict flips the guard is reverted, not the expectation. R6 guard tried 2026-11-04 and reverted: care_and_sanction_same_role flipped from violated to holds_to_k (flags vacuous, antecedent-unreachable) in this entry AND in kibbutz-childrens-house-no-implicit (check-all 104/106; gate still PASS). The preregistration above was wrong about which binding carries the verdict: the property quantifies sanction power over the SUBJECT ((is_subject y) and (can_sanction z y) and (provides_care x y) => (= z x)), so the violating trace needs can_sanction(committee, child) = (enabled reprimand committee child), which R6 'true' grants and (assigned child) never does (the child is not a member, so R1 cannot put it on the rota: the antecedent becomes unreachable and the invariant holds vacuously). The guard would have to be '(or (assigned x) (is_subject x))' or the property's reading changed; neither was accepted, so R6 is back to 'true' and the ABM keeps reprimanding random members (committee split with the guard, 10 seeds x 30 steps: assign(committee,metapelet) 0.685, reprimand(committee,metapelet) 0.315, as preregistered for layer 2; without it: 0.32 / 0.275 / child 0.225 / male_member 0.18). Layer-2 reading of R8 at step 0 (2026-11-04): assigned(metapelet) is in the entry's `initial` (_kib_init, alongside provides_care(metapelet, child)), so Reference.initial_split puts it in the fixed set and the ABM's step-0 state carries it; neglect(metapelet, child) is therefore a power at step 0 (verified with Reference.power on the ABM's initial state: available_for('metapelet') = [neglect]); the slice-3 observation that it was not predates R8 reaching institutions.json, and the metapelet's 'none' adoption is a choice (neglect breaches R3, sanctioned by R6), not an absence of power; no rule change. DISAGREEMENT 2026-11-04: iso with coverture-household at guard+strands reads NO (matched 0, distance 9) under the current matcher; claim not edited; cause unexamined (candidate: the matcher needs the same strand tag on R3 and coverture R3 and a shared guard shape). Encoder observation, not a cause finding: rules_iso.rule_skeleton keys the aim by literal-role vs variable positions, and this entry's R3 aim names roles (provides_care metapelet child) while coverture R3 uses bound variables (provides_care w h)."
})
# ---------------------------------------------------------------- kibbutz-childrens-house-no-implicit (minimal pair)
inst.append({
 "id":"kibbutz-childrens-house-no-implicit",
 "name":"Kibbutz children's house without the implicit assignment rule (minimal pair)",
 "roles":KIB_ROLES,"fluents":KIB_FLUENTS,"actions":KIB_ACTIONS,
 "rules":[r for r in KIB_RULES if r["id"] != "R2"],
 "source_text":"Construction: kibbutz-childrens-house with R2 (the implicit 'never a man in the children's house') deleted; nothing historical corresponds to it. The explicit rules are unchanged: R1 lets the committee assign any member.",
 "expected_properties":{"care_assigned_by_sex":"fails","subject_cannot_exit":"reachable","care_and_sanction_same_role":"violated"},
 "isomorphic_to":[],
 "not_isomorphic_to":["kibbutz-childrens-house"],
 "minimal_pair_of":{"id":"kibbutz-childrens-house","rule":"R2","differs_on":"care_assigned_by_sex"},
 "notes":"PREREGISTERED (2026-11-03, before any run): care_assigned_by_sex fails (a compliant trace assigns the male_member, R1, and provides_care(male_member, child) with female false breaks the universal). The same rules minus R2 and nothing else; the gate (d) check compares this verdict with the original's."
})

# ---------------------------------------------------------------- airline-flight (permanent negative control, EXPECTED to match)
# Third review 2026-11-03: a flight's crew must care for passengers aboard, may restrain a disruptive one, and the
# passenger may not leave in flight. Tagged as the reviewer tagged it (care superadditive, restrain rival, exit bar
# disability). PREREGISTERED: it WILL match police-crisis / cps / coverture at guard+strands; the match is structural
# (in-flight custody) and is the expected finding, so this entry is NOT in any `not_isomorphic_to_control`.
AIR = "Reconstruction from the third review's 6-rule sketch (no statute opened): 14 CFR 91.11 / 121.580 (interference with crew; crew may restrain) and flight-attendant duties are named by the reviewer from general knowledge. "+UNV
inst.append({
 "id":"airline-flight",
 "name":"Airline flight (permanent negative control, EXPECTED to match the care+control cluster)",
 "roles":[{"name":"crew","gloss":"cabin crew; serves and may restrain"},{"name":"passenger","gloss":"a passenger aboard; the counterparty"}],
 "fluents":fl("is_subject","provides_care") + [
   DV("can_sanction",["c","p"],"(enabled restrain c p)"),
   DV("can_exit",["p"],"(enabled leave p)"),
   F("aboard",1,"p is aboard a flight in the air"),
   F("disruptive",1,"p is behaving disruptively (exogenous)"),
   F("restrained",1,"p is physically restrained")],
 "actions":[
   A("board",["c","p"],[E("aboard",["p"],True),E("is_subject",["p"],True),E("provides_care",["c","p"],True)]),
   A("attend",["c","p"],[E("provides_care",["c","p"],True)]),
   A("withdraw",["c","p"],[E("provides_care",["c","p"],False)]),
   A("restrain",["c","p"],[E("restrained",["p"],True)]),
   A("leave",["p"],[E("aboard",["p"],False),E("is_subject",["p"],False),E("provides_care",["crew","p"],False)]),
   A("complain",["p"],[])],
 "rules":[
   R("R1","crew","may","(board c p)","(not (aboard p))",None,"tying",False,AIR,var_roles={"c":"crew","p":"passenger"}),
   R("R2","crew","must","(provides_care c p)","(aboard p)",None,"superadditive",False,AIR+" (crew must care for passengers aboard). "+STATE+"board establishes provides_care; attend restores it, withdraw breaks it",load_bearing=LB,var_roles={"c":"crew","p":"passenger"}),
   R("R3","crew","may","(restrain c p)","(and (aboard p) (disruptive p))",None,"rival",False,AIR+" (crew may restrain a disruptive passenger)",var_roles={"c":"crew","p":"passenger"}),
   R("R4","passenger","must_not","(leave p)","(aboard p)",None,"rival",False,AIR+" (a passenger cannot leave in flight)."+EXIT+" "+DERIVED+"can_exit(p) = leave enabled (R5), which this disability makes false aboard"),
   R("R5","passenger","may","(leave p)","true",None,"rival",True,"implicit: the physical possibility of leaving is always there; R4 removes it in flight. "+DERIVED+"can_exit(p) = leave enabled (R5) and not barred (R4)"),
   R("R6","passenger","may","(complain p)","true",None,"tying",False,AIR+" (a passenger may complain)")],
 "source_text":"Reconstruction, not a quotation: a flight's crew must care for passengers aboard, may restrain a disruptive passenger, and a passenger must not leave in flight (may leave on the ground); the passenger may complain. Supplied by the third review (2026-11-03) as a structural negative control for the care+control match.",
 "expected_properties":{"subject_cannot_exit":"reachable","dependent_cannot_exit":"reachable","care_and_sanction_same_role":"holds_to_k"},
 "isomorphic_to":[],
 "not_isomorphic_to":[],
 "expected_control_match": True,
 "minimal_pair_of":None,
 "notes":"EXPECTED-MATCH control (`expected_control_match: true`; third review 2026-11-03). PREREGISTERED before any run: airline-flight matches police-crisis, cps and coverture-household at guard+strands (care R2 superadditive ~ care, R3 rival ~ chastise/detain/remove, R4 exit bar ~ exit bar). The match is structural: in-flight custody has the same care + restraint + exit-bar form, so it is a finding about the form, not a failure of the encoding. Retagging R2 superadditive -> tying removes every match: the strand tags are load-bearing and the tags are human inputs. Why it is not in `not_isomorphic_to_control`: gate (b) fails on any match, and the gate has no expected-match mode (philosophy-engine is not edited here); `rules_gate` still lists it as an ordinary dataset entry. Expectations copied from police-crisis minus no_standing and are unverified until check-all. 6 rules (the review's list), not 10."
})

# ---------------------------------------------------------------- MWPA backtest chain (plans/backtest-mwpa.md, 2026-11-03)
# A path of minimal pairs out of coverture-household, one plan delta per step; every entry shares coverture's roles,
# fluents and actions and differs from the previous one only by the rules named in its minimal_pair_of. The plan's
# predicted failure modes are entries of their own (DT (Capture per ADR 0016): the 1839-50 creditor-exemption act, which is the chain's first
# historical step; BL (backlash; filed Erosion by ADR 0016 on 2026-11-03, reverted by its council pass 2026-11-04): courts narrowing the property act). PREREGISTERED verdicts are in each entry's expected_properties
# and in the plan's "Layer-1 run" section, written before the first run; they are not edited to match.
GLT = "Geddes, Lueck & Tennyson 2007 (draft), Table 1 dates of property / earnings acts; https://isnie-archive.sioe.org/assets/files/papers2007/geddes.pdf [F, via plans/backtest-mwpa.md]"
KHAN = "Khan 1996, Married Women's Property Laws and Female Commercial Activity, Table 1 (sole-trader dates; the 1839-50 wave as debt relief); https://www.laits.utexas.edu/~mbs31415/Khan_MarriedWomenPropertyRights.pdf [F, via plans/backtest-mwpa.md]"
CHUSED84 = "Chused 1984 (https://core.ac.uk/download/230496986.pdf [F, via plans/backtest-mwpa.md]): the 1839-50 acts 'generally contained nothing more than statements exempting married women's property from the debts of husbands'; courts 'narrowly construing' the acts to keep husbands' control during marriage (citing Chused 1983 at 1400; Chused 1983 itself [R], PDF refused: UNVERIFIED)"
NY1848 = "New York Married Women's Property Act 1848 (the statute text itself not opened: [R] UNVERIFIED; dates from "+GLT+")"
MWPA_FLUENTS_EXTRA = [
   F("transferred",2,"h has conveyed property of his to w"),
   F("narrowed",1,"a court has construed the property act narrowly as to w (keeps the husband's control during marriage)"),
   {"name":"can_attach","arity":2,"gloss":"creditor c holds the power to attach (levy on) property in w's hands for the husband's debts","params":["c","w"],"derived":"(enabled attach c w)"}]
MWPA_ACTIONS_EXTRA = [
   A("attach",["c","w"],[]),
   A("transfer_to_wife",["h","w"],[E("acquired_property",["w"],True),E("transferred",["h","w"],True)])]
COV = inst[0]; assert COV["id"] == "coverture-household"
def _mwpa(id, name, prev, drop, add, expected, pair, source_text, notes, roles_extra=(), actions_extra=(), fluents_extra=()):
    e = copy.deepcopy(prev)
    e["id"] = id; e["name"] = name
    e["roles"] = e["roles"] + list(roles_extra)
    e["fluents"] = e["fluents"] + list(fluents_extra)
    e["actions"] = e["actions"] + list(actions_extra)
    e["rules"] = [r for r in e["rules"] if r["id"] not in drop] + list(add)
    e["source_text"] = source_text
    e["expected_properties"] = expected
    e["isomorphic_to"] = []; e["not_isomorphic_to"] = []; e["not_isomorphic_to_control"] = []
    e["minimal_pair_of"] = pair
    e["notes"] = notes
    e.pop("initial", None); e.pop("initial_free", None); e.pop("defaults", None)
    return e
MWPA_BASE_EXP = {"subject_cannot_exit":"reachable","care_and_sanction_same_role":"holds_to_k"}
# Step DT (Capture per ADR 0016) (1839-50 debtor-relief wave): coverture + a creditor who may levy on the household's property (baseline,
# implicit) but must not reach the wife's acquired property (the exemption), + the husband may convey to his wife.
# R1 (husband manages) is KEPT: that is the dark twin (the plan: 'creditor must_not attach wife_property, husband's
# management kept'); the task's shield reading (husband conveys to wife to put assets beyond creditors) is R12.
EXEMPT = _mwpa("mwpa-creditor-exemption","Married women's property, 1839-50 form: creditor exemption only (dark twin; Capture per ADR 0016)",COV,
  drop=(), add=[
   R("R10","creditor","may","(attach c w)","(married h w)",None,"rival",True,"implicit baseline: a husband's creditors reach the property the husband holds, which under R1 includes his wife's. "+UNV+". "+DERIVED+"can_attach(c, w) = attach enabled (R10) and not barred (R11)", var_roles={"c":"creditor","w":"wife","h":"husband"}),
   R("R11","creditor","must_not","(attach c w)","(and (married h w) (acquired_property w))",None,"tying",False,CHUSED84+"; "+KHAN+" (Mississippi 1839 shielded property from husbands' creditors; Khan excludes it as debt relief). A disability (or_else null): the exemption removes the creditor's power, no sanction is involved", var_roles={"c":"creditor","w":"wife","h":"husband"}),
   R("R12","husband","may","(transfer_to_wife h w)","(married h w)",None,"tying",True,"implicit: the transfer vehicle the exemption invites (conveyance to the wife, in practice through a trustee); "+CHUSED84+". "+UNV+" as a rule of the 1839-50 acts; Blackstone's bar on grants between spouses is read as lifted by the exemption acts for property so conveyed", var_roles={"h":"husband","w":"wife"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"holds_to_k","financial_dependence_unpropertied":"holds_to_k","cannot_contract":"holds_to_k",
            "no_standing":"reachable","double_burden":"unreachable_open","creditor_shield":"reachable","backlash":"unreachable_open"}),
  pair={"id":"coverture-household","rule":"R10,R11,R12","differs_on":"creditor_shield"},
  source_text="The 1839-1850 acts 'generally contained nothing more than statements exempting married women's property from the debts of husbands', passed after the panics (Chused 1984, citing Chused 1983). Mississippi's 1839 act shielded (slave) property from husbands' creditors; Khan 1996 excludes it as debt relief. Both via plans/backtest-mwpa.md.",
  notes="DARK TWIN (DT; relabelled Capture by ADR 0016, 2026-11-03, verdicts unchanged) of the property act, encoded as the plan says: the creditor may not reach the wife's acquired property (R11) but the husband's management (R1) stands, so nothing on the wife's side changes. PREREGISTERED (2026-11-03, before any run): financial_dependence and financial_dependence_unpropertied holds_to_k (unchanged from coverture); creditor_shield REACHABLE (marry, transfer_to_wife: the husband's property sits in his wife's name, under his management, beyond his creditors); no_standing reachable, cannot_contract holds, double_burden open, backlash open (no court here). Distance 3 from coverture (R10 baseline, R11 exemption, R12 conveyance): not a one-rule pair; R10 exists only so that can_attach is a granted power the exemption removes rather than a constant. Displacement: the plan names no burden moving to another role in this wave; none is encoded.",
  roles_extra=[{"name":"creditor","gloss":"a creditor of the husband"}], actions_extra=MWPA_ACTIONS_EXTRA, fluents_extra=MWPA_FLUENTS_EXTRA)
inst.append(EXEMPT)
PROP = _mwpa("mwpa-property","Married women's property act: separate property (coverture minus R1, plus may hold_property)",EXEMPT,
  drop=("R1",), add=[
   R("R13","wife","may","(hold_property w)","(and (married h w) (acquired_property w) (not (narrowed w)))",None,"tying",False,NY1848+"; "+GLT+" (property acts: the wife holds and controls property acquired by gift or inheritance as if a feme sole). Conditioned on (not narrowed): a narrow construction (BL entry, R17) re-disables the power. "+DERIVED+"controls_own_property(w) = hold_property enabled (R13)", var_roles={"w":"wife","h":"husband"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"violated","financial_dependence_unpropertied":"holds_to_k","cannot_contract":"holds_to_k",
            "no_standing":"reachable","double_burden":"unreachable_open","creditor_shield":"unreachable_open","backlash":"unreachable_open"}),
  pair={"id":"mwpa-creditor-exemption","rule":"R1->R13","differs_on":"financial_dependence"},
  source_text="Property acts (GLT Table 1: MA 1845, NY 1848, PA 1848, ...): a married woman holds property acquired by gift or inheritance in her own right, beyond her husband's control and his creditors. Statute texts not opened ([R]); dates and the gloss via plans/backtest-mwpa.md.",
  notes="Plan delta `property`: delete R1 (husband may control_property), add wife may hold_property (R13); the creditor exemption (R11) and conveyance (R12) carry over from the 1839-50 form. PREREGISTERED (2026-11-03, before any run): financial_dependence VIOLATED (a propertied wife now controls her own property), financial_dependence_unpropertied holds_to_k (a wife without acquired property is as dependent as before: the flip is 'for propertied wives only'), can_exit unchanged (subject_cannot_exit reachable), has_standing unchanged (no_standing reachable), cannot_contract holds; creditor_shield OPEN (with R1 gone the husband no longer manages what he conveys: the dark twin is extinguished by the real act), backlash open, double_burden open.")
inst.append(PROP)
EARN = _mwpa("mwpa-earnings","Married women's earnings act (property act plus may keep_earnings)",PROP,
  drop=(), add=[
   R("R14","wife","may","(keep_earnings w)","(and (married h w) (earns w))",None,"tying",False,GLT+" (earnings acts: NY 1860, MA 1846/1874, PA 1872, ...: a married woman's wages are her separate property). Statute texts not opened ([R]). "+DERIVED+"owns_earnings(w) = keep_earnings enabled (R14)", var_roles={"w":"wife","h":"husband"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"violated","financial_dependence_unpropertied":"violated","cannot_contract":"holds_to_k",
            "no_standing":"reachable","double_burden":"reachable","creditor_shield":"unreachable_open","backlash":"unreachable_open"}),
  pair={"id":"mwpa-property","rule":"R14","differs_on":"financial_dependence_unpropertied"},
  source_text="Earnings acts (GLT Table 1): a married woman's earnings from her own labour are her separate property. Statute texts not opened ([R]); via plans/backtest-mwpa.md.",
  notes="Plan delta `earnings`: add wife may keep_earnings (R14). PREREGISTERED (2026-11-03, before any run): financial_dependence_unpropertied VIOLATED (a wage-earning wife without property is no longer dependent); DISPLACEMENT (plan's DI): the implicit care obligation R3 is unchanged, so double_burden (a wife who owns her wages and still must keep house) becomes REACHABLE here and was open before; no burden moves to another role (the plan names none). cannot_contract holds, no_standing reachable, exit unchanged.")
inst.append(EARN)
SOLE = _mwpa("mwpa-sole-trader","Sole-trader act (earnings act minus R7, plus may contract)",EARN,
  drop=("R7",), add=[
   R("R15","wife","may","(contract w)","true",None,"tying",False,KHAN+" (sole-trader provisions: a married woman may carry on trade and contract in her own name; ME 1844, MA 1860, NY 1860, ...). Statute texts not opened ([R]). "+DERIVED+"can_contract(w) = contract enabled (R15), no longer barred (R7 deleted)", var_roles={"w":"wife"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"violated","financial_dependence_unpropertied":"violated","cannot_contract":"violated",
            "no_standing":"reachable","double_burden":"reachable","creditor_shield":"unreachable_open","backlash":"unreachable_open"}),
  pair={"id":"mwpa-earnings","rule":"R7->R15","differs_on":"cannot_contract"},
  source_text="Sole-trader acts (Khan 1996 Table 1): a married woman may trade and contract in her own name. Statute texts not opened ([R]); via plans/backtest-mwpa.md.",
  notes="Plan delta `sole-trader`: delete the R7 disability on contract; because a power is what the rules grant (ADR 0013), a may contract (R15) replaces it (one replacement, distance 1). PREREGISTERED (2026-11-03, before any run): cannot_contract VIOLATED; can_exit still false (R6 stands: subject_cannot_exit reachable); no_standing still reachable (R4 stands).")
inst.append(SOLE)
SUIT = _mwpa("mwpa-suit","Suit act (sole-trader act minus R4, plus may sue while married)",SOLE,
  drop=("R4",), add=[
   R("R16","wife","may","(sue w)","(married h w)",None,"tying",False,GLT+" (acts giving a married woman the right to sue and be sued in her own name; dates follow the property/earnings acts, e.g. NY 1860). Statute texts not opened ([R]). "+DERIVED+"has_standing(w) = sue enabled: R9 (feme sole) or R16 (married), R4 deleted", var_roles={"w":"wife","h":"husband"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"violated","financial_dependence_unpropertied":"violated","cannot_contract":"violated",
            "no_standing":"unreachable_open","double_burden":"reachable","creditor_shield":"unreachable_open","backlash":"unreachable_open"}),
  pair={"id":"mwpa-sole-trader","rule":"R4->R16","differs_on":"no_standing"},
  source_text="Suit provisions: a married woman may sue and be sued in her own name. Statute texts not opened ([R]); via plans/backtest-mwpa.md.",
  notes="Plan delta `suit`: delete R4; R9 was conditioned on (not married), so a may sue while married (R16) is added (one replacement, distance 1) and has_standing reads R9 or R16. PREREGISTERED (2026-11-03, before any run): no_standing UNREACHABLE (open) = has_standing flips true; subject_cannot_exit still REACHABLE (R6 stands: exit needs divorce reform, not encoded): the engine should say standing before exit.")
inst.append(SUIT)
NARROW = _mwpa("mwpa-property-narrowed","Property act under narrow construction (backlash; filed Erosion by ADR 0016 on 2026-11-03, reverted by its council pass 2026-11-04: court reinstates the husband's control)",PROP,
  drop=(), add=[
   R("R17","court","may","(construe_narrowly court w)","(and (married h w) (acquired_property w))",None,"rival",False,CHUSED84+" (courts narrowly construed the acts so as to keep husbands' control during marriage). The narrowing is a one-way act: nothing in the entry un-narrows", var_roles={"w":"wife","h":"husband"}),
   R("R18","husband","may","(control_property h w)","(and (married h w) (narrowed w))",None,"tying",False,"R1 reinstated under narrow construction (the plan's BL encoding): "+CHUSED84+". "+DERIVED+"controls_property(h, w) = control_property enabled (R18)", var_roles={"h":"husband","w":"wife"})],
  expected=dict(MWPA_BASE_EXP, **{"financial_dependence":"violated","financial_dependence_unpropertied":"holds_to_k","cannot_contract":"holds_to_k",
            "no_standing":"reachable","double_burden":"unreachable_open","creditor_shield":"reachable","backlash":"reachable"}),
  pair={"id":"mwpa-property","rule":"R17,R18","differs_on":"backlash"},
  source_text="Courts 'narrowly construing' the married women's property acts to keep husbands' control during marriage (Chused 1984 citing Chused 1983 at 1400; the 1983 article [R] not opened). Via plans/backtest-mwpa.md.",
  notes="BACKLASH (BL) entry (backlash; filed Erosion by ADR 0016 on 2026-11-03, reverted by its council pass 2026-11-04; verdicts unchanged; see docs/reviews/2026-11-04-adr0016-council.md): mwpa-property plus a court that may construe the act narrowly (R17, sets narrowed(w)), which re-disables the wife's R13 power (its condition carries (not narrowed)) and reinstates R1 as R18 under narrowed. PREREGISTERED (2026-11-03, before any run): backlash REACHABLE (marry, construe_narrowly: the husband controls again, the wife does not); financial_dependence still VIOLATED (the court may but need not narrow, and before it does the wife holds); creditor_shield REACHABLE again (marry, transfer_to_wife, construe_narrowly: with his management reinstated the conveyance is a shield once more); everything else as mwpa-property. Distance 2 from mwpa-property (the narrowing power and the reinstated R1 are two rules). Not a chain step: a branch off mwpa-property.",
  roles_extra=[{"name":"court","gloss":"a court construing the act"}],
  actions_extra=[A("construe_narrowly",["court","w"],[E("narrowed",["w"],True)])])
inst.append(NARROW)
_mwpa_roles = {"is_subject":["wife"],"provides_care":None,"female":["wife"],"married":["husband","wife"],"acquired_property":["wife"],"earns":["wife"],
               "transferred":["husband","wife"],"narrowed":["wife"],"can_attach":["creditor","wife"],"controls_property":["husband","wife"],
               "controls_own_property":["wife"],"owns_earnings":["wife"],"can_contract":["wife"],"can_sanction":["husband","wife"],"can_exit":["wife"],"has_standing":["wife"]}
_mwpa_roles = {k:v for k,v in _mwpa_roles.items() if v}
MWPA_IDS = ["mwpa-creditor-exemption","mwpa-property","mwpa-earnings","mwpa-sole-trader","mwpa-suit","mwpa-property-narrowed"]

# ---------------------------------------------------------------- footbinding (layer-2 gate (a); plans/layer2-abm.md)
# Encoded 2026-11-04 for ABM gate test (a) (philengine/abm/gate.py crit_a: institution id `footbinding`, property
# `binding_practised` true while the practice is in force, pledge actions named `<action>_pledge` for a declared
# `<action>`, ADR 0015 A3). SOURCES: the session's network allowed no page fetch (semanticscholar, jstor, wikipedia,
# cambridge.org, the cognitionandculture.net PDF mirror all refused), so every source below was read as a web-search
# snippet, never as the page: Mackie's ABSTRACT was returned verbatim by the search index ([F] for the abstract's
# sentences, [R] for anything in the body); the pledge wording and the societies' dates come from Wikipedia snippets
# ('Tian Zu Hui', 'Heavenly Foot Society', 'Foot Emancipation Society') and are [R]; Brown et al. 2012 is its abstract
# only ([R]). Rules reconstructed beyond those snippets are UNVERIFIED.
MACKIE = ("Mackie, 'Ending Footbinding and Infibulation: A Convention Account', ASR 61(6):999-1017 (1996), abstract "
  "(read 2026-11-04 as a search-index snippet, the article itself not opened: https://www.jstor.org/stable/2096305 "
  "paywalled, PDF mirrors unreachable from this session): 'Female footbinding in China lasted for 1,000 years but ended "
  "in a single generation. I show that each practice is a self-enforcing convention, in Schelling's (1960) sense, "
  "maintained by interdependent expectations on the marriage market'; 'A Schelling coordination diagram explains how the "
  "three methods of the Chinese campaign to abolish footbinding succeeded in bringing it to a quick end'; 'The convention "
  "hypothesis predicts that promotion of such pledge associations would help bring female genital mutilation to an end' "
  "[F for these sentences; body [R]]")
PLEDGE_SRC = ("Anti-footbinding pledge associations: Heavenly Foot Society (Xiamen, 1874, MacGowan) and the Tian Zu Hui / "
  "Natural Foot Society (Shanghai, 1895, Alicia Little; Chinese reformers' societies from 1897, claimed membership "
  "~300,000): members pledged not to bind their daughters' feet and not to let their sons marry women with bound feet "
  "(Wikipedia 'Tian Zu Hui', 'Heavenly Foot Society', 'Foot Emancipation Society', read 2026-11-04 as search snippets "
  "only, pages not opened: [R]; Mackie 1996 names the same two-part pledge for the FGC analogue, abstract [F])")
BROWN = ("Brown, Bossen, Gates & Satterthwaite-Phillips, 'Marriage Mobility and Footbinding in Pre-1949 Rural China', "
  "J. Asian Studies 71(4):1035-1067 (2012), abstract only (search snippet, 2026-11-04, [R]): in a sample of 7,314 rural "
  "women footbinding did not guarantee a better marriage (two-thirds did not marry up); the marriage-market reading is "
  "Mackie's, and this entry encodes it as the convention, not as a claim that binding bought mobility")
FB_UNV = "UNVERIFIED (reconstructed from the convention account; no primary text opened)"
ANALOGY = " Strand tag by analogy with the house exit pattern, not from the source (encoding review 2026-11-04 finding 6)."
FB_ROLES = [{"name":"family","gloss":"the household deciding for a daughter (Mackie's 'parents' who bind, or pledge not to); the institutional sort, not a demographic (ADR 0011)"},
            {"name":"daughter","gloss":"the subject: the girl whose feet are bound or left unbound; bound in childhood, so she decides nothing"},
            {"name":"suitor","gloss":"the family of a prospective groom: the marriage-market counterparty whose expectations hold the convention"}]
FB_FLUENTS = fl("is_subject") + [
   DV("can_exit",["d"],"(enabled refuse_binding d)"),
   F("bound",1,"d's feet are bound (the practice is in force for the current cohort)"),
   F("pledged",1,"x has joined a pledge association: a family's daughters are not bound (leave_unbound_pledge), a suitor's sons marry only unbound women (accept_match_pledge); untyped union slot family|suitor"),
   F("married",1,"d has been married off"),
   {"name":"marriageable","arity":2,"gloss":"f can marry off d on the marriage market (bound, or unbound inside a pledge association)","params":["f","d"],"derived":"(enabled marry_off f d)"}]
FB_ACTIONS = [
   A("bind",["family","daughter"],[E("bound",["daughter"],True)]),
   A("leave_unbound",["family","daughter"],[E("bound",["daughter"],False)]),
   A("leave_unbound_pledge",["family","daughter"],[E("pledged",["family"],True)]),
   A("accept_match_pledge",["suitor","daughter"],[E("pledged",["suitor"],True)]),
   A("marry_off",["family","daughter"],[E("married",["daughter"],True)]),
   A("reject_match",["suitor","daughter"],[]),
   A("accept_match",["suitor","daughter"],[E("married",["daughter"],True)]),
   A("refuse_binding",["daughter"],[])]
FB_R3 = R("R3","family","must_not","(leave_unbound family daughter)","(is_subject daughter)","R5","tying",True,
   "SANCTIONED NORM (implicit; a convention, not a written rule): a family that leaves a daughter unbound loses her on the marriage market: "+MACKIE+". or_else R5 (the suitor's rejection) is the market sanction; the norm is stated unconditionally because it is the wider society's expectation, and it is the SANCTION (R5) that a pledge association lifts, not the norm. Tying: binding is tied to marriage, which is Mackie's whole point", load_bearing=False)
FB_R4 = R("R4","family","may","(leave_unbound_pledge family daughter)","(is_subject daughter)",None,"superadditive",False,
   "the anti-footbinding pledge (ADR 0015 A3 stand-in: `leave_unbound_pledge` is the pledge for `leave_unbound`): "+PLEDGE_SRC+". Effect pledged(family). The son half of the pledge (no bound bride) is R10 accept_match_pledge (suitor), read by R5/R6 as (pledged suitor); until the encoding review of 2026-11-04 (finding 2) it was folded into R5/R6's (pledged family) condition, which mis-attributed the sons' pledge to the daughter's family. The association's own marriage pool is what R6 reads. Superadditive: the pledge pays only in numbers (Mackie: the pledge associations' 'critical mass')")
FB_R10 = R("R10","suitor","may","(accept_match_pledge suitor daughter)","(is_subject daughter)",None,"superadditive",True,
   "the son half of the anti-footbinding pledge (ADR 0015 A3 stand-in: `accept_match_pledge` is the pledge for `accept_match`, i.e. the suitor family commits to marry its sons to unbound women): "+PLEDGE_SRC+". Effect pledged(suitor), read by R5 (lifts the rejection) and R6 (accepts the unbound bride). Added 2026-11-04 after the encoding review (finding 2: Mackie's pool is made by pledged SUITOR families). implicit: the rule is reconstructed, no text says a suitor 'may' pledge. Superadditive like R4. "+FB_UNV)
FB_RULES = [
   R("R1","family","may","(bind family daughter)","(is_subject daughter)",None,"tying",False,MACKIE+" (the practice; each step is a cohort decision, so the rule stays enabled while a subject exists). "+FB_UNV+" as a rule: no text says a family 'may' bind, the convention presupposes it"),
   R("R2","family","may","(leave_unbound family daughter)","(is_subject daughter)",None,"tying",True,"implicit: leaving a daughter unbound is always physically open to the family; R3 is what sanctions it. Per ADR 0015 A6 every action an agent may take needs a may rule. "+FB_UNV),
   FB_R3,
   FB_R4,
   FB_R10,
   R("R5","suitor","may","(reject_match suitor daughter)","(and (is_subject daughter) (not (bound daughter)) (not (pledged family)) (not (pledged suitor)))",None,"rival",True,"implicit: the marriage market refuses an unbound bride (R3's or_else), 'maintained by interdependent expectations on the marriage market' ("+MACKIE+"); NOT enabled once the family or the suitor has pledged, because pledged families' sons marry only unbound women ("+PLEDGE_SRC+"; (pledged suitor) added 2026-11-04, encoding review finding 2): that lapse of the sanction is the mechanism. Rival: a match refused here is a match made elsewhere."+ANALOGY+" "+FB_UNV+" as a rule"),
   R("R6","suitor","may","(accept_match suitor daughter)","(and (is_subject daughter) (or (bound daughter) (pledged family) (pledged suitor)))",None,"tying",False,"the convention from the groom's side: a bound daughter is acceptable; an unbound one only inside the pledge association, on either side's pledge ("+MACKIE+"; "+PLEDGE_SRC+"; (pledged suitor) added 2026-11-04, encoding review finding 2). "+FB_UNV+" as a rule"),
   R("R7","family","may","(marry_off family daughter)","(and (is_subject daughter) (or (bound daughter) (pledged family)))",None,"tying",False,"the marriage condition: "+MACKIE+" ('interdependent expectations on the marriage market'); "+BROWN+" (the data qualify mobility, not marriageability as encoded). "+DERIVED+"marriageable(f, d) = marry_off enabled (R7)"),
   R("R8","daughter","may","(refuse_binding daughter)","true",None,"rival",True,"implicit: the physical possibility of refusal is always there; R9 removes it."+ANALOGY+" "+DERIVED+"can_exit(d) = refuse_binding enabled (R8) and not barred (R9)"),
   R("R9","daughter","must_not","(refuse_binding daughter)","(is_subject daughter)",None,"rival",True,"binding is done to a young girl by her family: she has no say. A disability (or_else null), the subject-side exit bar per ADR 0013."+EXIT+ANALOGY+" "+FB_UNV+" (age at binding and the mother's role are general knowledge, no text opened; implicit set True 2026-11-04, encoding review finding 6: an UNVERIFIED rule with no text opened is implicit)")]
FB_SOURCE = ("'Female footbinding in China lasted for 1,000 years but ended in a single generation. I show that each practice is a "
  "self-enforcing convention, in Schelling's (1960) sense, maintained by interdependent expectations on the marriage market.' "
  "'A Schelling coordination diagram explains how the three methods of the Chinese campaign to abolish footbinding succeeded in "
  "bringing it to a quick end.' 'The convention hypothesis predicts that promotion of such pledge associations would help bring "
  "female genital mutilation to an end.' (Mackie 1996, abstract, via a search-index snippet 2026-11-04; the article was not "
  "opened.) Pledge associations: members pledged not to bind their daughters' feet and not to let their sons marry women with "
  "bound feet (Wikipedia 'Tian Zu Hui' / 'Heavenly Foot Society', snippets, [R])."+CONSIST)
FB_PREREG = ("PREREGISTERED (2026-11-04, before any run; layer 1 under init declared, strict compliance, step one): "
  "binding_practised PERSISTS in footbinding AND in footbinding-no-pledge (bound(daughter) is initial; the only action that "
  "clears it, leave_unbound, is forbidden by the sanctioned norm R3, which strict compliance never breaches; the pledge R4 "
  "changes nothing at layer 1 because the norm R3 is unconditional and only the sanction R5 reads pledged). "
  "marriage_requires_binding HOLDS_TO_K in both (R7 is the only marry_off rule and its condition is bound-or-pledged; "
  "non-vacuous because marriageable(family, daughter) is true at t=0). subject_cannot_exit and dependent_cannot_exit REACHABLE "
  "in both (t=0: is_subject(daughter) and R9 bars refuse_binding). The pair's layer-1 verdicts are IDENTICAL "
  "(minimal_pair_of.differs_on is null on purpose: the pair differs only at layer 2). Expected warnings: can_sanction, "
  "provides_care, has_standing, can_claim_for undeclared (no care or standing here); care_and_sanction_same_role is not "
  "expected (it would be vacuous: no provides_care). Isomorphism: not_isomorphic_to the care+control cluster (no carer, no "
  "sanctioner over a cared-for subject; the sanction here is a counterparty's refusal); isomorphic_to nothing (no entry has "
  "the convention shape). Information only, not an expectation: under --compliance sanctioned binding_practised should FAIL in "
  "both (leave_unbound may fire and pay the sanction).")
FB_NOTES_COORD = (" LAYER 2 (for the engine's coordination module, which is a stub at writing): the actions the module should "
  "treat as `coordinated` are bind and leave_unbound (a family's choice pays only when enough neighbouring families choose the "
  "same, Mackie's marriage-market assurance game); the pledge is leave_unbound_pledge (A3 naming convention, counts as "
  "adoption of leave_unbound for neighbours' thresholds). philengine has no action tag for this yet (ActionDecl has no `tags`), "
  "so the entry carries an ASSUMED extra field `coordinated: [bind, leave_unbound]` that pydantic ignores. Two things the "
  "engine agent should know: (1) state is role-level (A2 deferred), so `pledged(family)` flips for every family when one agent "
  "pledges and `Reference.successor` lets set-true beat set-false, so bound(daughter) stays true while any family still binds: "
  "collapse of binding_practised needs every family to leave unbound in one step; the gate's collapse reading should probably "
  "use the adoption share of leave_unbound instead, or the module should read pledges per agent; (2) `payoffs` sets bind and "
  "leave_unbound both to 1.0 (the A1 default made explicit) so the gate can sweep them; the sanction R5 is what the material "
  "run prices.")
FB_PREREG2 = (" PREREGISTERED (2026-11-04, encoding review finding 2, written and committed before the first run with the suitor "
  "pledge): adding accept_match_pledge(suitor, daughter) [effect pledged(suitor)] with rule R10 suitor may accept_match_pledge, "
  "and reading (pledged suitor) in R5 (and-not) and R6 (or), changes NO layer-1 verdict in footbinding or footbinding-no-pledge: "
  "binding_practised persists, marriage_requires_binding holds_to_k, subject_cannot_exit and dependent_cannot_exit reachable "
  "in both; the new pledge only lifts the sanction R5 (and widens R6), R3 is unconditional, R7 is untouched, and pledged is a "
  "fluent per role (footbinding-no-pledge strips BOTH pledge actions and both pledge rules R4 and R10, so nothing sets "
  "pledged(suitor) there). Iso: still none at every level against the care+control cluster; isomorphic_to nothing. Expected "
  "warnings unchanged (can_sanction, provides_care, has_standing, can_claim_for undeclared). Layer 2 (information, not an "
  "expectation): pledged(suitor) is role-level too (A2), so one suitor's pledge lifts R5 for every suitor, the same "
  "coarseness as pledged(family): the A2 caveat now applies on both sides; gate (a)'s _has_pledges reading is unchanged "
  "(true via either pledge) and ablate_pledges strips both. If any verdict flips, the drift is recorded here and the "
  "expectations are not edited.")
FB_DRIFT3 = (" Drift 2026-11-04 (encoding review finding 3): marriage_requires_binding is by construction (marriageable is "
  "derived from R7's enabledness and R7's condition is bound-or-pledged, so the property restates the rule); kept in "
  "expected_properties for the record, not evidence; the property carries by_construction: true, which the engine ignores.")
FB_COHORT = (" Layer 1 has one cohort (encoding review 2026-11-04 finding 4): one daughter, bound at t=0, and `married` never "
  "clears, so no trace shows a per-cohort binding decision before the market; a `new_cohort` action clearing bound/married "
  "is deferred to the author.")
FB_RESULT2 = (" RESULT (2026-11-04, after the run, commit b6f48aa preceding it): no drift. check-all 115/115 with all four "
  "verdicts as preregistered in both entries; `phil rules gate` PASS; pytest 15 passed; no warning printed for either entry "
  "(none was printed before the change either). ABM information, `--seeds 5 --steps 60 --modules material,coordination`: "
  "bound 1.0 in every seed (persistence), pledged 0.667 over seeds, i.e. true on the family and the suitor role tuple and "
  "not the daughter's: the A2 caveat on both sides, as the preregistration said; breach, sanction and unavoidable rates 0.")
inst.append({
 "id":"footbinding",
 "name":"Footbinding as a marriage-market convention (Mackie 1996), with pledge associations",
 "roles":FB_ROLES,"fluents":FB_FLUENTS,"actions":FB_ACTIONS,"rules":FB_RULES,
 "source_text":FB_SOURCE,
 "expected_properties":{"binding_practised":"persists","marriage_requires_binding":"holds_to_k",
                        "subject_cannot_exit":"reachable","dependent_cannot_exit":"reachable"},
 "isomorphic_to":[],
 "not_isomorphic_to":["coverture-household","police-crisis","cps"],
 "minimal_pair_of":None,
 "payoffs":{"bind":1.0,"leave_unbound":1.0},
 "coordinated":["bind","leave_unbound"],
 "initial_practice":"bind",
 "notes":("Layer-2 gate (a) institution. Mackie's convention: a family binds because every other family binds and suitors expect it "
   "(R3 sanctioned norm, R5 the market's refusal, R6/R7 the marriage condition); the campaign's pledge associations (R4) create a "
   "marriage pool in which an unbound daughter is marriageable, so the sanction R5 lapses for pledged families and leave_unbound "
   "(R2) becomes costless once enough neighbours pledge. Deviations from the task sketch: no matchmaker/community role (no source "
   "gives one a rule); a `suitor` role instead, because the sanction needs an actor and Mackie's sanction is the other side of "
   "the market; the pledge's son half is a second pledge action R10 accept_match_pledge (suitor) read by R5/R6 (until 2026-11-04 it was folded into the family's pledge; encoding review finding 2); marriageable is derived (ADR 0013) "
   "from R7 rather than asserted; R3 is unconditional and R5 carries the (not pledged) condition, so that the pledge changes "
   "nothing at layer 1 (the preregistration the gate pair needs). Sources: every text was read as a search snippet, none as a "
   "page (network closed in this session); the abstract sentences are verbatim from the index, everything else is [R] or "
   "UNVERIFIED and says so per rule. "+FB_PREREG+FB_PREREG2+FB_RESULT2+FB_DRIFT3+FB_COHORT+FB_NOTES_COORD)
})
inst.append({
 "id":"footbinding-no-pledge",
 "name":"Footbinding without the pledge action (minimal pair for gate (a))",
 "roles":FB_ROLES,"fluents":FB_FLUENTS,
 "actions":[a for a in FB_ACTIONS if not a["name"].endswith("_pledge")],
 "rules":[r for r in FB_RULES if r["id"] not in ("R4","R10")],
 "source_text":"Construction: footbinding with both pledge actions (leave_unbound_pledge, accept_match_pledge) and their rules R4 and R10 deleted (R10 since 2026-11-04, encoding review finding 2); pledged stays declared but nothing sets it. Historically the pre-1874 situation (no pledge associations).",
 "expected_properties":{"binding_practised":"persists","marriage_requires_binding":"holds_to_k",
                        "subject_cannot_exit":"reachable","dependent_cannot_exit":"reachable"},
 "isomorphic_to":[],
 "not_isomorphic_to":["coverture-household","police-crisis","cps"],
 "minimal_pair_of":{"id":"footbinding","rule":"R4,R10","differs_on":None},
 "payoffs":{"bind":1.0,"leave_unbound":1.0},
 "coordinated":["bind","leave_unbound"],
 "initial_practice":"bind",
 "notes":("PREREGISTERED (2026-11-04, before any run): the same four verdicts as footbinding (persists, holds_to_k, reachable, "
   "reachable): pledges change nothing at layer 1. The pair is the gate (a) 'pledge actions exist' half: crit_a reads "
   "_has_pledges on `footbinding` itself, so this entry is the dataset's record of what the no-pledge world looks like and "
   "`differs_on` is null by design (no layer-1 property separates them). At layer 2 the preregistration is the plan's: "
   "binding persists here under every module."+FB_PREREG2+FB_RESULT2+FB_DRIFT3+FB_COHORT)
})

# ---------------------------------------------------------------- ectogenesis / gestational-surrogacy (plans/ectogenesis.md)
# Encoded 2026-11-04 from the preregistration plans/ectogenesis.md (committed before this block, CONTRIBUTING step 2).
# Author decisions, all ASSUMED (given to the encoder in chat 2026-11-04, not in the plan file): (1) the R2+R3 substitution
# counts as a minimal pair; (2) E's R2/R3 are tagged `superadditive`, no new strand value; (3) R7 has no birth condition;
# (4) R5 triggers on female(p); (5) no leave action, the leave property rows are dropped; (6) neither entry is added to
# CONTROLS; (7) gestator consent is out of scope.
ECTO_UNV = ("UNVERIFIED: no text opened for this rule (plans/ectogenesis.md section 2: Firestone 1970 ch.1 and ch.10 are cited from memory; "
  "the one network probe, an archive.org search, returned HTTP 200 and no text was read or downloaded)")
FIRESTONE = ("Firestone, The Dialectic of Sex (1970), ch.1 (the demand to free women from 'the tyranny of their reproductive biology' "
  "and to spread child-bearing and child-rearing across society; wording from memory, check before quoting) and ch.10 "
  "'The Ultimate Revolution' (artificial reproduction and the end of the biological family; from memory). "+ECTO_UNV)
SURR_UNV = "Statute citations still to be added (state surrogacy acts vary). UNVERIFIED: no statute or case opened."
ECTO_DECISIONS = ("ASSUMED author decisions (2026-11-04, from the encoder's brief, not from the plan file): R2+R3 substituted counts as a minimal "
  "pair; E R2/R3 tagged `superadditive` by hand (no new strand value; claim L11 is refuted for this reason, plan section 5c); R7 has no "
  "birthing_parent condition; R5 triggers on female(p) (role not body: Kleven, docs/theory.md); no leave action, so the plan's "
  "leave_reserved_for_non_birthing_parent row is dropped; neither entry is in CONTROLS (ectogenesis is not registered as a "
  "care-without-control control); gestator consent is out of scope. BY CONSTRUCTION, flagged in advance (plan section 5): birth_labor_rival "
  "in ectogenesis restates R2's effect list (gestates is never set there), and care_decoupled_from_birth in ectogenesis is reachable "
  "because decant omits birthing_parent (the only non-trivial leg is R7's missing birth condition); both properties carry "
  "by_construction: true, which the engine ignores. Treat those two verdicts as information, as marriage_requires_binding was, not as "
  "evidence; non-circular evidence needs layer 2/3. Also by construction: gestated_ex_utero exists only to mark an absence.")
ECTO_PREREG = ("PREREGISTERED (plans/ectogenesis.md section 3, before any run; layer 1, init declared, strict compliance, k=6). "
  "gestational-surrogacy: birth_labor_rival holds_to_k; care_decoupled_from_birth unreachable_open; solo_care_by_non_birthing_parent "
  "reachable; care_assigned_by_sex violated. ectogenesis: birth_labor_rival violated; care_decoupled_from_birth reachable; "
  "solo_care_by_non_birthing_parent reachable; care_assigned_by_sex violated. Headline difference: birth_labor_rival. Iso (ADR 0010, "
  "about 65% confident): ectogenesis ~ surrogacy iso at guard, not iso at guard+strands (R2/R3 rival to superadditive tag flip), not iso at "
  "exact; ectogenesis not iso coverture-household / police-crisis / cps / kibbutz-childrens-house (no control permission over the subject, "
  "no exit bar, so the care+control sub-signature fails); vs transferable-leave / paternity-quota a guess of partial at guard+strands, two "
  "legs (R5~R7 implicit must-care by attribute; R4~R5 may care), about 40% confident. Failure modes (ADR 0016): surrogacy Displacement "
  "(layer 3); ectogenesis Dark twin (layer 3), Capture (needs a new rule), Dead letter (layer 2); R5 surviving is partial reform, no mode. "
  "Layer 2 not required.")
ECTO_ROLES = [{"name":"intended_parent","gloss":"the person or couple who will raise the child; the carer; the institutional sort, not a demographic (ADR 0011)"},
              {"name":"child","gloss":"the subject: the child, a subject only once born (is_subject is set only by a birth action)"},
              {"name":"provider","gloss":"the clinic or lab that starts, transfers, implants or decants gestation"},
              {"name":"registry","gloss":"vital records / court: registers parentage and reprimands"}]
SURR_ROLES = ECTO_ROLES + [{"name":"gestator","gloss":"the surrogate whose body carries the child; the rival input (one body, a short window; docs/theory.md 'Pregnancy, birth, nursing')"}]
ECTO_FLUENTS_COMMON = fl("is_subject","provides_care","female","parent","birthing_parent") + [
   F("in_gestation",1,"c is being carried or incubated, anywhere")]
ECTO_FLUENTS = ECTO_FLUENTS_COMMON + [
   F("gestated_ex_utero",1,"c is in a device (ectogenesis only; exists to mark an absence of a body)")]
SURR_FLUENTS = ECTO_FLUENTS_COMMON + [
   F("gestates",2,"x's body carries c (surrogacy only)")]
_ECTO_START = A("start_gestation",["provider","child"],[E("in_gestation",["child"],True)])
_ECTO_SHARED_ACTIONS = [
   A("register_parentage",["registry","intended_parent","child"],[E("parent",["intended_parent","child"],True)]),
   A("provide_care",["intended_parent","child"],[E("provides_care",["intended_parent","child"],True)]),
   A("reprimand",["registry","x"],[])]
ECTO_ACTIONS = [_ECTO_START] + _ECTO_SHARED_ACTIONS + [
   A("transfer_to_device",["provider","child"],[E("gestated_ex_utero",["child"],True)]),
   A("decant",["provider","child"],[E("is_subject",["child"],True),E("in_gestation",["child"],False),E("gestated_ex_utero",["child"],False)])]
SURR_ACTIONS = _ECTO_SHARED_ACTIONS + [
   A("implant",["provider","gestator","child"],[E("in_gestation",["child"],True),E("gestates",["gestator","child"],True)]),  # Revision 2: merged, no bodiless step
   A("give_birth",["gestator","child"],[E("birthing_parent",["gestator","child"],True),E("is_subject",["child"],True),
                                        E("in_gestation",["child"],False),E("gestates",["gestator","child"],False)])]
def _ecto_common_rules():
    return {
     "R1":R("R1","provider","may","(start_gestation provider child)","true",None,"rival",False,FIRESTONE+" (the technology that makes gestation a service; for surrogacy, the clinic's role in assisted conception)"),
     "R4":R("R4","intended_parent","may","(provide_care intended_parent child)","(and (parent intended_parent child) (is_subject child))",None,"superadditive",False,"care by any registered parent of a born child is permitted, men included; nothing here bars it. "+ECTO_UNV),
     "R5":R("R5","intended_parent","must","(provide_care intended_parent child)","(and (parent intended_parent child) (is_subject child) (female intended_parent))","R6","tying",True,
            "implicit sanctioned norm (a care-norm, not a written rule): the female registered parent of a born child must care for it. The condition names female and parent, NOT birthing_parent: the Kleven finding in docs/theory.md (adoptive mothers take the same hit, so role not body carries it). ASSUMED decision (author, 2026-11-04): trigger on female(p), so the norm survives the loss of the body. Not load-bearing at layer 1: it fires either way, so 'the tying strand outlives the rival input' is carried by the encoding, not discovered. "+ECTO_UNV),
     "R6":R("R6","registry","may","(reprimand registry x)","true",None,"tying",False,"the registry's sanction for R3 and R5 (or_else target). Condition 'true' as in kibbutz-childrens-house R6; x is untyped (the sanctioned party differs by rule). "+ECTO_UNV),
     "R7":R("R7","registry","may","(register_parentage registry intended_parent child)","(is_subject child)",None,"tying",False,"parentage is registered for any born child; NO birthing_parent condition (ASSUMED author decision, 2026-11-04; the legal default today keys it to the birth, which would make care_decoupled_from_birth unreachable in E). "+ECTO_UNV)}
_c = _ecto_common_rules()
ECTO_RULES = [_c["R1"],
  R("R2","provider","may","(transfer_to_device provider child)","(in_gestation child)",None,"superadditive",False,FIRESTONE+". Strand tag is a HAND TAG (ASSUMED author decision 2026-11-04; plan section 5c): the rival input is deleted, not redistributed, and no strand value says 'no strand'."),
  R("R3","provider","must","(decant provider child)","(gestated_ex_utero child)","R6","superadditive",False,FIRESTONE+". The birth duty moves from a body to a device operator; decant never sets birthing_parent. Strand tag is a HAND TAG (ASSUMED author decision 2026-11-04)."),
  _c["R4"],_c["R5"],_c["R6"],_c["R7"]]
_c = _ecto_common_rules()
SURR_RULES = [  # Revision 2: R1 and start_gestation removed (plans/ectogenesis.md v2)
  R("R2","provider","may","(implant provider gestator child)","true",None,"rival",False,"gestational surrogacy: the clinic implants an embryo in the gestator. "+SURR_UNV),
  R("R3","gestator","must","(give_birth gestator child)","(gestates gestator child)","R6","rival",False,"the gestator carries to term and gives birth; the rival input sits in one body. "+SURR_UNV+" Gestator consent and the right to keep the child are out of scope (ASSUMED author decision 2026-11-04)."),
  _c["R4"],_c["R5"],_c["R6"],_c["R7"]]
inst.append({
 "id":"ectogenesis",
 "name":"Ectogenesis (artificial womb; Firestone 1970): gestation in a device, no birthing parent",
 "roles":ECTO_ROLES,"fluents":ECTO_FLUENTS,"actions":ECTO_ACTIONS,"rules":ECTO_RULES,
 "source_text":"Firestone, The Dialectic of Sex (1970), ch.1 and ch.10: the demand to free women from the tyranny of their reproductive biology by artificial reproduction and to spread child-bearing and child-rearing across society. ALL UNVERIFIED: wording from memory, no page opened (plans/ectogenesis.md section 2). The mechanism is a thought-experiment technology; no statute exists.",
 "expected_properties":{"birth_labor_rival":"violated","care_decoupled_from_birth":"reachable",
                        "solo_care_by_non_birthing_parent":"reachable","care_assigned_by_sex":"violated"},
 "isomorphic_to":[{"id":"gestational-surrogacy","level":"guard","sub_signature":[]}],
 "not_isomorphic_to":["gestational-surrogacy","coverture-household","police-crisis","cps","kibbutz-childrens-house"],
 "minimal_pair_of":{"id":"gestational-surrogacy","rule":"R1,R2,R3","differs_on":"birth_labor_rival"},
 "notes":("Firestone's claim: ectogenesis removes the rival input itself (one body, a short window), where transferable-leave and kibbutz-childrens-house redistribute the care obligation around it. Substitution pair with gestational-surrogacy: R2 (transfer_to_device vs implant) and R3 (decant vs give_birth) swapped; everything else is shared. "+ECTO_DECISIONS+" "+ECTO_PREREG),
})
inst.append({
 "id":"gestational-surrogacy",
 "name":"Gestational surrogacy: the rival input moves to another body (control for ectogenesis)",
 "roles":SURR_ROLES,"fluents":SURR_FLUENTS,"actions":SURR_ACTIONS,"rules":SURR_RULES,
 "source_text":"Construction, not a statute: gestational surrogacy as the control for ectogenesis (plans/ectogenesis.md section 1). "+SURR_UNV,
 "expected_properties":{"birth_labor_rival":"holds_to_k","care_decoupled_from_birth":"unreachable_open",
                        "solo_care_by_non_birthing_parent":"reachable","care_assigned_by_sex":"violated"},
 "isomorphic_to":[{"id":"ectogenesis","level":"guard","sub_signature":[]}],
 "not_isomorphic_to":["ectogenesis","coverture-household","police-crisis","cps","kibbutz-childrens-house"],
 "minimal_pair_of":None,
 "notes":("Control: the rival input moves to a weaker party (failure mode Displacement; the model case is the global care chain; layer 3). The minimal pair is recorded on ectogenesis. Revision 2 (2026-11-04): start_gestation merged into implant per plans/ectogenesis.md v2; v1 drift 1 stays in the record. "+ECTO_DECISIONS+" "+ECTO_PREREG),
})

def L(f,*a): return "(%s %s)" % (f, " ".join(a))
def _animal_roles(owner):
    return {"owns":[owner,"animal"],"can_sanction":[owner,"animal"],"controls_reproduction":[owner,"animal"],
            "provides_care":[owner,"animal"],"is_subject":["animal"],"can_exit":["animal"],"has_standing":["animal"],
            "abandoned":["animal"],"at_large":["animal"],"best_interest":[owner,"animal"],"can_claim_for":["court","animal"]}
# union-typed slots (parent, provides_care, *_weeks_available, on_*_leave: either parent role) are left untyped
_leave_roles = {"birthing_parent":["birthing_parent","child"],"female":["birthing_parent"],"benefit_period_ended":["child"]}
_leave_init = [L("parent","birthing_parent","child"),L("parent","non_birthing_parent","child"),
               L("birthing_parent","birthing_parent","child"),L("female","birthing_parent")]
def _crisis_roles(r):
    d = {"is_subject":["subject"],"can_sanction":[r,"subject"],"provides_care":[r,"subject"],"can_exit":["subject"],
         "has_standing":["subject"],"in_custody":["subject"],"in_crisis":["subject"],"danger":["subject"],"call_received":["subject"]}
    if r == "responder":
        del d["can_sanction"]  # responder or officer (R8): untyped first slot
    return d
_cps_roles = {"is_subject":["child"],"can_sanction":["social_worker","child"],"provides_care":["social_worker","child"],
              "can_exit":["child"],"has_standing":["child"],"can_claim_for":["court","child"],"in_custody":["child"],
              "parent":["parent","child"],"female":["parent"],"report_received":["child"],"case_open":["child"],
              "immediate_danger":["child"],"cooperates":["parent","child"],"best_interest":["parent","child"],
              "in_home_considered":["social_worker","child"],"contacted":["social_worker","parent"],"counsel_appointed":["child"]}
_animal_init = lambda o: [L("owns",o,"animal"),L("is_subject","animal"),L("provides_care",o,"animal")]
# (arg_roles, initial, initial_free): exogenous triggers must be initial_free under init=declared, or no call/report ever arrives
_kib_roles = {"is_subject":["child"],"female":["metapelet"],"can_exit":["child"],"at_home":["child"]}
_kib_init = [L("female","metapelet"),L("is_subject","child"),L("member","metapelet"),L("member","male_member"),
             L("assigned","metapelet"),L("provides_care","metapelet","child")]
EXTRA = {
 "police-crisis":(_crisis_roles("officer"),[],["call_received","in_crisis","danger","resists"]),
 "crisis-team":(_crisis_roles("responder"),[],["call_received","eligible","in_crisis","danger"]),
 "cps":(_cps_roles,[],["report_received","immediate_danger","parent","female","best_interest"]),
 "paternity-quota":(_leave_roles,_leave_init,[]),
 "transferable-leave":(_leave_roles,_leave_init,[]),
 "companion-ownership":(_animal_roles("owner"),_animal_init("owner"),["best_interest"]),
 "companion-guardianship":(_animal_roles("owner"),_animal_init("owner"),["best_interest"]),
 "companion-guardian-renamed":(_animal_roles("guardian"),_animal_init("guardian"),["best_interest"]),
 "kibbutz-childrens-house":(_kib_roles,_kib_init,[]),
 "kibbutz-childrens-house-no-implicit":(_kib_roles,_kib_init,[]),
 "airline-flight":({"is_subject":["passenger"],"can_sanction":["crew","passenger"],"provides_care":["crew","passenger"],"can_exit":["passenger"],"aboard":["passenger"],"disruptive":["passenger"],"restrained":["passenger"]},[],["disruptive"]),
 "lease":({"is_subject":["tenant"],"can_exit":["tenant"],"leased":["landlord","tenant"],"habitable":["landlord","tenant"],"rent_paid":["tenant"]},[],[]),
 "footbinding":({"is_subject":["daughter"],"can_exit":["daughter"],"bound":["daughter"],"married":["daughter"],"marriageable":["family","daughter"]},[L("is_subject","daughter"),L("bound","daughter")],[]),
 "footbinding-no-pledge":({"is_subject":["daughter"],"can_exit":["daughter"],"bound":["daughter"],"married":["daughter"],"marriageable":["family","daughter"]},[L("is_subject","daughter"),L("bound","daughter")],[]),
 "public-library":({"is_subject":["patron"],"can_exit":["patron"],"open":["librarian"],"present":["patron"],"served":["librarian","patron"],"suspended":["patron"],"disruptive":["patron"]},[],["disruptive"]),
 "ectogenesis":({"is_subject":["child"],"provides_care":["intended_parent","child"],"female":["intended_parent"],"parent":["intended_parent","child"],"birthing_parent":["intended_parent","child"],"in_gestation":["child"],"gestated_ex_utero":["child"]},[],["female"]),
 "gestational-surrogacy":({"is_subject":["child"],"provides_care":["intended_parent","child"],"female":["intended_parent"],"parent":["intended_parent","child"],"birthing_parent":["gestator","child"],"in_gestation":["child"],"gestates":["gestator","child"]},[],["female"]),
 "naming-convention":({"uses_old":["member"],"uses_new":["member"]},[L("uses_old","member")],[]),
}
for mid in MWPA_IDS:
    EXTRA[mid] = (_mwpa_roles, [], ["female","acquired_property","earns"])
for i in inst:
    if i["id"] in EXTRA:
        ar, init, free = EXTRA[i["id"]]
        i["fluents"] = copy.deepcopy(i["fluents"])
        roles = {r["name"] for r in i["roles"]}
        for f in i["fluents"]:
            if f["name"] in ar:
                assert set(ar[f["name"]]) <= roles and len(ar[f["name"]])==f["arity"], (i["id"], f["name"])
                f["arg_roles"] = ar[f["name"]]
        i["initial"] = init
        if free:
            i["initial_free"] = free
        if i["id"] == "cps":
            i["defaults"] = {"cooperates":"true"}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "institutions.json")
json.dump(inst, open(out,"w"), indent=1); open(out,"a").write("\n")
print("ok", len(inst), [len(i["rules"]) for i in inst])
