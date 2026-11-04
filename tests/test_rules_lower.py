import pytest
import z3

from philengine import rules_lower as rl
from philengine.schemas_rules import InstitutionJSON, Property, load_institutions, load_properties, default_paths


def tiny(**over) -> InstitutionJSON:
    """2-rule institution: the boss must pay an employed worker; an employed worker must not quit."""
    d = {
        "id": "tiny", "roles": [{"name": "boss"}, {"name": "worker"}],
        "fluents": [{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1}],
        "actions": [
            {"name": "hire", "args": ["b", "w"], "effects": [{"fluent": "employed", "args": ["w"], "value": True}]},
            {"name": "pay", "args": ["b", "w"], "effects": [{"fluent": "paid", "args": ["w"], "value": True}]},
            {"name": "quit", "args": ["w"], "effects": [{"fluent": "employed", "args": ["w"], "value": False}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "boss", "deontic": "must", "aim": "(pay b w)", "conditions": "(employed w)",
             "or_else": None, "strand": "superadditive"},
            {"id": "R2", "attribute": "worker", "deontic": "must_not", "aim": "(quit w)", "conditions": "(employed w)",
             "or_else": "R1", "strand": "rival"},
        ],
    }
    d.update(over)
    return InstitutionJSON.model_validate(d)


def test_validate_ok_and_true_condition():
    inst = tiny()
    assert rl.validate_institution(inst) == []
    assert rl.parse_condition("true") is None
    assert rl.parse_condition(" true ") is None
    inst2 = tiny(rules=[*[r.model_dump() for r in inst.rules],
                        {"id": "R3", "attribute": "boss", "deontic": "may", "aim": "(hire b w)", "conditions": "true",
                         "or_else": None, "strand": "tying"}])
    assert rl.validate_institution(inst2) == []


def test_validate_errors_are_readable():
    inst = tiny(rules=[{"id": "R1", "attribute": "nobody", "deontic": "must", "aim": "(fire b w)",
                        "conditions": "(employed w x)", "or_else": "R9", "strand": "tying"}])
    errs = rl.validate_institution(inst)
    joined = "\n".join(errs)
    assert "attribute 'nobody'" in joined
    assert "undeclared action 'fire'" in joined
    assert "or_else 'R9'" in joined
    assert "arity 1" in joined
    with pytest.raises(rl.LowerError):
        rl.ground(inst)


def test_var_role_heuristic():
    inst = tiny()
    assert rl.var_role("b", inst) == "boss"
    assert rl.var_role("w", inst) == "worker"
    assert rl.var_role("x", inst) is None
    assert rl.var_role("boss", inst) == "boss"


def test_ground_shapes():
    G = rl.ground(tiny(), k=3)
    assert G.agents == ["boss", "worker"]
    assert ("employed", ("worker",), 0) in G.fluent_vars
    assert ("employed", ("worker",), 3) in G.fluent_vars
    assert ("pay", ("boss", "worker"), 2) in G.action_vars
    assert ("pay", ("boss", "worker"), 3) not in G.action_vars  # actions at t < k only
    # typed parameters: pay(worker, boss) is not an instance (b -> boss, w -> worker)
    assert ("boss", "worker") in G.action_instances["pay"]
    assert ("worker", "boss") not in G.action_instances["pay"]
    assert G.exogenous == set()
    assert z3.Solver().check(G.system()) == z3.sat


def test_frame_axioms_persist_and_effects_apply():
    G = rl.ground(tiny(), k=3)
    s = z3.Solver()
    s.add(G.system())
    # empty init: nothing employed at 0; hire at 0 -> employed at 1; must persist to 3 (quit forbidden while employed)
    s.add(G.action("hire", ("boss", "worker"), 0))
    assert s.check() == z3.sat
    m = s.model()
    assert not z3.is_true(m.eval(G.fluent("employed", ("worker",), 0)))
    for t in (1, 2, 3):
        assert z3.is_true(m.eval(G.fluent("employed", ("worker",), t), model_completion=True))
    # obligation: employed at 1 forces pay at 1, so paid at 2
    assert z3.is_true(m.eval(G.action("pay", ("boss", "worker"), 1), model_completion=True))
    assert z3.is_true(m.eval(G.fluent("paid", ("worker",), 2), model_completion=True))


def test_property_lowering_quantifiers_and_succ():
    G = rl.ground(tiny(), k=2)
    from philengine import sexpr as sx
    p = sx.parse("(exists ((w agent)) (and (employed w t) (exists ((t2 step)) (and (succ t t2) (paid w t2)))))")
    e = rl.lower_property(p, G, 1)
    s = z3.Solver()
    s.add(G.system(), e)
    assert s.check() == z3.sat
    # at t = k there is no successor step: the exists over t2 is false
    s = z3.Solver()
    s.add(G.system(), rl.lower_property(p, G, 2))
    assert s.check() == z3.unsat


def test_dataset_loads_and_grounds():
    ip, pp = default_paths()
    insts = load_institutions(ip)
    props = load_properties(pp)
    assert {i.id for i in insts} >= {"coverture-household", "police-crisis", "crisis-team"}
    for inst in insts:
        assert rl.validate_institution(inst) == [], inst.id
        G = rl.ground(inst, k=2)
        assert z3.Solver().check(G.system()) == z3.sat
        for name in inst.expected_properties:
            errs, _ = rl.validate_property(props[name], inst)
            assert errs == [], (inst.id, name, errs)


# ------------------------------------------------------------ initial state
def test_initial_literal_parsing():
    assert rl.parse_literal("employed(worker)") == ("employed", ("worker",))
    assert rl.parse_literal("(owns owner animal)") == ("owns", ("owner", "animal"))
    assert rl.parse_literal("flag") == ("flag", ())
    assert rl.parse_literal(" f( a , b ) ") == ("f", ("a", "b"))
    with pytest.raises(Exception):
        rl.parse_literal("(and a b)")


def test_resolve_init_default_depends_on_fields():
    assert rl.resolve_init(tiny(), None) == "empty"
    assert rl.resolve_init(tiny(initial=[]), None) == "declared"
    assert rl.resolve_init(tiny(defaults={"paid": "true"}), None) == "declared"
    assert rl.resolve_init(tiny(initial_free=["paid"]), None) == "declared"
    assert rl.resolve_init(tiny(initial=["employed(worker)"]), "empty") == "empty"
    with pytest.raises(rl.LowerError):
        rl.resolve_init(tiny(), "nope")


def test_initial_and_initial_free_at_t0():
    inst = tiny(initial=["employed(worker)"], initial_free=["paid"])
    G = rl.ground(inst, k=2)
    assert G.init == "declared"
    s = z3.Solver(); s.add(G.system())
    assert s.check() == z3.sat
    # employed(worker) is forced true, employed(boss) forced false; paid is unconstrained at t=0
    s.push(); s.add(z3.Not(G.fluent("employed", ("worker",), 0))); assert s.check() == z3.unsat; s.pop()
    s.push(); s.add(G.fluent("employed", ("boss",), 0)); assert s.check() == z3.unsat; s.pop()
    s.push(); s.add(G.fluent("paid", ("worker",), 0)); assert s.check() == z3.sat; s.pop()
    s.push(); s.add(z3.Not(G.fluent("paid", ("worker",), 0))); assert s.check() == z3.sat; s.pop()
    # empty mode ignores the fields: employed(worker) is false at t=0
    G = rl.ground(inst, k=2, init="empty")
    s = z3.Solver(); s.add(G.system(), G.fluent("employed", ("worker",), 0))
    assert s.check() == z3.unsat


def test_defaults_apply_before_initial_and_pin_exogenous_fluents():
    inst = tiny(fluents=[{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1},
                         {"name": "can_exit", "arity": 1}, {"name": "can_claim_for", "arity": 2}],
                defaults={"can_exit": True, "can_claim_for": "false"}, initial=["paid(boss)"])
    assert inst.defaults == {"can_exit": "true", "can_claim_for": "false"}
    G = rl.ground(inst, k=2)
    assert "can_exit" in G.exogenous and "can_claim_for" in G.exogenous
    s = z3.Solver(); s.add(G.system()); assert s.check() == z3.sat
    m = s.model()
    for ag in ("boss", "worker"):
        assert z3.is_true(m.eval(G.fluent("can_exit", (ag,), 0)))
        for t in range(3):  # nothing sets it: the frame keeps the default to k
            assert not z3.is_true(m.eval(G.fluent("can_claim_for", (ag, "worker"), t), model_completion=True))
    assert z3.is_true(m.eval(G.fluent("paid", ("boss",), 0)))
    assert not z3.is_true(m.eval(G.fluent("paid", ("worker",), 0), model_completion=True))
    s.add(G.fluent("can_claim_for", ("boss", "worker"), 1))
    assert s.check() == z3.unsat


def test_initial_state_validation_errors_are_readable():
    inst = tiny(initial=["employed(nobody)", "(paid worker boss)", "ghost(worker)", "(and a b)"],
                defaults={"nope": "true"}, initial_free=["zip"])
    joined = "\n".join(rl.validate_institution(inst))
    assert "'nobody' is not a role" in joined
    assert "arity 1" in joined
    assert "undeclared fluent 'ghost'" in joined
    assert "initial literal" in joined
    assert "defaults: undeclared fluent 'nope'" in joined
    assert "initial_free: undeclared fluent 'zip'" in joined
    with pytest.raises(Exception):
        tiny(defaults={"paid": "maybe"})


# ------------------------------------------------------------- argument roles
def test_fluent_arg_roles_type_the_tuples():
    inst = tiny(fluents=[{"name": "employed", "arity": 1, "arg_roles": ["worker"]}, {"name": "paid", "arity": 1}])
    G = rl.ground(inst, k=2)
    assert G.fluent_tuples["employed"] == [("worker",)]
    assert G.fluent_tuples["paid"] == [("boss",), ("worker",)]
    assert ("employed", ("boss",), 0) not in G.fluent_vars
    e = G.fluent("employed", ("boss",), 1)
    assert z3.is_false(e)  # ill-typed tuple is constant false
    with pytest.raises(KeyError):
        G.fluent("ghost", ("boss",), 0)
    from philengine import sexpr as sx
    p = sx.parse("(exists ((x agent)) (employed x t))")
    s = z3.Solver(); s.add(G.system(), rl.lower_property(p, G, 1), z3.Not(G.fluent("employed", ("worker",), 1)))
    assert s.check() == z3.unsat
    errs = "\n".join(rl.validate_institution(tiny(fluents=[{"name": "employed", "arity": 1, "arg_roles": ["boss", "worker"]},
                                                           {"name": "paid", "arity": 1, "arg_roles": ["nobody"]}])))
    assert "arg_roles has 2 entries, arity is 1" in errs and "'nobody', which is not a role" in errs


def test_action_arg_roles_and_typed_args_and_var_roles():
    inst = tiny(roles=[{"name": "boss"}, {"name": "worker"}, {"name": "witness"}],
                actions=[{"name": "hire", "args": [["b", "boss"], "x"], "effects": [{"fluent": "employed", "args": ["x"], "value": True}]},
                         {"name": "pay", "args": ["b", "x"], "arg_roles": [None, "worker"],
                          "effects": [{"fluent": "paid", "args": ["x"], "value": True}]},
                         {"name": "quit", "args": ["x"], "effects": [{"fluent": "employed", "args": ["x"], "value": False}]}],
                rules=[{"id": "R1", "attribute": "boss", "deontic": "must", "aim": "(pay b x)", "conditions": "(employed x)",
                        "strand": "superadditive"},
                       {"id": "R2", "attribute": "worker", "deontic": "must_not", "aim": "(quit x)", "conditions": "(employed y)",
                        "strand": "rival", "var_roles": {"y": "witness"}},
                       {"id": "R3", "attribute": "boss", "deontic": "may", "aim": "(hire b x)", "conditions": "true", "strand": "tying",
                        "var_roles": {"x": "worker"}}])
    assert inst.actions[0].args == ["b", "x"] and inst.actions[0].arg_roles == ["boss", None]
    assert rl.validate_institution(inst) == []
    G = rl.ground(inst, k=2)
    # x in hire is untyped by the heuristic (no role starts with x) but typed by the rule's var_roles; the
    # attribute scoping keeps the actor to boss
    assert set(G.action_instances["hire"]) == {("boss", "worker"), ("boss", "witness")}
    assert [ri.args for ri in G.rule_instances if ri.rule.id == "R3"] == [("boss", "worker")]
    assert set(G.action_instances["pay"]) == {("boss", "worker")}
    assert not any("R3" in w for w in G.warnings)
    # var_roles on a free condition variable: R2 binds y to the witness, not every agent
    assert not any("R2" in w for w in G.warnings)
    errs = "\n".join(rl.validate_institution(tiny(rules=[{**tiny().rules[0].model_dump(), "var_roles": {"w": "ghost"}}])))
    assert "var_roles types 'w' as 'ghost'" in errs
    errs = "\n".join(rl.validate_institution(tiny(actions=[{"name": "hire", "args": ["b", "w"], "arg_roles": ["boss"]}])))
    assert "arg_roles has 1 entries, args has 2" in errs


def test_attribute_scoping_restricts_the_actor():
    # transfer is named only by a worker rule: the boss cannot transfer, even though the action is otherwise free
    inst = tiny(fluents=[{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1}, {"name": "token", "arity": 1}],
                actions=[*[a.model_dump() for a in tiny().actions],
                         {"name": "transfer", "args": ["x", "y"], "effects": [{"fluent": "token", "args": ["y"], "value": True}]}],
                rules=[*[r.model_dump() for r in tiny().rules],
                       {"id": "R3", "attribute": "worker", "deontic": "must_not", "aim": "(transfer x y)", "conditions": "true",
                        "strand": "rival"}])
    G = rl.ground(inst, k=2)
    assert G.action_instances["transfer"] == [("worker", "boss")]
    s = z3.Solver(); s.add(G.system(), G.fluent("token", ("worker",), 2))
    assert s.check() == z3.unsat  # nobody but the worker could transfer, and the worker must not
    # without any rule naming it the action is open to every typed instance
    inst2 = inst.model_copy(update={"rules": inst.rules[:2]})
    G2 = rl.ground(inst2, k=2)
    assert len(G2.action_instances["transfer"]) == 2


def test_step_mode_one_vs_many():
    G1 = rl.ground(tiny(), k=2, step_mode="one")
    s = z3.Solver(); s.add(G1.system(), G1.action("hire", ("boss", "worker"), 0), G1.action("quit", ("worker",), 0))
    assert s.check() == z3.unsat
    G2 = rl.ground(tiny(), k=2, step_mode="many")
    s = z3.Solver(); s.add(G2.system(), G2.action("hire", ("boss", "worker"), 0), G2.action("quit", ("worker",), 0))
    assert s.check() == z3.sat
    with pytest.raises(rl.LowerError):
        rl.ground(tiny(), k=2, step_mode="all")


def test_dataset_loads_with_declared_init():
    ip, pp = default_paths()
    for inst in load_institutions(ip):
        G = rl.ground(inst, k=2)
        assert G.init == ("declared" if inst.declares_init() else "empty"), inst.id
        assert z3.Solver().check(G.system()) == z3.sat, inst.id


def test_free_condition_variable_may_coincide_with_an_aim_argument():
    # clerk must log(c, s) when (flag q): plain existential quantification, so q = s is a witness (no distinctness)
    inst = tiny(roles=[{"name": "clerk"}, {"name": "subject"}],
                fluents=[{"name": "flag", "arity": 1}, {"name": "logged", "arity": 1}],
                actions=[{"name": "log", "args": ["c", "s"], "arg_roles": ["clerk", "subject"],
                          "effects": [{"fluent": "logged", "args": ["s"], "value": True}]}],
                rules=[{"id": "R1", "attribute": "clerk", "deontic": "must", "aim": "(log c s)",
                        "conditions": "(and (flag q) (not (logged s)))", "var_roles": {"q": "subject"}, "strand": "tying"}])
    G = rl.ground(inst, k=2, init="free")
    s = z3.Solver(); s.add(G.system(), G.fluent("flag", ("subject",), 0), G.fluent("logged", ("subject",), 1))
    assert s.check() == z3.sat
    s = z3.Solver(); s.add(G.system(), G.fluent("flag", ("subject",), 0), z3.Not(G.fluent("logged", ("subject",), 0)),
                           z3.Not(G.action("log", ("clerk", "subject"), 0)))
    assert s.check() == z3.unsat  # the obligation binds: flag(subject) is a witness for q


def household(**over) -> InstitutionJSON:
    """ADR 0009: a state obligation. must-be cared(h, w) when married(h, w); marry establishes it, neglect breaks it."""
    d = {
        "id": "household", "roles": [{"name": "husband"}, {"name": "wife"}],
        "fluents": [{"name": "married", "arity": 2}, {"name": "cared", "arity": 2}, {"name": "rich", "arity": 1}],
        "actions": [
            {"name": "marry", "args": ["h", "w"], "effects": [{"fluent": "married", "args": ["h", "w"], "value": True},
                                                             {"fluent": "cared", "args": ["h", "w"], "value": True}]},
            {"name": "maintain", "args": ["h", "w"], "effects": [{"fluent": "cared", "args": ["h", "w"], "value": True}]},
            {"name": "neglect", "args": ["h", "w"], "effects": [{"fluent": "cared", "args": ["h", "w"], "value": False}]},
            {"name": "invest", "args": ["h"], "effects": [{"fluent": "rich", "args": ["h"], "value": True}]},
            {"name": "chastise", "args": ["h", "w"], "effects": []},
        ],
        "rules": [
            {"id": "R1", "attribute": "husband", "deontic": "must", "aim": "(cared h w)", "conditions": "(married h w)",
             "or_else": "R2", "strand": "superadditive"},
            {"id": "R2", "attribute": "husband", "deontic": "may", "aim": "(chastise h w)", "conditions": "(married h w)",
             "strand": "rival"},
        ],
    }
    d.update(over)
    return InstitutionJSON.model_validate(d)


def test_state_obligation_aim_kind_and_validation():
    inst = household()
    assert rl.validate_institution(inst) == []
    assert rl.aim_kind(inst.rules[0], inst) == "state" and rl.aim_kind(inst.rules[1], inst) == "action"
    errs = "\n".join(rl.validate_institution(household(rules=[{**household().rules[0].model_dump(), "deontic": "may"}])))
    assert "`may` on a fluent" in errs
    errs = "\n".join(rl.validate_institution(household(rules=[{**household().rules[0].model_dump(), "aim": "(cared h)"}])))
    assert "arity 2, aim gives 1" in errs
    errs = "\n".join(rl.validate_institution(household(rules=[{**household().rules[0].model_dump(), "aim_kind": "action"}])))
    assert "aim_kind is 'action'" in errs
    errs = "\n".join(rl.validate_institution(household(rules=[{**household().rules[0].model_dump(), "aim": "(ghost h w)"}])))
    assert "undeclared action 'ghost'" in errs


def test_state_obligation_fires_no_action_and_binds_at_every_step():
    inst = household()
    G = rl.ground(inst, k=3, step_mode="one")
    assert [ri.kind for ri in G.rule_instances if ri.rule.id == "R1"] == ["state"]
    m, h = ("husband", "wife"), ("husband",)
    # marry at 0 (married + cared at 1), then a discretionary action at 1: the standing obligation leaves the slot free
    s = z3.Solver(); s.add(G.system(), G.action("marry", m, 0), G.action("invest", h, 1), G.fluent("rich", h, 2))
    assert s.check() == z3.sat
    # neglect while married breaks the state: no compliant trace (strict)
    s = z3.Solver(); s.add(G.system(), G.action("marry", m, 0), G.action("neglect", m, 1))
    assert s.check() == z3.unsat
    # and the obligation binds at the last step k too: married at k without cared at k is out
    s = z3.Solver(); s.add(G.system(), G.fluent("married", m, 3), z3.Not(G.fluent("cared", m, 3)))
    assert s.check() == z3.unsat
    # sanctioned: the breach sets violated_R1 at the next step, which enables chastise (R2)
    Gs = rl.ground(inst, k=3, compliance="sanctioned")
    s = z3.Solver(); s.add(Gs.system(), Gs.action("marry", m, 0), Gs.action("neglect", m, 1))
    assert s.check() == z3.sat
    mdl = s.model()
    assert z3.is_true(mdl.eval(Gs.violation_vars[("R1", 3)], model_completion=True))
    # must_not on a fluent is a state prohibition (symmetric)
    inst2 = household(rules=[{"id": "R1", "attribute": "husband", "deontic": "must_not", "aim": "(rich h)",
                              "conditions": "(married h w)", "strand": "rival"}])
    G2 = rl.ground(inst2, k=3)
    s = z3.Solver(); s.add(G2.system(), G2.action("marry", m, 0), G2.action("invest", h, 1))
    assert s.check() == z3.unsat


# ------------------------------------------------------------ derived fluents (ADR 0013)
def derived_police(**over) -> InstitutionJSON:
    """Toy police institution whose power fluents are derived from what the rules enable: can_sanction(o, s) is
    "detain or use_force is enabled", can_exit(s) is "leave is enabled" (barred by a disability in custody)."""
    d = {
        "id": "t-derived",
        "roles": [{"name": "officer"}, {"name": "subject"}],
        "fluents": [{"name": "is_subject", "arity": 1, "arg_roles": ["subject"]},
                    {"name": "responding", "arity": 2, "arg_roles": ["officer", "subject"]},
                    {"name": "danger", "arity": 1, "arg_roles": ["subject"]},
                    {"name": "in_custody", "arity": 1, "arg_roles": ["subject"]},
                    {"name": "provides_care", "arity": 2, "arg_roles": ["officer", "subject"]},
                    {"name": "can_sanction", "arity": 2, "arg_roles": ["officer", "subject"], "params": ["o", "s"],
                     "derived": "(or (enabled detain o s) (enabled use_force o s))"},
                    {"name": "can_exit", "arity": 1, "arg_roles": ["subject"], "params": ["s"],
                     "derived": "(enabled leave s)"}],
        "actions": [
            {"name": "respond", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "responding", "args": ["o", "s"], "value": True},
                         {"fluent": "is_subject", "args": ["s"], "value": True},
                         {"fluent": "provides_care", "args": ["o", "s"], "value": True}]},
            {"name": "detain", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "in_custody", "args": ["s"], "value": True}]},
            {"name": "use_force", "args": ["o", "s"], "arg_roles": ["officer", "subject"], "effects": []},
            {"name": "release", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "in_custody", "args": ["s"], "value": False}]},
            {"name": "neglect", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "provides_care", "args": ["o", "s"], "value": False}]},
            {"name": "leave", "args": ["s"], "arg_roles": ["subject"],
             "effects": [{"fluent": "responding", "args": ["officer", "s"], "value": False}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "officer", "deontic": "may", "aim": "(respond o s)", "conditions": "(not (responding o s))", "strand": "tying"},
            {"id": "R2", "attribute": "officer", "deontic": "must", "aim": "(provides_care o s)", "conditions": "(responding o s)",
             "or_else": None, "strand": "superadditive", "load_bearing": True},
            {"id": "R3", "attribute": "officer", "deontic": "may", "aim": "(detain o s)", "conditions": "(and (responding o s) (danger s))", "strand": "rival"},
            {"id": "R4", "attribute": "officer", "deontic": "may", "aim": "(use_force o s)", "conditions": "(in_custody s)", "strand": "rival"},
            {"id": "R5", "attribute": "subject", "deontic": "may", "aim": "(leave s)", "conditions": "true", "strand": "rival"},
            {"id": "R6", "attribute": "subject", "deontic": "must_not", "aim": "(leave s)", "conditions": "(in_custody s)", "or_else": None, "strand": "rival"},
            {"id": "R7", "attribute": "officer", "deontic": "may", "aim": "(release o s)", "conditions": "(in_custody s)", "strand": "superadditive"},
            {"id": "R8", "attribute": "officer", "deontic": "may", "aim": "(neglect o s)", "conditions": "true", "strand": "rival"},
        ],
        "initial_free": ["danger"],
    }
    d.update(over)
    return InstitutionJSON.model_validate(d)


def _sat(*exprs):
    s = z3.Solver()
    for e in exprs:
        s.add(e)
    return s.check() == z3.sat


def test_derived_fluent_is_defined_by_enabledness_not_effects():
    inst = derived_police()
    assert rl.validate_institution(inst) == []
    G = rl.ground(inst, k=3)
    assert ("can_sanction", ("officer", "subject"), 0) not in G.fluent_vars  # no state variable
    assert ("can_sanction", ("officer", "subject"), 0) in G.derived_vars
    assert not any(n.startswith("frame:can_sanction") or n.startswith("init:can_sanction") for n, _ in G.assertions)
    cs = G.fluent("can_sanction", ("officer", "subject"), 2)
    # power exists exactly when detain or use_force is enabled: responding+danger, or in custody
    assert not _sat(G.system(), cs, z3.Not(G.fluent("in_custody", ("subject",), 2)),
                    z3.Not(z3.And(G.fluent("responding", ("officer", "subject"), 2), G.fluent("danger", ("subject",), 2))))
    assert _sat(G.system(), cs, G.fluent("in_custody", ("subject",), 2))
    # can_exit is barred by the disability while in custody, and only then
    ce = G.fluent("can_exit", ("subject",), 2)
    assert not _sat(G.system(), ce, G.fluent("in_custody", ("subject",), 2))
    assert not _sat(G.system(), z3.Not(ce), z3.Not(G.fluent("in_custody", ("subject",), 2)))
    # a tuple outside arg_roles is constant false
    assert z3.is_false(G.fluent("can_sanction", ("subject", "officer"), 0))


def test_derived_fluent_appears_in_traces_and_warns_on_unregulated_actions():
    from philengine import rules_checks as rc
    inst = derived_police()
    props = {"cs": Property(name="cs", formal="(can_sanction officer subject t)")}
    rep = rc.run_all(inst, props, k=3, which={"cs": ["reachable"]})
    assert rep.results[0].verdict == "reachable"
    assert any("can_sanction(officer, subject)" in s.fluents for s in rep.results[0].trace)
    # an unregulated action (no may/must rule) is never (enabled ...): no rule grants it (ADR 0013 amendment
    # 2026-11-03), so the derived power reads false, with a warning; the action itself can still fire in traces
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] != "R4"]
    rep = rc.run_all(InstitutionJSON.model_validate(d), props, k=3, which={"cs": ["reachable"]})
    assert any("(enabled use_force ...) names an action no may/must rule regulates" in w and "never enabled" in w
               for w in rep.warnings)
    G = rl.ground(InstitutionJSON.model_validate(d), k=3)
    assert z3.is_false(G.enabled("use_force", ("officer", "subject"), 1))
    # custody no longer confers power: can_sanction is detain-only (responding + danger)
    assert not _sat(G.system(), G.fluent("can_sanction", ("officer", "subject"), 2),
                    z3.Not(z3.And(G.fluent("responding", ("officer", "subject"), 2), G.fluent("danger", ("subject",), 2))))
    assert _sat(G.system(), G.action("use_force", ("officer", "subject"), 1))  # but it may still fire
    # with no may/must rule on either action the power is constant false and the property unreachable
    d["rules"] = [r for r in d["rules"] if r["id"] != "R3"]
    rep = rc.run_all(InstitutionJSON.model_validate(d), props, k=3, which={"cs": ["reachable"]})
    assert rep.results[0].verdict == "open"


def test_derived_fluent_validation_errors():
    base = derived_police()

    def errs(**over):
        return "\n".join(rl.validate_institution(derived_police(**over)))

    # effect on a derived fluent
    acts = [a.model_dump() for a in base.actions]
    acts[0]["effects"].append({"fluent": "can_sanction", "args": ["o", "s"], "value": True})
    assert "effect on derived fluent 'can_sanction'" in errs(actions=acts)
    # initial / defaults / initial_free on a derived fluent
    assert "is derived; it has no initial value" in errs(initial=["(can_sanction officer subject)"])
    assert "is derived; it has no initial value" in errs(defaults={"can_exit": "true"})
    assert "is derived; it has no initial value" in errs(initial_free=["can_exit"])
    # as an aim
    rules = [r.model_dump() for r in base.rules]
    rules.append({"id": "R9", "attribute": "officer", "deontic": "must", "aim": "(can_sanction o s)", "conditions": "true",
                  "or_else": None, "strand": "tying"})
    assert "is a derived fluent; a state obligation needs a fluent effects can establish" in errs(rules=rules)
    # params / grammar / references
    fl = [f.model_dump() for f in base.fluents]
    bad = dict(fl[5]); bad["params"] = ["o"]
    assert "params has 1 name(s), arity is 2" in errs(fluents=fl[:5] + [bad] + fl[6:])
    bad = dict(fl[5]); bad["derived"] = "(enabled arrest o s)"
    assert "not a declared action" in errs(fluents=fl[:5] + [bad] + fl[6:])
    bad = dict(fl[5]); bad["derived"] = "(enabled detain o)"
    assert "action takes 2 argument(s), got 1" in errs(fluents=fl[:5] + [bad] + fl[6:])
    bad = dict(fl[5]); bad["derived"] = "(enabled detain o q)"
    assert "'q' is neither a param, a role nor a bound variable" in errs(fluents=fl[:5] + [bad] + fl[6:])
    bad = dict(fl[5]); bad["derived"] = "(exists ((t2 step)) (in_custody s))"
    assert "is not agent" in errs(fluents=fl[:5] + [bad] + fl[6:])
    # `enabled` is not a condition primitive: conditions see it as an undeclared fluent
    rules = [r.model_dump() for r in base.rules]
    rules[2]["conditions"] = "(enabled use_force o s)"
    assert "undeclared fluent 'enabled'" in errs(rules=rules)


def test_derived_fluent_cycles_are_errors():
    inst = derived_police()
    fl = [f.model_dump() for f in inst.fluents]
    # direct: can_sanction <-> can_exit
    a = dict(fl[5]); a["derived"] = "(not (can_exit s))"
    b = dict(fl[6]); b["derived"] = "(not (can_sanction officer s))"
    errs = rl.validate_institution(derived_police(fluents=fl[:5] + [a, b]))
    assert any("cyclic" in e for e in errs), errs
    # through a rule condition: can_exit := enabled(leave); leave's rule reads can_exit
    rules = [r.model_dump() for r in inst.rules]
    rules[4]["conditions"] = "(can_exit s)"
    errs = rl.validate_institution(derived_police(rules=rules))
    assert any("cyclic" in e and "can_exit" in e for e in errs), errs
    # derived through another derived is fine in dependency order
    fl2 = [f.model_dump() for f in inst.fluents]
    fl2.append({"name": "powerless", "arity": 1, "arg_roles": ["subject"], "params": ["s"],
                "derived": "(and (not (can_exit s)) (can_sanction officer s))"})
    inst2 = derived_police(fluents=fl2)
    assert rl.validate_institution(inst2) == []
    assert rl.derived_order(inst2) == ["can_exit", "can_sanction", "powerless"] or rl.derived_order(inst2)[-1] == "powerless"
    rl.ground(inst2, k=2)
