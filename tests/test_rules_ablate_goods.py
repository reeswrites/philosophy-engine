"""Goods in rule ablation (plans/priority-slice2.md section 6): goods_state, lost / gained, contested alternatives,
readings and strand agreement, validator rejections."""
import json

import pytest

from philengine import rules_ablate as ra
from philengine.schemas_rules import InstitutionJSON, Property, PropertyResult, RulesLoadError, load_properties

CARED = "(forall ((s agent)) (=> (is_subject s t) (exists ((c agent)) (cares c s t))))"


def good(name, formal, contested=(), **kw):
    return Property(name=name, kind="goods", polarity="good", check="persists", encoders=["e1", "e2"],
                    contested=list(contested), formal=formal, **kw)


def care(extra_rules=()):
    """A carer may enrol a subject (which starts care); while s is a subject, care must hold (R2, must-be); neglect,
    unregulated, breaks care, so only R2 keeps it. go_home is barred by a disability (R3); it sends s home."""
    inst = InstitutionJSON.model_validate({
        "id": "t-care",
        "roles": [{"name": "carer"}, {"name": "subj"}],
        "fluents": [{"name": "is_subject", "arity": 1, "arg_roles": ["subj"]},
                    {"name": "cares", "arity": 2, "arg_roles": ["carer", "subj"]},
                    {"name": "at_home", "arity": 1, "arg_roles": ["subj"]}],
        "actions": [
            {"name": "enrol", "args": ["c", "s"], "arg_roles": ["carer", "subj"],
             "effects": [{"fluent": "is_subject", "args": ["s"], "value": True},
                         {"fluent": "cares", "args": ["c", "s"], "value": True}]},
            {"name": "neglect", "args": ["c", "s"], "arg_roles": ["carer", "subj"],
             "effects": [{"fluent": "cares", "args": ["c", "s"], "value": False}]},
            {"name": "go_home", "args": ["s"], "arg_roles": ["subj"],
             "effects": [{"fluent": "at_home", "args": ["s"], "value": True},
                         {"fluent": "is_subject", "args": ["s"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "carer", "deontic": "may", "aim": "(enrol c s)", "conditions": "true", "strand": "tying"},
            {"id": "R2", "attribute": "carer", "deontic": "must", "aim": "(cares c s)", "conditions": "(is_subject s)",
             "or_else": None, "strand": "superadditive"},
            {"id": "R3", "attribute": "subj", "deontic": "must_not", "aim": "(go_home s)", "conditions": "true",
             "or_else": None, "strand": "rival"},
            *extra_rules,
        ],
        "expected_properties": {},
    })
    props = {
        "cared": good("cared", CARED),
        "home": good("home", "(forall ((s agent)) (=> (at_home s t) (is_subject s t)))"),
    }
    return inst, props


def row(res, rid):
    return next(a for a in res if a.rule_id == rid)


def test_goods_state_mapping():
    def r(v, **kw):
        return PropertyResult(property="g", check="persists", verdict=v, **kw)
    assert ra.goods_state(r("persists", antecedent_reachable=True, subject_exists=True)) == "stable"
    assert ra.goods_state(r("persists", antecedent_reachable=False, vacuous=True)) == "absent"  # vacuous persists
    assert ra.goods_state(r("persists", antecedent_reachable=True, subject_exists=False, vacuous=True)) == "absent"
    assert ra.goods_state(r("fails", antecedent_reachable=True)) == "fragile"
    assert ra.goods_state(r("persists", antecedent_reachable=None)) is None  # vacuity undecided: uncounted
    assert ra.goods_state(r("open", z3_unknown=True)) is None and ra.goods_state(r("error")) is None
    assert ra.goods_state(None) is None


def test_must_be_care_duty_deleted_is_lost_and_constitutive():
    inst, props = care()
    res = ra.ablate(inst, props, k=4)
    a = row(res, "R2")
    assert a.goods_states["cared"] == ["stable", "fragile"]
    assert (a.load_goods, a.load_goods_gained, a.goods_families_lost) == (1, 0, ["cared"])
    assert a.load_freedom_up == 0 and a.reading() == "constitutive"
    assert ra.strand_agreement(a.strand, a.reading()) == "agree"
    assert a.load_goods_by_encoder["e1"]["lost"] == 1 and a.load_goods_by_encoder["e2"]["lost"] == 1  # no alternative


def test_deleting_a_disability_yields_a_good_gained_not_lost():
    inst, props = care()
    a = row(ra.ablate(inst, props, k=4), "R3")
    assert a.goods_states["home"] == ["absent", "stable"]  # vacuous persists before, live after
    assert (a.load_goods, a.load_goods_gained, a.goods_families_gained) == (0, 1, ["home"])
    assert a.reading() == "unread"


def test_contested_alternative_reported_beside_never_pooled():
    inst, props = care()
    alt = "(forall ((s agent)) (=> (is_subject s t) (is_subject s t)))"  # trivially true: never lost
    props["cared"] = good("cared", CARED, contested=[{"encoder": "e2", "formal": alt, "note": "toy"}])
    res = ra.ablate(inst, props, k=4)
    a = row(res, "R2")
    assert a.load_goods == 1  # the primary's
    assert a.goods_alt_states == {"cared@e2": ["stable", "stable"]}
    assert a.load_goods_by_encoder["e1"]["lost"] == 1 and a.load_goods_by_encoder["e2"]["lost"] == 0
    assert a.reading_by_encoder() == {"e1": "constitutive", "e2": "unread"}
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    # R1~prohibit (condition true, ranked): no subject is ever enrolled, so both formulas turn vacuous: stable > absent
    assert summ["constitutive"] == ["R1~prohibit", "R2"] and summ["contested_readings"] == ["R2"]
    assert row(res, "R1~prohibit").goods_states["cared"] == ["stable", "absent"]
    stats = ra.scoreboard_stats({"t": m}, (4,))
    assert stats["contested_readings"] == 1 and stats["goods_rows"] >= 1
    assert "cared@e2" not in {f[0] for f in a.flips}


def test_adding_goods_changes_no_freedom_column():
    inst, props = care()
    props["subj_free"] = Property(name="subj_free", kind="freedom", polarity="unfreedom", check="persists",
                                  formal="(forall ((s agent)) (=> (is_subject s t) (not (at_home s t))))")
    only_freedom = {"subj_free": props["subj_free"]}
    keys = ("rule_id", "load_freedom", "load_freedom_up", "load_freedom_down", "load_freedom_unsigned", "families_up",
            "families_down", "families_mixed", "flip_directions", "deregulated", "offcondition_free", "inconsistent_after")
    a = [{k: x.to_dict()[k] for k in keys} for x in ra.ablate(inst, only_freedom, k=4)]
    b = [{k: x.to_dict()[k] for k in keys} for x in ra.ablate(inst, props, k=4)]
    assert a == b and any(r["load_freedom"] for r in a)


def test_entries_make_a_goods_property_applicable_despite_undeclared_fluent():
    inst, props = care()
    g = good("g", "(forall ((s agent)) (=> (is_subject s t) (or (cares carer s t) (elsewhere s t))))")
    which, na = ra.applicable_which(inst, {"g": g})
    assert "g" in na and "g" not in which
    g2 = g.model_copy(update={"entries": ["t-care"]})
    which, na = ra.applicable_which(inst, {"g": g2})
    assert which == {"g": ["persists"]} and na == []


def test_reading_and_strand_agreement_table():
    assert [ra.reading(u, l) for u, l in ((1, 0), (0, 2), (1, 1), (0, 0))] == ["tying", "constitutive", "hard case", "unread"]
    assert ra.strand_agreement("tying", "tying") == "agree"
    assert ra.strand_agreement("superadditive", "constitutive") == "agree"
    assert ra.strand_agreement("tying", "hard case") == "mismatch"
    assert ra.strand_agreement("superadditive", "tying") == "mismatch"
    assert ra.strand_agreement("rival", "tying") == "no_row"
    assert ra.strand_agreement("tying", "unread") == "unread" and ra.strand_agreement("rival", "unread") == "unread"


@pytest.mark.parametrize("item,match", [
    ({"kind": "goods", "polarity": "good", "check": "persists", "encoders": ["a", "b"]}, "contested"),
    ({"kind": "goods", "polarity": "good", "check": "persists", "encoders": ["a"], "contested": []}, "two encoders"),
    ({"kind": "goods", "polarity": "good", "check": "persists", "encoders": ["a", "a"], "contested": []}, "two encoders"),
    ({"kind": "goods", "polarity": "unfreedom", "check": "persists", "encoders": ["a", "b"], "contested": []}, "polarity: good"),
    ({"kind": "goods", "check": "persists", "encoders": ["a", "b"], "contested": []}, "polarity: good"),
    ({"kind": "goods", "polarity": "good", "check": "invariant", "encoders": ["a", "b"], "contested": []}, "persists"),
    ({"kind": "freedom", "polarity": "good"}, "polarity"),
    ({"kind": "structure", "polarity": "good"}, "only for kind goods"),
    ({"kind": "goods", "polarity": "good", "check": "persists", "encoders": ["a", "b"],
      "contested": [{"encoder": "b", "formal": "(and (held ward t)"}]}, "does not parse"),
])
def test_validator_rejections(tmp_path, item, match):
    p = tmp_path / "p.json"
    p.write_text(json.dumps([{"name": "x", "formal": "(held ward t)", **item}]))
    with pytest.raises(RulesLoadError, match=match):
        load_properties(p)


def test_validator_accepts_goods():
    p = good("x", "(held ward t)", contested=[{"encoder": "e2", "formal": "(not (held ward t))"}])
    assert p.contested[0].encoder == "e2" and p.contested[0].note == ""
    assert set(ra.expand_contested({"x": p})) == {"x", "x@e2"}
    assert ra.expand_contested(ra.expand_contested({"x": p})).keys() == {"x", "x@e2"}


def test_spawn_workers_match_serial_on_goods(monkeypatch):
    from philengine.abm import parallel
    monkeypatch.setenv("PHIL_START_METHOD", "spawn")
    inst, props = care()
    props["cared"] = good("cared", CARED, contested=[{"encoder": "e2", "formal": "(forall ((s agent)) (is_subject s t))"}])
    s1 = ra.ablate_multi_k(inst, props, (4, 5), workers=1)
    with parallel.pool(4):
        s4 = ra.ablate_multi_k(inst, props, (4, 5), workers=None)
    assert [m.to_dict() for m in s1] == [m.to_dict() for m in s4]


def test_cli_ablate_readings_table(tmp_path):
    from philengine.cli import build_parser
    inst, props = care()
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([p.model_dump(mode="json") for p in props.values()]))
    out = tmp_path / "r.md"
    a = build_parser().parse_args(["rules", "ablate", "--k", "4", "--institutions", str(tmp_path / "i.json"),
                                   "--properties", str(tmp_path / "p.json"), "--readings", str(out)])
    assert a.fn(a) == 0
    txt = out.read_text()
    assert "| t-care | R2 | yes | superadditive | 4 | 0 | 1 | 1 | 0 | 0 | constitutive | constitutive | agree | agree |" in txt


def test_dataset_goods_have_two_encoders_and_contested(dataset_env):
    props = load_properties(dataset_env[1])
    for n, p in props.items():
        if p.kind == "goods":
            assert len(set(p.encoders)) >= 2 and p.contested is not None and p.polarity == "good", n
