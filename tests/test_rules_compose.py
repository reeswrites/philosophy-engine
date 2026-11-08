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
    assert vr["R1"] == {"z": "wife"}
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
    assert out[0]["entry"] == "toy" and out[0]["var_roles"]["R1"] == {"z": "wife"}
    assert {"entry", "rule", "variable", "role", "action", "existing"} <= set(out[0]["rows"][0])
