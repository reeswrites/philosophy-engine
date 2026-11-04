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
CONTROLS = ["lease","public-library"]
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
   F("controls_property",2,"h holds and manages w's property and earnings")],
 "actions":[
   A("marry",["h","w"],[E("married",["h","w"],True),E("is_subject",["w"],True),E("controls_property",["h","w"],True),
                        E("provides_care",["h","w"],True),E("provides_care",["w","h"],True)]),
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
                        "care_and_sanction_same_role":"holds_to_k","no_standing":"reachable","care_assigned_by_sex":"violated"},
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
KIB_R2 = R("R2","committee","must_not","(assign committee male_member)","true",None,"tying",True,
   "IMPLICIT: the nanny 'was always a woman's role' (WIKI_KIB); no kibbutz by-law said so, the rota simply never put a man in the children's house. "+TIGER+". A disability (or_else null): can_assign(committee, male_member) is false by derivation, not by any effect (ADR 0013)", load_bearing=LB)
KIB_RULES = [
   R("R1","committee","may","(assign committee x)","(member x)",None,"superadditive",False,WIKI_KIB+" (members are assigned to the children's house by the committee; the rule as written is sex-blind: any member). "+DERIVED+"can_assign(committee, x) = assign enabled (R1) and not barred (R2)"),
   KIB_R2,
   R("R3","metapelet","must","(provides_care metapelet child)","(assigned metapelet)","R6","superadditive",False,WIKI_KIB+" (the metapelet runs the children's house). "+STATE+"assign establishes provides_care(x, child); neglect breaks it (sanction R6); release ends the assignment", load_bearing=LB),
   R("R4","child","must_not","(sleep_home child)","true",None,"rival",False,WIKI_KIB+" (communal sleeping: the children lived and slept in the children's house). A disability (or_else null), as every subject-side exit bar since ADR 0013; the draft's or_else R6 is dropped for the same reason as coverture R6. "+DERIVED+"can_exit(child) = sleep_home enabled (R7) and not barred (R4)"),
   R("R5","male_member","may","(visit male_member child)","true",None,"superadditive",False,WIKI_KIB+" (children 'visited their parents for 2-3 hours a day'; the father's relation to the children's house is the visit, not care)"),
   R("R6","committee","may","(reprimand committee x)","true",None,"rival",True,"implicit: the committee / general assembly disciplines a member who neglects the rota (R3's or_else). "+UNV+". "+DERIVED+"can_sanction(committee, x) = reprimand enabled (R6)"),
   R("R7","child","may","(sleep_home child)","true",None,"rival",True,"implicit: the physical possibility of sleeping at the parents' home is always there; R4 removes it. What the 1970s-1990s reform changed is R4 (dropped kibbutz by kibbutz, last at Baram in 1997: "+JTA_BARAM+"); the reform did not touch R2 ("+SCMP_BARAM+"). "+DERIVED+"can_exit(child) = sleep_home enabled (R7) and not barred (R4)")]
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
 "notes":"Gate (d): the historical failure. The explicit rules are sex-blind (R1 may assign any member) and the reform of the 1970s-1990s removed the exit bar on the child (R4), yet care_assigned_by_sex PERSISTS because the implicit disability R2 (never a man in the children's house) survives: every compliant trace keeps provides_care in female hands, and can_assign(committee, male_member) is false at every step by derivation. PREREGISTERED (2026-11-03, before any run): care_assigned_by_sex persists here; fails in kibbutz-childrens-house-no-implicit, which is this entry minus R2 (differs_on care_assigned_by_sex); subject_cannot_exit reachable (R4 bars sleep_home); care_and_sanction_same_role violated (the committee sanctions, the metapelet cares). Deviations from plans/institutions-batch2.md: R1 is '(assign committee x) when (member x)' rather than '(assign committee metapelet)', because an action instance no may/must rule names is disabled, so the draft's ablation (drop R2 -> assign male_member) only bites if R1 covers the man; R4 is a disability (or_else null) per the ADR 0013 exit convention, so R6 is R3's or_else only and its condition is 'true' (the or_else link enables it on breach); an implicit R7 'may sleep_home' carries can_exit as in every other entry; the draft's release action is kept but the breaker of R3 is neglect (release clears the condition with the state, so it breaks nothing). Pitfalls: (1) female needs arg_roles [metapelet] or the solver invents a female male_member; (2) an encoder that writes R1 as 'may assign metapelet' hides R2 inside R1 and the no-implicit variant collapses into the original; (3) 'persists' is about what the rules permit, not uptake. Rival reading (notes only): regendering of care came from mothers' demands (SCMP), not from the committee; the entry does not encode who drove the reform."
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
 "lease":({"is_subject":["tenant"],"can_exit":["tenant"],"leased":["landlord","tenant"],"habitable":["landlord","tenant"],"rent_paid":["tenant"]},[],[]),
 "public-library":({"is_subject":["patron"],"can_exit":["patron"],"open":["librarian"],"present":["patron"],"served":["librarian","patron"],"suspended":["patron"],"disruptive":["patron"]},[],["disruptive"]),
}
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
