"""ADR 0013 amendment 2026-11-05: `ActionDecl.liberty`. A liberty action is (enabled ...) unless a disability bars it,
whether or not a may/must names it; a power action (default) is enabled only when a rule grants it. Both lowerings."""
import z3

from philengine import rules_ablate as ra
from philengine import rules_checks as rc
from philengine import rules_lower as rl
from philengine.rules_reference import Reference
from philengine.schemas_rules import InstitutionJSON, Property

ACT = ("contract", ("person",))


def lib(liberty=True, bar=True, grant=False) -> InstitutionJSON:
    """`contract` toggles nothing; `bind`/`free` toggle bound(person); a disability bars contract while bound."""
    rules = [
        {"id": "R1", "attribute": "person", "deontic": "may", "aim": "(bind p)", "conditions": "(not (bound p))", "strand": "rival"},
        {"id": "R2", "attribute": "person", "deontic": "may", "aim": "(free p)", "conditions": "(bound p)", "strand": "rival"},
    ]
    if bar:
        rules.append({"id": "R3", "attribute": "person", "deontic": "must_not", "aim": "(contract p)",
                      "conditions": "(bound p)", "or_else": None, "strand": "tying"})
    if grant:
        rules.append({"id": "R4", "attribute": "person", "deontic": "may", "aim": "(contract p)",
                      "conditions": "true", "strand": "rival"})
    return InstitutionJSON.model_validate({
        "id": "t-liberty",
        "roles": [{"name": "person"}],
        "fluents": [{"name": "bound", "arity": 1, "arg_roles": ["person"]},
                    {"name": "can_contract", "arity": 1, "arg_roles": ["person"], "params": ["x"],
                     "derived": "(enabled contract x)"}],
        "actions": [
            {"name": "bind", "args": ["p"], "arg_roles": ["person"], "effects": [{"fluent": "bound", "args": ["p"], "value": True}]},
            {"name": "free", "args": ["p"], "arg_roles": ["person"], "effects": [{"fluent": "bound", "args": ["p"], "value": False}]},
            {"name": "contract", "args": ["p"], "arg_roles": ["person"], "effects": [], "liberty": liberty},
        ],
        "rules": rules,
    })


NEVER = Property(name="never", kind="structure", formal="(forall ((x agent)) (=> (not (bound x t)) (not (can_contract x t))))")
CAN = Property(name="can", kind="structure", formal="(can_contract person t)")
BARRED = Property(name="barred", kind="structure", formal="(and (bound person t) (can_contract person t))")


def verdicts(inst, k=3):
    rep = rc.run_all(inst, {"never": NEVER, "can": CAN, "barred": BARRED}, k=k,
                     which={"never": ["invariant"], "can": ["reachable"], "barred": ["reachable"]})
    return rep, {r.property: r.verdict for r in rep.results}


def z_enabled(inst, t, k=3):
    return rl.ground(inst, k=k), t


def test_liberty_without_rules_is_enabled_and_not_vacuous():
    inst = lib(bar=False)
    assert rl.validate_institution(inst) == []
    G = rl.ground(inst, k=3)
    assert all(z3.is_true(z3.simplify(G.enabled("contract", ("person",), t))) for t in range(4))
    rep, v = verdicts(inst)
    assert v["never"] == "violated" and v["can"] == "reachable"
    r = next(r for r in rep.results if r.property == "never")
    assert not r.vacuous


def test_liberty_disability_bars_only_while_its_condition_holds():
    inst = lib()
    G = rl.ground(inst, k=3)
    bound = lambda t: G.fluent("bound", ("person",), t)
    en = lambda t: G.enabled("contract", ("person",), t)
    for t in range(4):
        s = z3.Solver(); s.add(G.system(), bound(t), en(t)); assert s.check() == z3.unsat
        s = z3.Solver(); s.add(G.system(), z3.Not(bound(t)), z3.Not(en(t))); assert s.check() == z3.unsat
        if t:
            s = z3.Solver(); s.add(G.system(), bound(t)); assert s.check() == z3.sat
    _, v = verdicts(inst)
    assert v["can"] == "reachable" and v["barred"] == "open" and v["never"] == "violated"


def test_power_action_without_grant_is_constant_false_unlike_liberty():
    p = lib(liberty=False)
    G = rl.ground(p, k=3)
    assert all(z3.is_false(z3.simplify(G.enabled("contract", ("person",), t))) for t in range(4))
    _, v = verdicts(p)
    assert v["never"] == "holds_to_k" and v["can"] == "open"
    _, vl = verdicts(lib())
    assert vl != v and vl["never"] != v["never"]
    # a grant on the power action restores enablement; on a liberty it changes nothing
    for liberty in (False, True):
        g = rl.ground(lib(liberty=liberty, grant=True), k=3)
        s = z3.Solver(); s.add(g.system(), z3.Not(g.fluent("bound", ("person",), 1)), z3.Not(g.enabled("contract", ("person",), 1)))
        assert s.check() == z3.unsat


def test_reference_agrees_with_the_z3_lowering():
    for make in (lambda: lib(bar=False), lib, lambda: lib(liberty=False), lambda: lib(liberty=False, grant=True),
                 lambda: lib(grant=True)):
        inst = make()
        props = {"never": NEVER, "can": CAN, "barred": BARRED}
        ref = Reference(inst, k=3)
        for name, kind in (("never", "invariant"), ("can", "reachable"), ("barred", "reachable")):
            _, eng = verdicts(inst)
            assert ref.verdict(props[name], kind) == eng[name], (name, inst.actions[2].liberty, [r.id for r in inst.rules])
    # direct power(): liberty enabled iff not bound; power action without grant never
    for bound_on in (False, True):
        st = frozenset({("bound", ("person",))}) if bound_on else frozenset()
        assert Reference(lib(), k=2).power(st, *ACT) == (not bound_on)
        assert Reference(lib(bar=False), k=2).power(st, *ACT) is True
        assert Reference(lib(liberty=False), k=2).power(st, *ACT) is False


def test_deleting_the_sole_must_not_on_a_liberty_flips_the_power_property():
    inst = lib()
    # a person who is bound from the start and can never be freed: the disability R3 bars the liberty at every
    # step, so "no power while bound" is trivially fine; the property below says the liberty is NEVER enabled
    props = {"never": Property(name="never", kind="structure", formal="(forall ((x agent)) (=> (bound x t) (not (can_contract x t))))")}
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] not in ("R1", "R2")]
    d["initial"] = ["(bound person)"]
    d["expected_properties"] = {"never": "holds_to_k"}
    inst2 = InstitutionJSON.model_validate(d)
    res = {a.rule_id: a for a in ra.ablate(inst2, props, k=3) if a.variant == "deleted"}
    assert res["R3"].flips == [("never", "holds_to_k", "violated")]


def test_unregulated_warning_not_raised_for_liberty():
    p = {"can": CAN}
    msgs = lambda inst: [w for w in rc.run_all(inst, p, k=2, which={"can": ["reachable"]}).warnings if "no may/must rule regulates" in w]
    assert msgs(lib(liberty=True)) == []
    m = msgs(lib(liberty=False))
    assert len(m) == 1 and "liberty" in m[0] and "never enabled" in m[0]
