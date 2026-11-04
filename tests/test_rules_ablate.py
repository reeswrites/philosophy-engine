"""Rule ablation (philengine.rules_ablate): metamorphic properties on a tiny exit fixture."""
import json

import pytest

from philengine import rules_ablate as ra
from philengine import rules_checks as rc
from philengine.schemas_rules import InstitutionJSON, Property, RulesLoadError, load_properties

from .test_rules_meta import rename


def keeper(extra_rules=()):
    """A keeper may seize a free ward; a held ward must not exit (R2, disability); a free ward may exit (R3)."""
    inst = InstitutionJSON.model_validate({
        "id": "t-keeper",
        "roles": [{"name": "keeper"}, {"name": "ward"}],
        "fluents": [{"name": "held", "arity": 1, "arg_roles": ["ward"]}],
        "actions": [
            {"name": "seize", "args": ["k", "w"], "arg_roles": ["keeper", "ward"],
             "effects": [{"fluent": "held", "args": ["w"], "value": True}]},
            {"name": "exit", "args": ["w"], "arg_roles": ["ward"],
             "effects": [{"fluent": "held", "args": ["w"], "value": False}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "keeper", "deontic": "may", "aim": "(seize k w)", "conditions": "(not (held w))", "strand": "rival"},
            {"id": "R2", "attribute": "ward", "deontic": "must_not", "aim": "(exit w)", "conditions": "(held w)",
             "or_else": None, "strand": "tying"},
            {"id": "R3", "attribute": "ward", "deontic": "may", "aim": "(exit w)", "conditions": "true", "strand": "rival"},
            *extra_rules,
        ],
        "expected_properties": {"held_persists": "persists"},
    })
    props = {
        "held_persists": Property(name="held_persists", kind="freedom", formal="(held ward t)"),
        "held_reachable": Property(name="held_reachable", kind="structure", formal="(held ward t)"),
        "ghost": Property(name="ghost", kind="goods", formal="(unknown_fluent ward t)"),
    }
    return inst, props


UNF = ra.UNFREEDOM | {"held_persists", "held_reachable", "held2_persists"}


def keeper_free():
    """keeper with held_reachable promoted to a freedom property, so prohibiting seize (R1) moves it reachable>open."""
    inst, props = keeper()
    props["held_reachable"] = props["held_reachable"].model_copy(update={"kind": "freedom"})
    return inst, props


def loads(res):
    return {a.rule_id: (a.load_freedom, a.load_goods, a.permission_removed, sorted((b, c) for _, b, c in a.flips),
                        a.inconsistent_after) for a in res}


def test_kind_required_by_loader(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps([{"name": "x", "formal": "(held ward t)"}]))
    with pytest.raises(RulesLoadError, match="kind"):
        load_properties(p)
    p.write_text(json.dumps([{"name": "x", "kind": "freedom", "formal": "(held ward t)"}]))
    assert load_properties(p)["x"].kind == "freedom"


def test_basic_flip_and_applicability():
    inst, props = keeper()
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=4)}
    a2 = res["R2"]
    assert a2.flips == [("held_persists", "persists", "fails")] and a2.load_freedom == 1 and a2.load_goods == 0
    assert a2.not_applicable == ["ghost"] and a2.applicable == 2  # not only expected_properties; ghost skipped
    assert res["R1"].deregulated and not res["R1"].permission_removed


def test_non_expected_property_is_read():
    inst, props = keeper()
    assert "held_reachable" not in inst.expected_properties
    which, _ = ra.applicable_which(inst, props)
    assert which == {"held_persists": ["persists"], "held_reachable": ["reachable"]}


def test_a_rename_preserves_every_load():
    inst, props = keeper()
    before = loads(ra.ablate(inst, props, k=4))
    assert any(v[0] > 0 for v in before.values())  # non-vacuous: some rule carries load
    names = [r.name for r in inst.roles] + [f.name for f in inst.fluents] + [a.name for a in inst.actions]
    inst2, props2 = rename(inst, props, {n: f"zz{i}_{n[::-1]}" for i, n in enumerate(names)})
    assert loads(ra.ablate(inst2, props2, k=4)) == before


def test_b_inert_rule_changes_no_load():
    inst, props = keeper()
    base = loads(ra.ablate(inst, props, k=4))
    inert = {"id": "R9", "attribute": "ward", "deontic": "must", "aim": "(held w)", "conditions": "(held w)",
             "or_else": None, "strand": "tying"}
    inst2, _ = keeper([inert])
    assert rc.run_all(inst2, props, k=4, which={"held_persists": ["persists"]}).inert == ["R9"]
    res = loads(ra.ablate(inst2, props, k=4))
    assert res.pop("R9")[0] == 0 and res == base


def test_c_deleting_exit_must_not_only_opens_exit(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)  # treat the fixture property as an unfreedom
    inst, props = keeper()
    for k in (3, 4, 5):
        a = next(a for a in ra.ablate(inst, props, k=k) if a.rule_id == "R2")
        assert a.deontic == "must_not" and a.flips == [("held_persists", "persists", "fails")]
        assert (a.load_freedom, a.load_freedom_up, a.load_freedom_down) == (1, 1, 0)
        assert a.flip_directions == {"held_persists": "freedom_up"}


def test_direction_unsigned_without_polarity():
    inst, props = keeper()
    a = next(a for a in ra.ablate(inst, props, k=4) if a.rule_id == "R2")
    assert (a.load_freedom, a.load_freedom_unsigned, a.load_freedom_up) == (1, 1, 0)
    assert ra.flip_direction("subject_cannot_exit", "reachable", "open") == "freedom_up"
    assert ra.flip_direction("subject_cannot_exit", "open", "reachable") == "freedom_down"


def test_deregulation_sole_may_is_flagged_not_ranked(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper_free()
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=4) if a.variant == "deleted"}
    assert res["R1"].deregulated and not res["R1"].permission_removed  # sole may on seize
    assert res["R3"].deregulated  # sole may/must on exit (R2 is a must_not: does not regulate)
    assert not res["R2"].deregulated
    summ = ra.summarize({"t-keeper": ra.ablate_multi_k(inst, props, ks=(4,))}, (4,))["entries"]["t-keeper"]
    assert summ["top_rules"] == ["R2"] and set(summ["deregulated_not_ranked"]) == {"R1", "R3"}
    assert summ["offcondition_free_not_ranked"] == ["R1~prohibit"]  # sole regulator, condition (not (held w)): leaks
    assert summ["top_load_freedom_up"] == 1
    assert summ["inconsistent_after"] == 0 and summ["uncounted"] == 0


def test_may_with_other_regulator_is_permission_removed():
    extra = {"id": "R7", "attribute": "ward", "deontic": "may", "aim": "(exit w)", "conditions": "true", "strand": "rival"}
    inst, props = keeper([extra])
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=3)}
    assert res["R3"].permission_removed and not res["R3"].deregulated


def test_orphaned_or_else_listed():
    sanction = {"id": "R9", "attribute": "keeper", "deontic": "may", "aim": "(seize k w)", "conditions": "true", "strand": "rival"}
    soft = {"id": "R8", "attribute": "ward", "deontic": "must_not", "aim": "(exit w)", "conditions": "(held w)",
            "or_else": "R9", "strand": "tying"}
    inst, props = keeper([sanction, soft])
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=3)}
    assert res["R9"].orphaned_or_else == ["R8"] and res["R1"].orphaned_or_else == []


def test_unknown_excluded_by_flag_not_message():
    from philengine.schemas_rules import PropertyResult
    ok = PropertyResult(property="x", check="reachable", verdict="open", reason="no compliant trace ... (not 'safe')")
    unk = PropertyResult(property="x", check="reachable", verdict="open", z3_unknown=True, reason="no compliant trace (not 'safe')")
    assert ra.effective_verdict(ok) == "open" and ra.effective_verdict(unk) is None


def test_d_may_rules_carry_permission_removed():
    inst, props = keeper()
    for a in ra.ablate(inst, props, k=3):
        if a.variant == "deleted":
            assert a.permission_removed == (a.deontic == "may" and not a.deregulated)
        else:
            assert a.permission_removed and a.deontic == "must_not" and not a.deregulated


def test_e_k_disagreement_empty_when_ks_agree():
    inst, props = keeper()
    res = ra.ablate_multi_k(inst, props, ks=(3, 4))
    assert all(m.k_disagreement == [] for m in res)
    assert {m.rule_id for m in res} == {"R1", "R2", "R3", "R1~prohibit", "R3~prohibit"}


def chain(n=7):
    """f1..fn reached one action at a time: `goal` (fn) is reachable within k=8 steps but not within k=6."""
    inst = InstitutionJSON.model_validate({
        "id": "t-chain", "roles": [{"name": "agent"}],
        "fluents": [{"name": f"f{i}", "arity": 1, "arg_roles": ["agent"]} for i in range(1, n + 1)],
        "actions": [{"name": f"a{i}", "args": ["x"], "arg_roles": ["agent"],
                     "effects": [{"fluent": f"f{i}", "args": ["x"], "value": True}]} for i in range(1, n + 1)],
        "rules": [{"id": f"R{i}", "attribute": "agent", "deontic": "may", "aim": f"(a{i} x)",
                   "conditions": "true" if i == 1 else f"(f{i - 1} x)", "strand": "rival"} for i in range(1, n + 1)],
        "expected_properties": {"goal": "reachable"}})
    return inst, {"goal": Property(name="goal", kind="freedom", formal=f"(f{n} agent t)")}


def test_e_k_disagreement_nonempty_when_horizon_matters():
    inst, props = chain()
    res = {m.rule_id: m for m in ra.ablate_multi_k(inst, props, ks=(6, 8))}
    assert res["R7"].k_disagreement == ["goal"]
    # deleting R7 unregulates a7 (always enabled): at k=6 the goal flips open>reachable, at k=8 it was reachable already
    assert res["R7"].by_k[6].flips == [("goal", "open", "reachable")] and res["R7"].by_k[8].flips == []
    assert res["R7"].by_k[6].deregulated


def test_cli_ablate_writes_json(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    from philengine import cli_rules
    inst, props = keeper_free()
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([p.model_dump(mode="json") for p in props.values()]))
    out = tmp_path / "o.json"
    summ = tmp_path / "s.json"
    a = __import__('philengine.cli', fromlist=['x']).build_parser().parse_args(["rules", "ablate", "--k", "3,4", "--institutions", str(tmp_path / "i.json"),
                                             "--properties", str(tmp_path / "p.json"), "--json", str(out), "--summary", str(summ)])
    assert a.fn(a) == 0
    txt = capsys.readouterr().out
    assert "deregulated (action becomes unregulated" in txt and "2 properties applicable, 1 not applicable" in txt
    d = json.loads(out.read_text())
    sd = json.loads(summ.read_text())
    assert sd["entries"]["t-keeper"]["top_rules"] == ["R2"] and sd["totals"]["entries"] == 1
    assert "deregulated, not ranked" in txt and "prohibit leaks off-condition (sole regulator): not ranked" in txt and " mixed " in txt and "check kinds: held_persists=persists" in txt
    assert d["entries"]["t-keeper"]["check_kinds"]["held_persists"] == "persists"
    assert d["ks"] == [3, 4] and d["entries"]["t-keeper"]["rules"][0]["rule_id"]


def test_family_collapses_twin_properties(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", ra.UNFREEDOM | {"held_persists", "held2_persists"})
    inst, props = keeper()
    props["held2_persists"] = Property(name="held2_persists", kind="freedom", formal="(held ward t)")
    assert props["held2_persists"].family == "held2_persists" and props["held_persists"].family == "held_persists"
    a = next(a for a in ra.ablate(inst, props, k=4) if a.rule_id == "R2")
    assert a.load_freedom_up == 2 and a.families_up == ["held2_persists", "held_persists"]
    for n in ("held_persists", "held2_persists"):
        props[n] = props[n].model_copy(update={"family": "held"})
    a = next(a for a in ra.ablate(inst, props, k=4) if a.rule_id == "R2")
    assert len(a.flips) == 2 and (a.load_freedom, a.load_freedom_up) == (1, 1) and a.families_up == ["held"]


R4 = {"id": "R4", "attribute": "keeper", "deontic": "must_not", "aim": "(seize k w)", "conditions": "true",
      "or_else": None, "strand": "tying"}


def keeper_down(mixed=False):
    """keeper + R4 (must_not seize, always): held_reachable is open; deleting R4 makes it reachable (freedom_down)."""
    inst, props = keeper([R4])
    props["held_reachable"] = props["held_reachable"].model_copy(update={"kind": "freedom"})
    if mixed:  # u2 holds_to_k > violated on the same deletion (freedom_up), same family as held_reachable
        props["u2"] = Property(name="u2", kind="freedom", formal="(not (held ward t))", check="invariant")
        for n in ("held_reachable", "u2"):
            props[n] = props[n].model_copy(update={"family": "held"})
    return inst, props


def test_ranking_ignores_down_flips_pipeline(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper_down()
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=4)}
    assert res["R4"].flips == [("held_reachable", "open", "reachable")]
    assert (res["R4"].load_freedom, res["R4"].load_freedom_up, res["R4"].load_freedom_down) == (1, 0, 1)
    summ = ra.summarize({"t": ra.ablate_multi_k(inst, props, ks=(4,))}, (4,))["entries"]["t"]
    assert summ["top_rules"] == [] and summ["top_load_freedom_up"] == 0  # the only flip is down: R4 not ranked


def test_mixed_family_counts_in_neither_direction(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF | {"u2"})
    inst, props = keeper_down(mixed=True)
    a = next(a for a in ra.ablate(inst, props, k=4) if a.rule_id == "R4")
    assert a.flip_directions == {"held_reachable": "freedom_down", "u2": "freedom_up"}
    assert (a.load_freedom, a.load_freedom_up, a.load_freedom_down, a.load_freedom_mixed) == (1, 0, 0, 1)
    assert a.families_mixed == ["held"] and a.families_up == [] and a.families_down == []


def test_prohibit_leak_sole_regulator_vs_true_condition(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper_free()
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=4)}
    assert res["R1~prohibit"].offcondition_free and res["R1~prohibit"].load_freedom_up == 1  # loads still shown
    assert not res["R3~prohibit"].offcondition_free  # condition true: the must_not binds everywhere
    assert not any(a.offcondition_free for a in res.values() if a.variant == "deleted")
    extra = {"id": "R7", "attribute": "keeper", "deontic": "may", "aim": "(seize k w)", "conditions": "true", "strand": "rival"}
    inst2, props2 = keeper([extra])
    assert not next(a for a in ra.ablate(inst2, props2, k=3) if a.rule_id == "R1~prohibit").offcondition_free  # not sole
    summ = ra.summarize({"t": ra.ablate_multi_k(inst, props, ks=(4,))}, (4,))["entries"]["t"]
    assert "R1~prohibit" not in summ["top_rules"] and summ["offcondition_free_not_ranked"] == ["R1~prohibit"]


def test_prohibit_variant_of_sole_may_is_offcondition_and_unranked(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper_free()
    res = {a.rule_id: a for a in ra.ablate(inst, props, k=4)}
    assert res["R1"].deregulated and res["R1"].variant == "deleted"
    p = res["R1~prohibit"]
    assert p.variant == "prohibited" and not p.deregulated and p.load_freedom_up == 1 and p.offcondition_free
    assert p.flips == [("held_reachable", "reachable", "open")]
    inst2, orphan = ra.prohibited(inst, "R1")
    r = next(r for r in inst2.rules if r.id == "R1~prohibit")
    assert (r.deontic, r.attribute, r.aim, r.conditions, r.or_else, r.strand) == \
        ("must_not", "keeper", "(seize k w)", "(not (held w))", None, "rival") and orphan == []


def test_explicit_property_check_wins_and_source_reported():
    inst, props = keeper()
    props["held_reachable"] = props["held_reachable"].model_copy(update={"check": "invariant"})
    which, _ = ra.applicable_which(inst, props)
    assert which["held_reachable"] == ["invariant"] and which["held_persists"] == ["persists"]
    assert ra.check_source("held_reachable", inst, {}, props) == ("invariant", "property")
    assert ra.check_source("held_persists", inst, {}, props) == ("persists", "expected")
    assert ra.check_source("x_persists", inst, {}, props) == ("persists", "suffix")
    assert ra.check_source("x", inst, {"x": "invariant"}, props) == ("invariant", "majority")
    assert ra.flip_direction("care_duty_on_women", "persists", "fails") == "freedom_up"
    assert ra.flip_direction("care_duty_on_women", "fails", "persists") == "freedom_down"


def test_sole_must_not_deleted_is_ranked_not_deregulated(monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper()
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] != "R3"]  # R2 (must_not exit) is now the only rule on exit
    inst = InstitutionJSON.model_validate(d)
    a = next(a for a in ra.ablate(inst, props, k=4) if a.rule_id == "R2")
    assert a.sole_rule and not a.deregulated
    assert a.flip_directions == {"held_persists": "freedom_up"} and a.load_freedom_up == 1
    summ = ra.summarize({"t": ra.ablate_multi_k(inst, props, ks=(4,))}, (4,))["entries"]["t"]
    assert "R2" in summ["top_rules"] and "R2" not in summ["deregulated_not_ranked"]


def test_spawn_workers_match_serial(monkeypatch):
    """workers=2 over a spawned pool returns exactly what workers=1 returns, rows in the same order, for ablate and ablate_multi_k."""
    from philengine.abm import parallel
    monkeypatch.setenv("PHIL_START_METHOD", "spawn")
    inst, props = keeper_free()
    s1 = ra.ablate(inst, props, 6, workers=1)
    with parallel.pool(2) as n:
        assert n == 2 and parallel._ACTIVE_METHOD[0] == "spawn"
        s2 = ra.ablate(inst, props, 6, workers=None)
        m2 = ra.ablate_multi_k(inst, props, (6, 8), workers=None)
    assert [a.to_dict() for a in s1] == [a.to_dict() for a in s2] and len(s1) == 5  # R1, R1~prohibit, R2, R3, R3~prohibit
    m1 = ra.ablate_multi_k(inst, props, (6, 8))
    assert [m.to_dict() for m in m1] == [m.to_dict() for m in m2]


def test_default_capacity_sole_may_is_not_deregulated():
    inst, props = keeper_free()
    d = inst.model_dump()
    for a in d["actions"]:
        if a["name"] == "exit":
            a["default_capacity"] = True
    cap = InstitutionJSON.model_validate(d)
    assert {a.rule_id: a.deregulated for a in ra.ablate(cap, props, k=4) if a.variant == "deleted"}["R3"] is False
    assert {a.rule_id: a.deregulated for a in ra.ablate(inst, props, k=4) if a.variant == "deleted"}["R3"] is True  # power action


def test_cli_ablate_scoreboard_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "UNFREEDOM", UNF)
    inst, props = keeper_free()
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([p.model_dump(mode="json") for p in props.values()]))
    board, summ = tmp_path / "board.md", tmp_path / "s.json"
    from philengine.cli import build_parser

    def run(*extra):
        a = build_parser().parse_args(["rules", "ablate", "--k", "3,4", "--institutions", str(tmp_path / "i.json"),
                                       "--properties", str(tmp_path / "p.json"), "--scoreboard", str(board), *extra])
        assert a.fn(a) == 0

    run("--summary", str(summ))
    run("--prev", str(summ))
    lines = board.read_text().splitlines()
    assert sum(l.startswith("| date ") for l in lines) == 1 and len(lines) == 4
    first, second = ([c.strip() for c in l.strip("|").split("|")] for l in lines[2:])
    assert first[2] == "rules ablate" and first[3] == "1" and first[-1] == "-"
    assert second[-1] == "0"
