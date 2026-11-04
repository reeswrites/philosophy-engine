"""rules_iso: bijection over roles ∪ fluents ∪ actions, partial matching, rule distance, strand flag."""
import copy

from philengine import rules_iso as ri
from philengine.schemas_rules import InstitutionJSON, load_institutions

from .helpers import require_dataset


def tiny(id_="base", **over) -> InstitutionJSON:
    d = {
        "id": id_,
        "roles": [{"name": "boss"}, {"name": "worker"}],
        "fluents": [{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1}, {"name": "tired", "arity": 1}],
        "actions": [
            {"name": "hire", "args": ["b", "w"], "effects": [{"fluent": "employed", "args": ["w"], "value": True}]},
            {"name": "pay", "args": ["b", "w"], "effects": [{"fluent": "paid", "args": ["w"], "value": True}]},
            {"name": "fire", "args": ["b", "w"], "effects": [{"fluent": "employed", "args": ["w"], "value": False}]},
            {"name": "quit", "args": ["w"], "effects": [{"fluent": "employed", "args": ["w"], "value": False}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "boss", "deontic": "may", "aim": "(hire b w)", "conditions": "true", "strand": "tying"},
            {"id": "R2", "attribute": "boss", "deontic": "must", "aim": "(pay b w)", "conditions": "(and (employed w) (not (tired w)))",
             "or_else": "R3", "strand": "superadditive"},
            {"id": "R3", "attribute": "worker", "deontic": "may", "aim": "(quit w)", "conditions": "(employed w)", "strand": "rival"},
            {"id": "R4", "attribute": "boss", "deontic": "must_not", "aim": "(fire b w)", "conditions": "(paid w)", "strand": "rival"},
        ],
    }
    d.update(over)
    return InstitutionJSON.model_validate(d)


def renamed() -> InstitutionJSON:
    """Same institution with every name changed, condition conjuncts reordered, variables renamed."""
    d = tiny("renamed").model_dump()
    sub = {"boss": "firm", "worker": "hand", "employed": "on_books", "paid": "settled", "tired": "weary",
           "hire": "engage", "pay": "remit", "fire": "dismiss", "quit": "walk"}
    d["roles"] = [{"name": sub[r["name"]], "gloss": ""} for r in d["roles"]]
    d["fluents"] = [{**f, "name": sub[f["name"]]} for f in d["fluents"]]
    d["actions"] = [{**a, "name": sub[a["name"]], "effects": [{**e, "fluent": sub[e["fluent"]]} for e in a["effects"]]}
                    for a in d["actions"]]
    rules = []
    for r in d["rules"]:
        r = dict(r)
        r["attribute"] = sub[r["attribute"]]
        for k, v in sub.items():
            r["aim"] = r["aim"].replace(k, v)
            r["conditions"] = r["conditions"].replace(k, v)
        r["aim"] = r["aim"].replace(" b ", " x ").replace(" w)", " y)").replace("(walk w)", "(walk y)")
        r["conditions"] = r["conditions"].replace(" w)", " y)")
        rules.append(r)
    rules[1]["conditions"] = "(and (not (weary y)) (on_books y))"  # reorder conjuncts
    rules.reverse()  # reorder rules
    d["rules"] = rules
    return InstitutionJSON.model_validate(d)


def test_pure_role_rename_is_cosmetic_iso():
    d = tiny("role-renamed").model_dump()
    d["roles"][0]["name"] = "employer"
    for r in d["rules"]:
        if r["attribute"] == "boss":
            r["attribute"] = "employer"
    b = InstitutionJSON.model_validate(d)
    r = ri.match(tiny(), b)
    assert r.iso and r.pure_rename and r.rule_distance == 0
    assert r.mapping["role"] == {"boss": "employer", "worker": "worker"}
    assert r.unmatched_a == [] and r.unmatched_b == []


def test_full_rename_is_structural_iso_not_cosmetic():
    r = ri.match(tiny(), renamed())
    assert r.iso and not r.pure_rename
    assert r.mapping["fluent"] == {"employed": "on_books", "paid": "settled", "tired": "weary"}
    assert r.mapping["action"]["pay"] == "remit"
    assert dict(r.matched_sub_signature) == {"R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4"}
    assert "structural" in r.notes[0]


def test_one_rule_added_is_distance_one():
    d = tiny("plus").model_dump()
    d["rules"].append({"id": "R5", "attribute": "worker", "deontic": "must", "aim": "(quit w)", "conditions": "(tired w)",
                       "or_else": None, "strand": "rival", "implicit": True, "source": "", "var_roles": {}})
    b = InstitutionJSON.model_validate(d)
    r = ri.match(tiny(), b)
    assert not r.iso and r.rule_distance == 1 and r.add_remove_distance == 1
    assert r.unmatched_a == [] and r.unmatched_b == ["R5"]
    assert len(r.matched_sub_signature) == 4


def test_different_deontic_is_not_iso_but_reports_partial():
    d = tiny("deontic").model_dump()
    d["rules"][3]["deontic"] = "may"
    b = InstitutionJSON.model_validate(d)
    r = ri.match(tiny(), b)
    assert not r.iso and r.rule_distance == 1 and r.add_remove_distance == 2
    assert r.unmatched_a == ["R4"] and r.unmatched_b == ["R4"]
    assert dict(r.matched_sub_signature) == {"R1": "R1", "R2": "R2", "R3": "R3"}


def test_or_else_linkage_matters():
    # same rules, but the sanction of R2 points at a different (structurally equal) rule: linkage must be preserved
    d = tiny("link").model_dump()
    d["rules"].append({"id": "R5", "attribute": "worker", "deontic": "may", "aim": "(quit w)", "conditions": "(paid w)",
                       "or_else": None, "strand": "rival", "implicit": False, "source": "", "var_roles": {}})
    a = InstitutionJSON.model_validate(d)
    d2 = copy.deepcopy(d); d2["id"] = "link2"; d2["rules"][1]["or_else"] = "R5"
    b = InstitutionJSON.model_validate(d2)
    r = ri.match(a, b)
    # R2's sanction is R3 in a and R5 in b; R3/R5 have different conditions, so they cannot map to each other
    assert not r.iso
    assert ("R2", "R2") not in r.matched_sub_signature or dict(r.matched_sub_signature).get("R3") != "R3"


def test_with_strands_can_break_a_match():
    d = tiny("strand").model_dump()
    d["rules"][0]["strand"] = "rival"
    b = InstitutionJSON.model_validate(d)
    assert ri.match(tiny(), b, with_strands=False).iso
    r = ri.match(tiny(), b, with_strands=True)
    assert not r.iso and r.unmatched_a == ["R1"]


def test_guard_level_abstracts_conditions():
    d = tiny("guard").model_dump()
    d["rules"][2]["conditions"] = "(paid w)"
    b = InstitutionJSON.model_validate(d)
    assert not ri.match(tiny(), b).iso
    assert ri.match(tiny(), b, cond_level="guard").iso


def test_real_dataset_expectations():
    insts = {i.id: i for i in load_institutions(require_dataset()[0])}
    r = ri.match(insts["companion-ownership"], insts["companion-guardian-renamed"])
    assert r.iso and r.pure_rename and r.mapping["role"]["owner"] == "guardian"
    r = ri.match(insts["companion-ownership"], insts["companion-guardianship"])
    assert not r.iso and r.rule_distance == 1 and r.unmatched_a == ["R9"] and r.unmatched_b == ["R9"]
    r = ri.match(insts["paternity-quota"], insts["transferable-leave"])
    assert not r.iso and r.rule_distance == 1 and r.unmatched_a == ["R2"] and r.unmatched_b == ["R2"]
    for other in ("coverture-household", "police-crisis", "cps"):
        assert not ri.match(insts["crisis-team"], insts[other]).iso


# ------------------------------------------------------------ care + control form, levels (review finding 4)
def care_control(id_, x, s, care_act, ctrl_act, exit_act, *, bar=True, same_target=True, extra=()):
    """A minimal care + control institution: X must care for S, X may control S, S must not exit."""
    tgt = s if same_target else x  # a control aimed at a third party is not control over the subject
    roles = [{"name": x}, {"name": s}, {"name": "other"}]
    rules = [
        {"id": "R1", "attribute": x, "deontic": "may", "aim": f"(bind a b)", "conditions": f"(not (bound a b))", "strand": "tying"},
        {"id": "R2", "attribute": x, "deontic": "must", "aim": f"({care_act} a b)", "conditions": "(bound a b)", "or_else": None, "strand": "superadditive"},
        {"id": "R3", "attribute": x, "deontic": "may", "aim": f"({ctrl_act} a b)", "conditions": "(bound a b)", "strand": "rival",
         **({} if same_target else {"var_roles": {"b": "other"}})},
    ]
    if bar:
        rules.append({"id": "R4", "attribute": s, "deontic": "must_not", "aim": f"({exit_act} b)", "conditions": f"(bound {x} b)", "or_else": None, "strand": "rival"})
    rules.extend(extra)
    return InstitutionJSON.model_validate({
        "id": id_, "roles": roles,
        "fluents": [{"name": "bound", "arity": 2, "arg_roles": [x, s]}, {"name": care_act, "arity": 2, "arg_roles": [x, s]}],
        "actions": [{"name": "bind", "args": ["a", "b"], "arg_roles": [x, s], "effects": [{"fluent": "bound", "args": ["a", "b"], "value": True}]},
                    {"name": ctrl_act, "args": ["a", "b"], "arg_roles": [x, None], "effects": []},
                    {"name": exit_act, "args": ["b"], "arg_roles": [s], "effects": [{"fluent": "bound", "args": [x, "b"], "value": False}]},
                    {"name": "misc", "args": ["a"], "effects": []}],
        "rules": rules,
    })


def lease(id_="lease") -> InstitutionJSON:
    """Negative control: landlord must keep the unit habitable when leased, may evict on breach; the tenant may
    terminate freely. A duty + a rival may on the same attribute, but no bar on the tenant's own action."""
    return InstitutionJSON.model_validate({
        "id": id_, "roles": [{"name": "landlord"}, {"name": "tenant"}],
        "fluents": [{"name": "leased", "arity": 2, "arg_roles": ["landlord", "tenant"]},
                    {"name": "habitable", "arity": 2, "arg_roles": ["landlord", "tenant"]},
                    {"name": "breach", "arity": 1, "arg_roles": ["tenant"]}],
        "actions": [{"name": "lease_to", "args": ["l", "t"], "effects": [{"fluent": "leased", "args": ["l", "t"], "value": True}]},
                    {"name": "evict", "args": ["l", "t"], "effects": [{"fluent": "leased", "args": ["l", "t"], "value": False}]},
                    {"name": "terminate", "args": ["t"], "effects": [{"fluent": "leased", "args": ["landlord", "t"], "value": False}]},
                    {"name": "default", "args": ["t"], "effects": [{"fluent": "breach", "args": ["t"], "value": True}]}],
        "rules": [
            {"id": "R1", "attribute": "landlord", "deontic": "may", "aim": "(lease_to l t)", "conditions": "(not (leased l t))", "strand": "tying"},
            {"id": "R2", "attribute": "landlord", "deontic": "must", "aim": "(habitable l t)", "conditions": "(leased l t)", "or_else": None, "strand": "superadditive"},
            {"id": "R3", "attribute": "landlord", "deontic": "may", "aim": "(evict l t)", "conditions": "(and (leased l t) (breach t))", "strand": "rival"},
            {"id": "R4", "attribute": "tenant", "deontic": "may", "aim": "(terminate t)", "conditions": "(leased landlord t)", "strand": "rival"},
            {"id": "R5", "attribute": "tenant", "deontic": "must_not", "aim": "(default t)", "conditions": "(leased landlord t)", "or_else": "R3", "strand": "tying"},
        ],
    })


def test_care_control_requires_duty_control_on_same_subject_and_exit_bar():
    a = care_control("cov", "husband", "wife", "maintain", "chastise", "leave")
    b = care_control("pol", "officer", "subject", "provides_care", "use_force", "walk")
    r = ri.match(a, b, True, "guard")
    cc = ri.care_control_subsignature(r, a, b)
    assert cc is not None
    assert cc.care == ("R2", "R2") and cc.control == ("R3", "R3") and cc.exit_bar == ("R4", "R4")
    assert cc.subject_role == ("wife", "subject") and cc.matched == 4 and cc.n_a == cc.n_b == 4
    assert list(cc) == cc.pairs() and 0 < cc.coverage <= 1
    assert "exit_bar R4:(leave b) ~ R4:(walk b)" in ri.format_care_control(cc, a, b)
    # no bar on the subject's own action: a duty + a rival may is not care + control
    b2 = care_control("pol2", "officer", "subject", "provides_care", "use_force", "walk", bar=False)
    r2 = ri.match(a, b2, True, "guard")
    assert ("R2", "R2") in r2.matched_sub_signature and ("R3", "R3") in r2.matched_sub_signature
    assert ri.care_control_subsignature(r2, a, b2) is None
    # the rival may aimed at a third party, not the subject the duty serves, is not control over the subject
    b3 = care_control("pol3", "officer", "subject", "provides_care", "use_force", "walk", same_target=False)
    r3 = ri.match(a, b3, True, "guard")
    assert ri.care_control_subsignature(r3, a, b3) is None


def test_lease_is_a_negative_control_at_guard_strands():
    a = care_control("cov", "husband", "wife", "maintain", "chastise", "leave")
    for level in ri.LEVELS:
        cond, ws = ri.parse_level(level)
        r = ri.match(a, lease(), ws, cond)
        assert not r.iso
        assert ri.care_control_subsignature(r, a, lease()) is None, level
    # the lease does share the weak form (duty + rival may on one attribute) at guard+strands: the old matcher's bug
    r = ri.match(a, lease(), True, "guard")
    assert ("R2", "R2") in r.matched_sub_signature and ("R3", "R3") in r.matched_sub_signature


def test_rule_target_and_parse_level():
    a = care_control("cov", "husband", "wife", "maintain", "chastise", "leave")
    assert ri.rule_target(a.rules[1], a) == ("b", "wife")
    assert ri.rule_target(a.rules[3], a) == (None, None)
    assert ri.parse_level("guard+strands") == ("guard", True)
    assert ri.parse_level("exact") == ("exact", False)
    assert ri.level_name("guard", True) == "guard+strands"
    import pytest
    with pytest.raises(ValueError):
        ri.parse_level("fuzzy")
