"""Role cardinality (RoleDecl.count; CL plans/cardinality.md Q1): invisible at count 1, instance grounding above it."""
import pytest
import z3

from philengine import rules_lower as rl
from philengine import rules_reference as rf
from philengine import rules_roles as rr
from philengine import sexpr as sx
from philengine.schemas_rules import InstitutionJSON

from .test_rules_lower import tiny


def toy(wives: int = 2, **over) -> InstitutionJSON:
    """A husband may marry a wife (any number of times over different wives); married is typed [husband, wife]."""
    d = {
        "id": "toy", "roles": [{"name": "husband"}, {"name": "wife", "count": wives}],
        "fluents": [{"name": "married", "arity": 2, "arg_roles": ["husband", "wife"]}],
        "actions": [{"name": "marry", "args": ["h", "w"],
                     "effects": [{"fluent": "married", "args": ["h", "w"], "value": True}]}],
        "rules": [{"id": "R1", "attribute": "husband", "deontic": "may", "aim": "(marry h w)", "conditions": "true",
                   "or_else": None, "strand": "rival"}],
    }
    d.update(over)
    return InstitutionJSON.model_validate(d)


def solve(G, *extra) -> bool:
    s = z3.Solver()
    s.add(G.system(), *extra)
    return s.check() == z3.sat


def prop(G, text, t):
    return rl.lower_property(sx.parse(text), G, t)


# ---------------------------------------------------------------- count 1 is invisible
def test_count_one_grounds_identically():
    inst = tiny()  # golden values captured from the pre-change engine (main b5fd019)
    R, G = rf.Reference(inst, k=3), rl.ground(inst, k=3)
    assert R.agents == G.agents == ["boss", "worker"]
    assert R.tuples["employed"] == [("boss",), ("worker",)] == G.fluent_tuples["employed"]
    assert {r.id: R.aim_types(r) for r in inst.rules} == {"R1": {"b": "boss", "w": "worker"}, "R2": {"w": "worker"}}
    assert [(x.rule_id, x.action, x.args) for x in R.rule_insts] == [("R1", "pay", ("boss", "worker")), ("R2", "quit", ("worker",))]
    assert [(x.rule.id, x.action, x.args) for x in G.rule_instances] == [("R1", "pay", ("boss", "worker")), ("R2", "quit", ("worker",))]
    assert R.action_insts == [("hire", ("boss", "worker")), ("pay", ("boss", "worker")), ("quit", ("worker",))]
    assert len(G.fluent_vars) + len(G.action_vars) + len(G.violation_vars) == 33
    assert "employed(boss)@0" in {str(v) for v in G.fluent_vars.values()}


def test_default_count_and_json():
    r = tiny().roles[0]
    assert r.count == 1 and r.instance_names == ["boss"] and r.model_dump()["count"] == 1
    assert toy().roles[1].instance_names == ["wife_1", "wife_2"]
    with pytest.raises(ValueError):
        InstitutionJSON.model_validate({**toy().model_dump(), "roles": [{"name": "h"}, {"name": "w", "count": 0}]})


# ---------------------------------------------------------------- two wives
def test_two_wives_typed_fluent_and_agents():
    inst = toy()
    R, G = rf.Reference(inst, k=2), rl.ground(inst, k=2)
    want = [("husband", "wife_1"), ("husband", "wife_2")]
    assert R.agents == G.agents == ["husband", "wife_1", "wife_2"]
    assert R.tuples["married"] == want == G.fluent_tuples["married"]
    assert R.role_of["wife_2"] == "wife" == G.role_of["wife_2"]
    # aim_types slot 0 stays the attribute role; the actor ranges over its instances; distinct, typed bindings
    assert R.aim_types(inst.rules[0]) == {"h": "husband", "w": "wife"}
    assert [x.args for x in R.rule_insts] == want == [x.args for x in G.rule_instances]
    assert R.action_insts == [("marry", a) for a in want]
    assert G.action_instances["marry"] == want


def test_distinctness_within_a_tuple_with_a_repeated_role():
    inst = toy(actions=[{"name": "swap", "args": ["a", "b"], "arg_roles": ["wife", "wife"], "effects": []}],
               rules=[], fluents=[{"name": "f", "arity": 1}])
    assert rf.Reference(inst, k=1).action_insts == [("swap", ("wife_1", "wife_2")), ("swap", ("wife_2", "wife_1"))]
    assert rl.ground(inst, k=1).action_instances["swap"] == [("wife_1", "wife_2"), ("wife_2", "wife_1")]


def test_forall_exists_range_over_both_wives():
    G = rl.ground(toy(), k=2)
    only_w2 = "(exists ((w agent)) (and (married husband w t) (= w wife_2)))"
    assert solve(G, prop(G, only_w2, 1))
    # wife_2 can be married while wife_1 is not: the forall sees each instance separately
    assert solve(G, prop(G, "(forall ((w agent)) (not (and (married husband w t) (= w wife_1))))", 1), prop(G, only_w2, 1))
    assert not solve(G, prop(G, "(forall ((w agent)) (not (married husband w t)))", 1), prop(G, only_w2, 1))


def test_atmost_one_vs_two():
    G = rl.ground(toy(), k=2)
    two = "(atmost 2 ((w agent)) (married husband w t))"
    one = "(atmost 1 ((w agent)) (married husband w t))"
    assert not solve(G, z3.Not(prop(G, two, 2)))  # two wives: both can be married, never three
    assert solve(G, z3.Not(prop(G, one, 2)))  # but two is more than one
    assert solve(G, prop(G, "(atleast 2 ((w agent)) (married husband w t))", 2))
    assert not solve(G, prop(G, "(atleast 3 ((w agent)) (married husband w t))", 2))


def test_atmost_in_a_rule_condition_caps_marriages():
    cap = {"id": "R2", "attribute": "husband", "deontic": "must_not", "aim": "(marry h w)",
           "conditions": "(atleast 1 ((x agent)) (married h x))", "or_else": None, "strand": "rival"}
    inst = toy(rules=[*[r.model_dump() for r in toy().rules], cap])
    G = rl.ground(inst, k=3)
    assert not solve(G, prop(G, "(atleast 2 ((w agent)) (married husband w t))", 3))
    assert solve(G, prop(G, "(atleast 1 ((w agent)) (married husband w t))", 3))
    R = rf.Reference(inst, k=2)
    st = frozenset({("married", ("husband", "wife_1"))})
    assert R.holds(st, sx.parse("(atleast 1 ((x agent)) (married husband x))"), {})
    assert not R.holds(frozenset(), sx.parse("(atleast 1 ((x agent)) (married husband x))"), {})
    assert R.holds(st, sx.parse("(atmost 1 ((x agent)) (married husband x))"), {})
    # the reference agrees: after one marriage the second is not a compliant step
    assert R.compliant_step(frozenset(), frozenset({("marry", ("husband", "wife_2"))})) == []
    assert R.compliant_step(st, frozenset({("marry", ("husband", "wife_2"))})) != []


def test_sexpr_roundtrip_and_errors():
    a = sx.parse("(atmost 2 ((x agent) (y agent)) (p x y))")
    assert isinstance(a, sx.Count) and a.n == 2 and sx.to_sexpr(a) == "(atmost 2 ((x agent) (y agent)) (p x y))"
    assert sx.parse(sx.to_sexpr(a)) == a
    for bad in ("(atmost x ((a agent)) (p a))", "(atmost 2 (p a))", "(atleast ((a agent)) (p a))"):
        with pytest.raises(sx.ParseError):
            sx.parse(bad)


def test_z3_variable_count_two_wife_toy_k6():
    G = rl.ground(toy(), k=6)
    assert len(G.fluent_vars) == 2 * 7 and len(G.action_vars) == 2 * 6  # 2 married tuples, 2 marry instances


# ---------------------------------------------------------------- errors, ceiling, initial
def test_literal_role_with_count_above_one_is_an_error():
    lit = toy(actions=[{"name": "give", "args": ["h", "wife"], "effects": []}], rules=[])
    with pytest.raises(rl.LowerError, match="name an instance or use a variable"):
        rl.ground(lit, k=1)
    with pytest.raises(rf.RefError, match="name an instance or use a variable"):
        rf.Reference(lit, k=1)
    rl.ground(toy(1, actions=lit.model_dump()["actions"], rules=[]), k=1)  # count 1: a literal is fine, unchanged


def test_ceiling_and_env(monkeypatch):
    inst = toy(4)
    with pytest.raises(rl.LowerError, match="ceiling 3"):
        rl.ground(inst, k=1)
    with pytest.raises(rf.RefError, match="PHIL_MAX_ROLE_COUNT"):
        rf.Reference(inst, k=1)
    monkeypatch.setenv("PHIL_MAX_ROLE_COUNT", "4")
    assert rl.ground(inst, k=1).agents == ["husband", "wife_1", "wife_2", "wife_3", "wife_4"]


def _with_initial(*lits):
    return toy(initial=list(lits), initial_free=[])


def test_initial_names_an_instance():
    inst = _with_initial("married(husband, wife_2)")
    assert rl.validate_institution(inst) == []
    G = rl.ground(inst, k=1)
    assert not solve(G, z3.Not(G.fluent("married", ("husband", "wife_2"), 0)))
    assert not solve(G, G.fluent("married", ("husband", "wife_1"), 0))
    R = rf.Reference(inst, k=1)
    assert R.initial_split()[0] == {("married", ("husband", "wife_2"))}


def test_initial_role_name_flag_both_ways(monkeypatch):
    inst = _with_initial("married(husband, wife)")
    assert rr.INITIAL_ROLE_EVERY_INSTANCE is False  # default: error
    with pytest.raises(rl.LowerError, match="name an instance"):
        rl.ground(inst, k=1)
    with pytest.raises(rf.RefError, match="name an instance"):
        rf.Reference(inst, k=1).initial_split()
    monkeypatch.setattr(rr, "INITIAL_ROLE_EVERY_INSTANCE", True)
    G = rl.ground(inst, k=1)
    for w in ("wife_1", "wife_2"):
        assert not solve(G, z3.Not(G.fluent("married", ("husband", w), 0)))
    assert rf.Reference(inst, k=1).initial_split()[0] == {("married", ("husband", "wife_1")), ("married", ("husband", "wife_2"))}
    # count 1 role name in initial: always itself, flag or not
    assert rr.expand_initial(toy(1), "married", ("husband", "wife")) == [("married", ("husband", "wife"))]


def test_property_naming_a_multi_instance_role_literally_is_an_error():
    from philengine.schemas_rules import Property
    p = Property.model_construct(name="bad", formal="(married husband wife t)")
    errs, _ = rl.validate_property(p, toy())
    assert any("free variables" in e for e in errs)
