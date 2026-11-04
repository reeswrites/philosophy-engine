"""Layer 2 ABM: state obligations (A8, ADR 0015 amendment 2026-11-04; ADR 0009 must-be) and the slice-2 review
fixes: one sanction quantity (a), A5 bearing from declared arg_roles (b), `payoff.<action>` sweep-axis validation
(c), conflicting musts reported as an inconsistent encoding (d). In-test institutions only, never the dataset."""
import json

import pytest

from philengine.abm import InstitutionModel, run_abm
from philengine.abm.sweep import sweep
from philengine.cli import main
from philengine.schemas_rules import InstitutionJSON


def kibbutz_like(extra_rules=(), extra_actions=(), fluent_arg_roles=("carer", "child")) -> InstitutionJSON:
    """The kibbutz-childrens-house shape: a carer must-be providing care while assigned (R3, or_else R6); `assign`
    (committee) establishes the state, `care` (carer) restores it, `neglect` breaks it and is enabled by a `may`
    rule (ADR 0015 A6); the committee may reprimand (the sanction rule)."""
    return InstitutionJSON.model_validate({
        "id": "carer-house",
        "roles": [{"name": "committee"}, {"name": "carer"}, {"name": "child"}],
        "fluents": [{"name": "provides_care", "arity": 2,
                     **({"arg_roles": list(fluent_arg_roles)} if fluent_arg_roles else {})},
                    {"name": "assigned", "arity": 1, "arg_roles": ["carer"]}],
        "actions": [{"name": "assign", "args": ["committee", "carer"],
                     "effects": [{"fluent": "provides_care", "args": ["carer", "child"], "value": True},
                                 {"fluent": "assigned", "args": ["carer"], "value": True}]},
                    {"name": "care", "args": ["carer", "child"],
                     "effects": [{"fluent": "provides_care", "args": ["carer", "child"], "value": True}]},
                    {"name": "neglect", "args": ["carer", "child"],
                     "effects": [{"fluent": "provides_care", "args": ["carer", "child"], "value": False}]},
                    {"name": "reprimand", "args": ["committee", "carer"]},
                    {"name": "play", "args": ["child"]}, *extra_actions],
        "rules": [{"id": "R1", "attribute": "committee", "deontic": "may", "aim": "(assign committee carer)",
                   "conditions": "true", "strand": "superadditive"},
                  {"id": "R3", "attribute": "carer", "deontic": "must", "aim": "(provides_care carer child)",
                   "conditions": "(assigned carer)", "strand": "superadditive", "or_else": "R6"},
                  {"id": "R5", "attribute": "carer", "deontic": "may", "aim": "(care carer child)",
                   "conditions": "(assigned carer)", "strand": "superadditive"},
                  {"id": "R6", "attribute": "committee", "deontic": "may", "aim": "(reprimand committee carer)",
                   "conditions": "true", "strand": "rival"},
                  {"id": "R7", "attribute": "carer", "deontic": "may", "aim": "(neglect carer child)",
                   "conditions": "true", "strand": "rival"},
                  {"id": "R8", "attribute": "child", "deontic": "may", "aim": "(play child)",
                   "conditions": "true", "strand": "rival"}, *extra_rules],
        "initial": [],
    })


CARE, NEGLECT = ("care", ("carer", "child")), ("neglect", ("carer", "child"))
ATOM = ("provides_care", ("carer", "child"))


def _child_carer_pairs(m):
    return [(c, k) for c in m.by_role["child"] for k in c.neighbours if k.role == "carer"]


def test_state_obligation_read_from_the_reference():
    """R3 is a state rule (aim_kind state): the model lists its atom as an obligation of the carer once assigned,
    and reads keep/breach through the reference successor: care keeps, neglect breaches, nothing keeps iff P holds."""
    m = InstitutionModel(kibbutz_like(), seed=0, agents_per_role=3)
    assert m.state_obligations_for("carer") == [] and m.obligations_for("carer") == []
    assert m.available_for("carer") == [NEGLECT]  # may neglect is unconditional; care needs assigned
    m.step()  # every committee member assigns -> assigned(carer), provides_care(carer, child) hold
    assert ATOM in m.state and m.state_obligation_rules("carer") == {ATOM: ["R3"]}
    assert set(m.available_for("carer")) == {CARE, NEGLECT}
    assert m.keeps("carer", CARE) and m.keeps("carer", None) and not m.keeps("carer", NEGLECT)
    assert m.state_breaches("carer", NEGLECT) == {ATOM: ["R3"]}


def test_breach_sanction_and_trust_fire_when_breach_pays():
    """Under parameters that make neglect pay (payoff 5 against a total expected sanction of 1 * 3 steps = 3 and
    care at 1), carers breach R3, are sanctioned, and the children the obligation bears on lose trust in them."""
    pay = {"neglect": 5.0, "care": 1.0, "assign": 1.0, "play": 1.0}
    m = InstitutionModel(kibbutz_like(), seed=0, agents_per_role=8, payoffs=pay,
                         params={"sanction_weight": 1.0, "copy_rate": 0.0})
    m.step()  # assign
    m.step()  # carers choose: neglect nets 5 - 3 = 2 > care 1
    assert all(k.chosen == NEGLECT and k.breached == ["R3"] and k.sanctioned for k in m.by_role["carer"])
    assert all(k.obligation_outcomes == [(ATOM, False)] for k in m.by_role["carer"])
    rep = m.report()
    assert rep.breaches[-1]["carer"] == 1.0 and rep.sanctioned[-1]["carer"] == 1.0
    assert rep.breach_rate()["carer"] > 0 and rep.sanctioned_rate()["carer"] > 0
    pairs = _child_carer_pairs(m)
    assert pairs
    assert all(c.trust[k.unique_id] == pytest.approx(0.5 - 2.0 * 0.1) for c, k in pairs)  # -beta*delta (A5)
    # the obligation bears on the child only: committee members' trust in carers never moves
    for cm in m.by_role["committee"]:
        assert all(cm.trust.get(k.unique_id) is None for k in cm.neighbours if k.role == "carer")
    assert not any(w.startswith(("unavoidable", "inconsistent")) for w in rep.warnings)


def test_no_breach_when_breach_does_not_pay():
    pay = {"neglect": 5.0, "care": 1.0, "assign": 1.0, "play": 1.0}
    m = InstitutionModel(kibbutz_like(), seed=0, agents_per_role=8, payoffs=pay,
                         params={"sanction_weight": 10.0, "copy_rate": 0.0})
    for _ in range(6):
        m.step()
    rep = m.report()
    assert all(v["carer"] == 0.0 for v in rep.breaches) and all(v["carer"] == 0.0 for v in rep.sanctioned)
    assert all(k.chosen == CARE and k.obligation_outcomes == [(ATOM, True)] for k in m.by_role["carer"])
    assert all(c.trust[k.unique_id] > 0.5 for c, k in _child_carer_pairs(m))  # kept, bearing on the child


def test_breach_rates_over_seeds_split_on_sanction_weight():
    pay = {"neglect": 5.0, "care": 1.0}

    def rate(w):
        reps = [run_abm(kibbutz_like(), seed=s, steps=8, agents_per_role=5, payoffs=pay,
                        params={"sanction_weight": w}) for s in range(5)]
        return sum(r.breach_rate()["carer"] for r in reps) / len(reps)
    assert rate(0.5) > 0.3
    assert rate(10.0) == 0.0


def test_unavoidable_breach_is_warned_once_per_run():
    """Strict enabledness (ADR 0013): without `may care`, once a carer has neglected nothing available to it
    re-establishes provides_care while assigned, so the breach is unavoidable; reported once, counted.
    Updated 2026-11-04 (review finding 3): an unavoidable breach is not a breach of choice, so from step 2 on it
    is in `unavoidable`, not `breaches`, and nobody is sanctioned for it; before, `breaches` stayed 1.0."""
    inst = kibbutz_like()
    inst.rules = [r for r in inst.rules if r.id != "R5"]
    for r in inst.rules:
        if r.id == "R1":
            r.conditions = "(not (assigned carer))"  # one-shot: the committee cannot re-establish care each step
    m = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs={"neglect": 5.0},
                         params={"sanction_weight": 0.0, "copy_rate": 0.0})
    m.step()  # assign
    m.step()  # neglect pays (no sanction cost): provides_care false, assigned still true
    assert ATOM not in m.state and ("assigned", ("carer",)) in m.state
    assert m.unavoidable == {}  # so far every breach was a choice
    for _ in range(3):
        m.step()  # nothing available to a carer sets provides_care: R3 cannot be kept
    rep = m.report()
    ws = [w for w in rep.warnings if w.startswith("unavoidable breach: R3")]
    assert len(ws) == 1 and "role carer" in ws[0] and "3 step(s)" in ws[0], rep.warnings
    assert m.unavoidable["R3"][2] == 3  # counted over steps, reported once
    assert not any(w.startswith("inconsistent") for w in rep.warnings)  # one rule alone: not a conflict
    assert rep.breaches[1]["carer"] == 1.0 and rep.unavoidable[1]["carer"] == 0.0  # step 1: neglect was a choice
    assert all(v["carer"] == 0.0 for v in rep.breaches[2:])  # then no option keeps P: not a breach of choice
    assert all(v["carer"] == 1.0 for v in rep.unavoidable[2:])
    assert all(k.unavoidable == ["R3"] and k.breached == [] for k in m.by_role["carer"])
    assert rep.breach_rate()["carer"] == pytest.approx(1 / 5) and rep.unavoidable_rate()["carer"] == pytest.approx(3 / 5)
    # finding 4: the counters are exact whatever is read between steps
    m2 = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs={"neglect": 5.0},
                          params={"sanction_weight": 0.0, "copy_rate": 0.0})
    for _ in range(5):
        m2.step()
        for _ in range(3):
            m2.available_for("carer"); m2.state_obligations_for("carer"); m2.state_breaches("carer", None)
    assert m2.unavoidable["R3"] == m.unavoidable["R3"] == ("carer", 2, 3)


def test_choosing_nothing_is_the_lawful_baseline():
    """A carer whose only available action breaches (no `may care`) and whose breach does not pay chooses nothing
    when P already holds: doing nothing keeps the obligation and is weighed at payoff 0."""
    inst = kibbutz_like()
    inst.rules = [r for r in inst.rules if r.id != "R5"]
    m = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs={"neglect": 1.0},
                         params={"sanction_weight": 10.0, "copy_rate": 0.0})
    m.step(); m.step()
    assert all(k.chosen is None and k.breached == [] for k in m.by_role["carer"])
    assert m.report().breach_rate()["carer"] == 0.0


# ---------------------------------------------------------------- 2026-11-04 review findings 2, 3, 7b

def dataset_shaped(initial=()) -> InstitutionJSON:
    """The kibbutz-childrens-house entry's shape: the carer has a must-be (R3) and a breaker `may neglect` (R7),
    the committee's `assign` establishes provides_care, and NO action of the carer restores it (no `may care`:
    `care` is declared but unnamed, so never available under strict enabledness)."""
    inst = kibbutz_like()
    inst.rules = [r for r in inst.rules if r.id != "R5"]
    inst.initial = list(initial)
    return inst


def test_dataset_shaped_breach_is_a_choice_only_while_an_option_keeps_the_state():
    """Review finding 2: on the dataset shape the carer's only move is the breaker, so with P held by the
    committee's assign the sign test on `neglect` decides. Sanction zero: every carer breaches by choice and is
    counted in `breaches`; sanction above the payoff: nobody does (they choose nothing). Finding 3: when nobody
    re-establishes P, the breach is unavoidable: `breaches` stays 0, `unavoidable` is 1, nobody is sanctioned."""
    free = InstitutionModel(dataset_shaped(), seed=0, agents_per_role=6, payoffs={"neglect": 1.0},
                            params={"sanction_weight": 0.0, "copy_rate": 0.0})
    free.step(); free.step()
    assert free.available_for("carer") == [NEGLECT]
    assert all(k.chosen == NEGLECT and k.breached == ["R3"] and k.unavoidable == [] for k in free.by_role["carer"])
    assert free.breaches[-1]["carer"] == 1.0 and free.unavoidable_steps[-1]["carer"] == 0.0
    dear = InstitutionModel(dataset_shaped(), seed=0, agents_per_role=6, payoffs={"neglect": 1.0},
                            params={"sanction_weight": 1.0, "copy_rate": 0.0})  # expected sanction 1 * 3 > 1
    for _ in range(4):
        dear.step()
    assert all(k.chosen is None and k.breached == [] for k in dear.by_role["carer"])
    assert all(v["carer"] == 0.0 for v in dear.breaches) and all(v["carer"] == 0.0 for v in dear.unavoidable_steps)
    # assigned but uncared-for from the start, and the committee never (re-)assigns: no option of the carer keeps P
    stuck = dataset_shaped(initial=["(assigned carer)"])
    for r in stuck.rules:
        if r.id == "R1":
            r.conditions = "(not (assigned carer))"
    for w in (0.0, 10.0):
        m = InstitutionModel(stuck, seed=0, agents_per_role=6, payoffs={"neglect": 1.0},
                             params={"sanction_weight": w, "copy_rate": 0.0})
        for _ in range(5):
            m.step()
        rep = m.report()
        assert ATOM not in m.state and m.state_obligation_rules("carer") == {ATOM: ["R3"]}
        assert rep.breach_rate()["carer"] == 0.0 and rep.unavoidable_rate()["carer"] == 1.0
        assert rep.sanctioned_rate()["carer"] == 0.0  # A4: no choice, no sanction
        assert all(k.unavoidable == ["R3"] and k.obligation_outcomes == [] for k in m.by_role["carer"])
        assert all(c.trust == {} for c in m.by_role["child"])  # nothing chosen to keep or breach: trust unmoved
        assert len([x for x in rep.warnings if x.startswith("unavoidable breach: R3")]) == 1
        assert "unavoidable_rate_over_seeds" in __import__("philengine.abm.report", fromlist=["summarize"]).summarize([rep])


def test_material_floor_admits_the_keepers_of_each_obligation_symmetrically():
    """Review finding 7b: under the floor the candidates are the practice plus, per obligation in force, the
    actions that keep it: the must action for an action must, the keep-set for a must-be. With an action must
    (R10 `must care`) and the must-be R3 both in force on a carer below the floor and without a practice: when P
    holds, `rest` keeps R3 (no effect on P) and is admitted although it is not the must action (before, only
    `care` was); when P is false only `care` keeps R3, so `rest` is dropped and `care` is chosen."""
    def inst(initial=()):
        out = kibbutz_like(extra_actions=[{"name": "rest", "args": ["carer"]}],
                           extra_rules=[{"id": "R9", "attribute": "carer", "deontic": "may", "aim": "(rest carer)",
                                         "conditions": "true", "strand": "rival"},
                                        {"id": "R10", "attribute": "carer", "deontic": "must", "aim": "(care carer child)",
                                         "conditions": "(assigned carer)", "strand": "superadditive", "or_else": "R6"}])
        out.initial = list(initial)
        return out
    REST = ("rest", ("carer",))
    pay = {"rest": 3.0, "care": 1.0, "neglect": 0.5}
    # sanction 0.1 * 3 steps = 0.3 per rule: rest nets 2.7 breaching R10 alone, 2.4 breaching R10 and R3
    params = {"initial_surplus": 0.0, "default_income": 0.0, "floor": 1.0, "copy_rate": 0.0, "sanction_weight": 0.1}
    # the floor binds everyone (surplus 0 < 1), so the committee never assigns: the state is set by `initial`
    held = InstitutionModel(inst(initial=["(assigned carer)", "(provides_care carer child)"]), seed=0,
                            agents_per_role=6, payoffs=pay, params=params)
    assert all(k.surplus < 1.0 and k.practice is None for k in held.by_role["carer"])
    assert held.keeps("carer", REST) and held.obligations_for("carer") == [CARE]
    held.step()
    assert all(k.chosen == REST and k.breached == ["R10"] for k in held.by_role["carer"])  # keeps R3: admitted
    broken = InstitutionModel(inst(initial=["(assigned carer)"]), seed=0, agents_per_role=6, payoffs=pay, params=params)
    assert not broken.keeps("carer", REST) and broken.keeps("carer", CARE)
    broken.step()
    assert all(k.chosen == CARE and k.breached == [] for k in broken.by_role["carer"])  # rest keeps nothing: dropped


# ---------------------------------------------------------------- item 2 (a): one sanction quantity

def test_expected_sanction_equals_total_realised_charge():
    """Expected = per-step charge * sanction_steps; realised = that charge at each of the sanction_steps steps, so
    the total an agent pays for one breach (no re-breach inside the window) equals what it expected."""
    pay = {"neglect": 5.0, "care": 1.0}
    m = InstitutionModel(kibbutz_like(), seed=0, agents_per_role=2, payoffs=pay,
                         params={"sanction_weight": 0.5, "sanction_steps": 4, "sanction_escalation": 2.0,
                                 "copy_rate": 0.0})
    k = m.by_role["carer"][0]
    m.step()
    assert k.sanction_charge("R3") == 0.5 and k.expected_sanction("R3") == 2.0
    m.step()  # breach: neglect nets 5 - 2 = 3 > care 1
    assert k.breached == ["R3"] and k.sanction_now == 0.5 and k.last_payoff == 4.5
    assert k.expected_sanction("R3") == 4.0  # graduated: 1.0 per step over 4 steps
    realised = m.payoff(k.chosen) - k.last_payoff
    for _ in range(5):
        m.step()
        if k.breached:
            break
        realised += m.payoff(k.chosen) - k.last_payoff
    assert k.breach_count == 1, "re-breach inside the window: 5 - 4 = 1 is not > 1"
    assert realised == 2.0  # 0.5 at each of the 4 sanctioned steps
    with_one_step = InstitutionModel(kibbutz_like(), seed=0, agents_per_role=2, payoffs=pay,
                                     params={"sanction_weight": 1.0, "sanction_steps": 1, "copy_rate": 0.0})
    k1 = with_one_step.by_role["carer"][0]
    with_one_step.step()
    assert k1.expected_sanction("R3") == 1.0 == k1.sanction_charge("R3")


# ---------------------------------------------------------------- item 2 (b): A5 from declared arg_roles

def test_bearing_uses_declared_arg_roles_not_instance_values():
    """With provides_care untyped and the aim written over a variable `x` (typed child only through var_roles),
    bearing is read from the declaration: without var_roles nobody is borne on even though the instance's second
    argument is the child agent; with var_roles the child is."""
    inst = kibbutz_like(fluent_arg_roles=None)
    typed = InstitutionModel(inst, seed=0, agents_per_role=4)
    assert typed.bears_on(ATOM, "child", "carer")  # literal role name in the aim counts as a declaration
    assert not typed.bears_on(ATOM, "committee", "carer") and not typed.bears_on(ATOM, "carer", "carer")
    untyped = kibbutz_like(fluent_arg_roles=None)
    for r in untyped.rules:
        if r.id == "R3":
            r.aim = "(provides_care carer x)"
    m = InstitutionModel(untyped, seed=0, agents_per_role=4)
    m.step()
    atoms = m.state_obligation_rules("carer")
    atom_x = next(a for a in atoms if a[1][1] == "child")  # untyped x: one instance per agent, this one the child's
    assert not m.bears_on(atom_x, "child", "carer")  # instance value is the child, but no declaration types x
    m.step()
    assert all(c.trust == {} for c in m.by_role["child"])
    for r in untyped.rules:
        if r.id == "R3":
            r.var_roles = {"x": "child"}
    m2 = InstitutionModel(untyped, seed=0, agents_per_role=4)
    m2.step(); m2.step()
    assert all(c.trust for c in m2.by_role["child"] if any(n.role == "carer" for n in c.neighbours))
    # action-aimed obligations: arg_roles on the action, not the instance
    shop = InstitutionJSON.model_validate({
        "id": "shop", "roles": [{"name": "boss"}, {"name": "worker"}],
        "fluents": [{"name": "open", "arity": 0}],
        "actions": [{"name": "pay", "args": ["b", "w"], "arg_roles": ["boss", "worker"]},
                    {"name": "greet", "args": ["b", "p"]}],  # p: no arg_roles, no role prefix
        "rules": [{"id": "R1", "attribute": "boss", "deontic": "must", "aim": "(pay b w)", "conditions": "true",
                   "strand": "rival", "or_else": "R2"},
                  {"id": "R2", "attribute": "boss", "deontic": "must", "aim": "(greet b p)", "conditions": "true",
                   "strand": "rival", "or_else": "R1"}],
        "initial": []})
    ms = InstitutionModel(shop, seed=0, agents_per_role=2)
    assert ms.bears_on(("pay", ("boss", "worker")), "worker", "boss")
    assert not ms.bears_on(("greet", ("boss", "worker")), "worker", "boss")  # p is untyped: bears on nobody


# ---------------------------------------------------------------- item 2 (c): payoff.<action> axes are validated

def test_sweep_payoff_axis_must_name_a_declared_action(capsys, tmp_path):
    inst = kibbutz_like()
    with pytest.raises(ValueError, match=r"payoff\.nurture.*not an action.*declared actions"):
        sweep(inst, {"payoff.nurture": [1.0, 2.0]}, seeds=1, steps=1, agents_per_role=2)
    out = sweep(inst, {"payoff.neglect": [0.1, 5.0]}, seeds=2, steps=3, agents_per_role=2)
    assert len(out["grid"]) == 2
    path = tmp_path / "institutions.json"
    path.write_text(json.dumps([inst.model_dump(mode="json")]))
    assert main(["abm", "sweep", "--institution", inst.id, "--seeds", "1", "--param", "payoff.nurture=0:1:2",
                 "--steps", "1", "--agents-per-role", "2", "--institutions", str(path)]) == 2
    assert "not an action" in capsys.readouterr().err


# ---------------------------------------------------------------- item 2 (d): conflicting musts

def test_conflicting_musts_are_reported_not_crashed():
    """Two musts on one role in one state over different actions (pay and train, one action per agent per step)
    leave no lawful action: the run completes and the report names both rule ids once."""
    inst = InstitutionJSON.model_validate({
        "id": "torn", "roles": [{"name": "boss"}, {"name": "worker"}],
        "fluents": [{"name": "open", "arity": 0}],
        "actions": [{"name": "pay", "args": ["boss", "worker"]}, {"name": "train", "args": ["boss"]}],
        "rules": [{"id": "R1", "attribute": "boss", "deontic": "must", "aim": "(pay boss worker)",
                   "conditions": "true", "strand": "rival", "or_else": "R2"},
                  {"id": "R2", "attribute": "boss", "deontic": "must", "aim": "(train boss)",
                   "conditions": "true", "strand": "rival", "or_else": "R1"}],
        "initial": []})
    rep = run_abm(inst, seed=0, steps=4, agents_per_role=3)
    ws = [w for w in rep.warnings if w.startswith("inconsistent encoding")]
    assert len(ws) == 1 and "R1, R2" in ws[0] and "role boss" in ws[0] and "on 4 step(s)" in ws[0], rep.warnings
    assert all(v["boss"] == 1.0 for v in rep.breaches)  # every boss breaches one of the two at every step
    # a must on a forbidden action is the same shape (must pay, must_not pay)
    inst.rules[1].deontic = "must_not"
    inst.rules[1].aim = "(pay boss worker)"
    ws = [w for w in run_abm(inst, seed=0, steps=2, agents_per_role=2).warnings if w.startswith("inconsistent")]
    assert len(ws) == 1 and "R1, R2" in ws[0]
    # consistent musts (two rules on the same action) are not flagged
    inst.rules[1].deontic = "must"
    assert not any(w.startswith("inconsistent") for w in run_abm(inst, seed=0, steps=2, agents_per_role=2).warnings)
