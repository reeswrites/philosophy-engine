"""rules_compose.freeze_bindings: write the prefix heuristic's answer into var_roles; never override; grounding unchanged."""
import json

from philengine import cli_rules
from philengine import rules_compose as rc
from philengine.rules_reference import Reference
from philengine.schemas_rules import InstitutionJSON


def toy() -> InstitutionJSON:
    def rule(id, aim, cond="true", deontic="must", var_roles=None):
        return {"id": id, "attribute": "husband", "deontic": deontic, "aim": aim, "conditions": cond,
                "strand": None, "var_roles": var_roles or {}}
    return InstitutionJSON.model_validate({
        "id": "toy",
        "roles": [{"name": "husband"}, {"name": "wife"}, {"name": "worker"}, {"name": "warden"}],
        "fluents": [{"name": "bound", "arity": 1}],
        "actions": [{"name": "give", "args": ["h", "wi"], "effects": []}],
        "rules": [
            rule("R1", "(give h z)"),                                        # z via action param wi -> wife
            rule("R2", "(bound wi)", cond="(bound w)"),                      # wi prefix -> wife; w ambiguous
            rule("R3", "(bound wi)", deontic="must_not", var_roles={"wi": "husband"}),  # conflict
            rule("R4", "(bound wi)", var_roles={"wi": "wife"}),              # already explicit
        ],
    })


def by(rows):
    return {(r.rule, r.variable): r for r in rows}


def test_slot0_attribute_written_and_conflict():
    inst = toy()
    frozen, rows = rc.freeze_bindings(inst)
    m = by(rows)
    assert (m["R1", "h"].role, m["R1", "h"].action) == ("husband", "written")
    assert {r.id: r.var_roles for r in frozen.rules}["R1"] == {"h": "husband", "z": "wife"}
    bad = inst.model_copy(update={"rules": [inst.rules[0].model_copy(update={"var_roles": {"h": "wife"}})]})
    f2, rows2 = rc.freeze_bindings(bad)
    c = by(rows2)["R1", "h"]
    assert (c.action, c.role, c.existing) == ("conflict", "husband", "wife")
    assert f2.rules[0].var_roles["h"] == "wife"  # not overwritten
    ok = inst.model_copy(update={"rules": [inst.rules[0].model_copy(update={"var_roles": {"h": "husband"}})]})
    assert by(rc.freeze_bindings(ok)[1])["R1", "h"].action == "already_explicit"


def test_slot0_entry_does_not_change_grounding():
    inst = toy()
    frozen, _ = rc.freeze_bindings(inst)
    assert frozen.rules[0].var_roles["h"] == "husband"
    # even a wrong explicit slot-0 entry must not move typing: attribute still wins
    wrong = frozen.model_copy(update={"rules": [frozen.rules[0].model_copy(update={"var_roles": {"h": "wife"}})] + list(frozen.rules[1:])})
    a, b, w = Reference(inst), Reference(frozen), Reference(wrong)
    assert b.aim_types(frozen.rules[0])["h"] == "husband" == w.aim_types(wrong.rules[0])["h"]
    key = lambda ref: [(x.rule_id, x.args, x.free_doms) for x in ref.rule_insts]
    assert key(a) == key(b) == key(w)


def test_written_untyped_conflict_explicit():
    inst = toy()
    frozen, rows = rc.freeze_bindings(inst)
    m = by(rows)
    assert (m["R1", "z"].role, m["R1", "z"].action) == ("wife", "written")
    assert (m["R2", "wi"].role, m["R2", "wi"].action) == ("wife", "written")
    assert (m["R2", "w"].role, m["R2", "w"].action) == (None, "untyped")  # condition variable, ambiguous prefix
    assert m["R3", "wi"].action == "conflict" and m["R3", "wi"].role == "wife" and m["R3", "wi"].existing == "husband"
    assert m["R4", "wi"].action == "already_explicit"
    vr = {r.id: r.var_roles for r in frozen.rules}
    assert vr["R1"] == {"h": "husband", "z": "wife"}
    assert vr["R2"] == {"wi": "wife"}  # untyped w left alone
    assert vr["R3"] == {"wi": "husband"}  # explicit kept
    assert vr["R4"] == {"wi": "wife"}
    assert all(r.var_roles == {} for r in inst.rules[:2])  # input not mutated


def test_grounding_unchanged():
    inst = toy()
    frozen, _ = rc.freeze_bindings(inst)
    a, b = Reference(inst), Reference(frozen)
    for r0, r1 in zip(inst.rules, frozen.rules):
        assert b.aim_types(r1) == a.aim_types(r0)
        assert b.free_var_types(r1, None) == a.free_var_types(r0, None)
    assert [(x.rule_id, x.args, x.free_doms) for x in a.rule_insts] == [(x.rule_id, x.args, x.free_doms) for x in b.rule_insts]


def test_idempotent():
    frozen, _ = rc.freeze_bindings(toy())
    again, rows = rc.freeze_bindings(frozen)
    assert not [r for r in rows if r.action == "written"]
    assert again == frozen
    assert {r.action for r in rows} <= {"already_explicit", "untyped", "conflict"}


def test_cli_json(tmp_path, capsys):
    p = tmp_path / "i.json"
    p.write_text(json.dumps([toy().model_dump(mode="json")]))
    pp = tmp_path / "p.json"
    pp.write_text("[]")
    ns = type("A", (), {"institutions": str(p), "properties": str(pp), "entry": ["toy"], "json": True})()
    assert cli_rules.cmd_freeze_bindings(ns) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["entry"] == "toy" and out[0]["var_roles"]["R1"] == {"h": "husband", "z": "wife"}
    assert {"entry", "rule", "variable", "role", "action", "existing"} <= set(out[0]["rows"][0])


# ---------------------------------------------------------------------------------------------------------------
# compose (ADR 0018)
import pytest

from philengine.rules_ablate import applicable_which
from philengine.schemas_rules import Property


def entry(id, roles, fluents=None, actions=None, rules=None, **kw):
    return InstitutionJSON.model_validate({
        "id": id, "roles": [{"name": r} for r in roles],
        "fluents": fluents or [{"name": "married", "arity": 2, "arg_roles": [roles[0], roles[1]]}],
        "actions": actions or [], "rules": rules or [], **kw})


def rl(id, attr, aim, cond="true", or_else=None, deontic="must", var_roles=None):
    return {"id": id, "attribute": attr, "deontic": deontic, "aim": aim, "conditions": cond, "strand": None,
            "or_else": or_else, "var_roles": var_roles or {}}


def pair():
    a = entry("cov-a", ["husband", "wife"],
              fluents=[{"name": "married", "arity": 2, "arg_roles": ["husband", "wife"]}, {"name": "owes", "arity": 1}],
              actions=[{"name": "pay", "args": ["h", "w"], "effects": [{"fluent": "owes", "args": ["w"], "value": False}]}],
              rules=[rl("R1", "husband", "(pay h w)", "(married h w)", or_else="R2", var_roles={"h": "husband"}),
                     rl("R2", "wife", "(pay h w)", "(married h w)", deontic="may")],
              initial=["married(husband, wife)"], defaults={"owes": "false"})
    b = entry("hosp-b", ["patient", "visitor"],
              fluents=[{"name": "married", "arity": 2}, {"name": "visits", "arity": 1}],
              actions=[{"name": "visit", "args": ["v"], "effects": [{"fluent": "visits", "args": ["v"], "value": True}]}],
              rules=[rl("R1", "visitor", "(visit v)", "(married patient visitor)")])
    return a, b


AL = {"cov-a": {"husband": "partner_a", "wife": "partner_b"}, "hosp-b": {"patient": "partner_a", "visitor": "partner_b"}}


def test_compose_happy_path():
    a, b = pair()
    c = rc.compose([a, b], AL, "comp", initial=["visits(partner_b)"], notes="n")
    assert [r.name for r in c.roles] == ["partner_a", "partner_b"]
    assert [r.id for r in c.rules] == ["cov_a__R1", "cov_a__R2", "hosp_b__R1"]
    assert c.rules[0].or_else == "cov_a__R2" and c.rules[2].or_else is None
    assert c.members == ["cov-a", "hosp-b"] and c.id == "comp" and c.notes == "n"
    assert {f.name for f in c.fluents} == {"married", "owes", "visits"}
    assert c.initial == ["married(partner_a, partner_b)", "visits(partner_b)"] and c.defaults == {"owes": "false"}
    assert c.expected_properties == {} and "cov-a" in c.source_text and "hosp-b" in c.source_text


def test_alias_renames_everything():
    a, b = pair()
    c = rc.compose([a], {"cov-a": {"husband": "partner_a", "wife": "partner_b"}}, "c1")
    r1 = c.rules[0]
    assert r1.attribute == "partner_a" and r1.var_roles["h"] == "partner_a" and r1.var_roles["w"] == "partner_b"
    assert c.fluents[0].arg_roles == ["partner_a", "partner_b"]
    assert c.initial == ["married(partner_a, partner_b)"]
    c2 = rc.compose([b], {"hosp-b": {"patient": "partner_a"}}, "c2")
    assert c2.rules[0].conditions == "(married partner_a visitor)"


def test_alias_errors():
    a, _ = pair()
    with pytest.raises(rc.ComposeError, match="cov-a.*nope"):
        rc.compose([a], {"cov-a": {"nope": "x"}}, "c")
    with pytest.raises(rc.ComposeError, match="cov-a.*roles"):
        rc.compose([a], {"cov-a": {"husband": "wife"}}, "c")
    with pytest.raises(rc.ComposeError, match="unknown member"):
        rc.compose([a], {"zzz": {}}, "c")


def test_conflicts_name_member_and_field():
    a, b = pair()
    al = AL
    # arity
    b1 = InstitutionJSON.model_validate({**b.model_dump(), "rules": [], "fluents": [
        {"name": "married", "arity": 1}, {"name": "visits", "arity": 1}]})
    with pytest.raises(rc.ComposeError, match=r"hosp-b.*married.*arity"):
        rc.compose([a, b1], al, "c")
    # two typed arg_roles disagree
    b2 = InstitutionJSON.model_validate({**b.model_dump(), "rules": [], "fluents": [
        {"name": "married", "arity": 2, "arg_roles": ["visitor", "patient"]}, {"name": "visits", "arity": 1}]})
    with pytest.raises(rc.ComposeError, match=r"hosp-b.*married.*arg_roles"):
        rc.compose([a, b2], al, "c")
    # derived differs
    def dfl(expr):
        return [{"name": "married", "arity": 2}, {"name": "ok", "arity": 1, "derived": expr, "params": ["x"]},
                {"name": "visits", "arity": 1}]
    a3 = InstitutionJSON.model_validate({**a.model_dump(), "rules": [], "initial": None, "defaults": {}, "actions": [],
                                         "fluents": dfl("(visits x)")})
    b3 = InstitutionJSON.model_validate({**b.model_dump(), "rules": [], "actions": [], "fluents": dfl("(not (visits x))")})
    with pytest.raises(rc.ComposeError, match=r"hosp-b.*ok.*derived"):
        rc.compose([a3, b3], al, "c")
    # action differs
    b4 = InstitutionJSON.model_validate({**b.model_dump(), "rules": [], "actions": [
        {"name": "pay", "args": ["h"], "effects": []}]})
    with pytest.raises(rc.ComposeError, match=r"hosp-b.*action 'pay'"):
        rc.compose([a, b4], al, "c")
    # default differs
    b5 = InstitutionJSON.model_validate({**b.model_dump(), "rules": [], "defaults": {"owes": "true"},
                                         "fluents": b.model_dump()["fluents"] + [{"name": "owes", "arity": 1}]})
    with pytest.raises(rc.ComposeError, match=r"hosp-b.*defaults.*owes"):
        rc.compose([a, b5], al, "c")


def test_typed_beats_untyped_either_order():
    a, b = pair()
    for ms in ([a, b], [b, a]):
        c = rc.compose(ms, AL, "c")
        assert next(f for f in c.fluents if f.name == "married").arg_roles == ["partner_a", "partner_b"]


def test_validate_institution_failure_surfaces():
    a, _ = pair()
    bad = InstitutionJSON.model_validate({**a.model_dump(), "rules": [rl("R1", "husband", "(pay h w)", "(zzz h)")]})
    with pytest.raises(rc.ComposeError, match="zzz"):
        rc.compose([bad], {}, "c")


def test_freeze_preserves_aim_types_under_alias():
    # `h`/`w` resolve by prefix in the member; after aliasing + a role that makes `h` ambiguous they must still type
    a, b = pair()
    extra = entry("extra", ["hunter", "wild"], fluents=[{"name": "seen", "arity": 1}])
    amap = AL["cov-a"]
    pre = {r.id: rc._typer(a).aim_types(r) for r in a.rules}
    c = rc.compose([a, b, extra], AL, "c")
    Reference(c)
    t = rc._typer(c)
    for r in c.rules:
        if r.id.startswith("cov_a__"):
            want = {k: (amap.get(v, v) if v else v) for k, v in pre[r.id.split("__", 1)[1]].items()}
            assert t.aim_types(r) == want


def test_applicable_which_members_leniency():
    a, b = pair()
    c = rc.compose([a, b], AL, "comp")
    # validators for goods are heavy and irrelevant here; build a goods-kind property directly
    p = Property.model_construct(name="pp", kind="goods", gloss="", formal="(undeclared_zz partner_a t)",
                                 scope=None, check=None, family="pp", polarity="good", encoders=[], contested=[],
                                 entries=["cov-a"], subject="(married partner_a partner_b t)", primary_measure=None, primary_measure_reason=None)
    plain = c.model_copy(update={"members": []})
    _w, na_plain = applicable_which(plain, {"pp": p})
    _w2, na_comp = applicable_which(c, {"pp": p})
    assert na_plain == ["pp"] and na_comp == []


def test_same_member_twice_distinct_prefixes():
    _, b = pair()
    c = rc.compose([b, b], {"hosp-b": {"patient": "p1", "visitor": "p2"}, "hosp-b_2": {"patient": "p2", "visitor": "p3"}}, "twice")
    assert [r.id for r in c.rules] == ["hosp_b__R1", "hosp_b_2__R1"]
    assert c.members == ["hosp-b", "hosp-b"] and [r.name for r in c.roles] == ["p1", "p2", "p3"]
    assert c.rules[1].attribute == "p3" and c.rules[1].conditions == "(married p2 p3)"
    # same alias map on a typed fluent twice is fine; a swapped one is a typed disagreement
    a, _ = pair()
    rc.compose([a, a], {"cov-a": {"husband": "p1", "wife": "p2"}, "cov-a_2": {"husband": "p1", "wife": "p2"}}, "ok")
    with pytest.raises(rc.ComposeError, match="cov-a_2.*arg_roles"):
        rc.compose([a, a], {"cov-a": {"husband": "p1", "wife": "p2"}, "cov-a_2": {"husband": "p2", "wife": "p1"}}, "bad")


def test_cli_compose(tmp_path, capsys):
    a, b = pair()
    p = tmp_path / "i.json"
    p.write_text(json.dumps([a.model_dump(mode="json"), b.model_dump(mode="json")]))
    pp = tmp_path / "p.json"
    pp.write_text("[]")
    args = cli_rules.build_parser().parse_args(
        ["rules", "compose", "--id", "c", "--member", "cov-a", "--member", "hosp-b", "--alias", "cov-a:husband=partner_a",
         "--alias", "cov-a:wife=partner_b", "--alias", "hosp-b:patient=partner_a", "--alias", "hosp-b:visitor=partner_b",
         "--institutions", str(p), "--properties", str(pp), "--json"])
    assert args.fn(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["members"] == ["cov-a", "hosp-b"] and [r["id"] for r in out["rules"]][0] == "cov_a__R1"
    bad = cli_rules.build_parser().parse_args(
        ["rules", "compose", "--id", "c", "--member", "cov-a", "--alias", "cov-a:nope=x", "--institutions", str(p), "--properties", str(pp)])
    assert bad.fn(bad) == 2 and "cov-a" in capsys.readouterr().err
