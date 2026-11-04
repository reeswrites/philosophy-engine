"""Layer 2 ABM, slice 1: report shape, seed determinism, reference-driven readings, material floor, dataset run,
module stubs, CLI (single seed and rates over seeds)."""
import json

import pytest

from philengine.abm import AbmReport, InstitutionModel, run_abm, summarize
from philengine.abm.model import MODULES
from philengine.cli import main
from philengine.rules_reference import Reference
from philengine.schemas_rules import InstitutionJSON, load_institutions

from .helpers import require_dataset


def tiny(extra_rules=(), extra_actions=()) -> InstitutionJSON:
    return InstitutionJSON.model_validate({
        "id": "tiny-shop",
        "roles": [{"name": "worker"}, {"name": "boss"}],
        "fluents": [{"name": "paid", "arity": 1, "arg_roles": ["worker"]},
                    {"name": "can_quit", "arity": 1, "arg_roles": ["worker"], "params": ["w"],
                     "derived": "(enabled quit w)"}],
        "actions": [{"name": "work", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": True}]},
                    {"name": "quit", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": False}]},
                    {"name": "pay", "args": ["boss", "worker"]},
                    {"name": "sweep", "args": ["worker"]}, *extra_actions],
        "rules": [{"id": "R1", "attribute": "worker", "deontic": "may", "aim": "(work worker)", "conditions": "true", "strand": "rival"},
                  {"id": "R2", "attribute": "worker", "deontic": "may", "aim": "(quit worker)", "conditions": "(paid worker)", "strand": "rival"},
                  {"id": "R3", "attribute": "boss", "deontic": "must", "aim": "(pay boss worker)", "conditions": "(paid worker)",
                   "strand": "rival", "or_else": "R1"}, *extra_rules],
        "initial": [],
    })


def _strip_seed(rep: AbmReport) -> str:
    d = rep.to_dict()
    return json.dumps({"adoption": d["adoption"], "fluent_rates": d["fluent_rates"]}, sort_keys=True)


def _check_shape(rep: AbmReport, inst: InstitutionJSON, steps: int, n: int):
    d = json.loads(rep.to_json())
    assert d["institution"] == inst.id
    assert d["steps"] == steps and len(d["adoption"]) == steps
    assert d["agents_per_role"] == n
    assert d["modules"] == ["material"]
    assert set(d["roles"]) == {r.name for r in inst.roles}
    for step in d["adoption"]:
        assert set(step) == set(d["roles"])
        for role, shares in step.items():
            assert abs(sum(shares.values()) - 1.0) < 1e-9, (role, shares)
    assert set(d["fluent_rates"]) == {f.name for f in inst.fluents}
    assert all(0.0 <= v <= 1.0 for v in d["fluent_rates"].values())
    assert "payoffs" in d["params"] and "copy_rate" in d["params"]


def test_report_shape_tiny():
    inst = tiny()
    rep = run_abm(inst, seed=0, steps=6, agents_per_role=4)
    _check_shape(rep, inst, 6, 4)
    # workers only ever hold rule-granted actions: sweep has no may/must rule, so it is never a practice
    labels = {k for step in rep.adoption for k in step["worker"]}
    assert not any(k.startswith("sweep") for k in labels)
    assert any(k.startswith("work") or k.startswith("quit") for k in labels)


def test_same_seed_identical_report():
    a = run_abm(tiny(), seed=7, steps=12, agents_per_role=5)
    b = run_abm(tiny(), seed=7, steps=12, agents_per_role=5)
    assert _strip_seed(a) == _strip_seed(b)
    assert a.to_json() == b.to_json()


def test_different_seeds_may_differ():
    """With two equally paid unconditional actions the bootstrap tie-break is a seeded draw, so dynamics vary."""
    inst = tiny(extra_actions=[{"name": "sing", "args": ["worker"]}],
                extra_rules=[{"id": "R9", "attribute": "worker", "deontic": "may", "aim": "(sing worker)",
                              "conditions": "true", "strand": "rival"}])
    reps = {_strip_seed(run_abm(inst, seed=s, steps=12, agents_per_role=8)) for s in range(6)}
    assert len(reps) > 1, "six seeds produced identical dynamics: the rng is not threaded through the run"


def test_enabledness_comes_from_the_reference():
    """quit is enabled only once paid; at step 0 nobody is paid, so no worker can hold quit at the first step."""
    inst = tiny()
    m = InstitutionModel(inst, seed=0, agents_per_role=3)
    assert m.available_for("worker") == [("work", ("worker",))]
    assert m.obligations_for("boss") == []
    m.step()
    assert all(a.practice == ("work", ("worker",)) for a in m.by_role["worker"])
    # effects landed: paid(worker) now holds, so quit is available and the boss is obliged to pay
    assert ("quit", ("worker",)) in m.available_for("worker")
    assert m.obligations_for("boss") == [("pay", ("boss", "worker"))]
    m.step()
    assert all(a.chosen == ("pay", ("boss", "worker")) for a in m.by_role["boss"])


def test_sanctionable_must_not_keeps_action_available():
    """ADR 0013: only an or_else-null disability bars a power. A sanctionable must_not leaves `quit` available
    (available_for == Reference.power) but strict compliance keeps agents from firing it."""
    inst = tiny(extra_rules=[{"id": "R4", "attribute": "worker", "deontic": "must_not", "aim": "(quit worker)",
                              "conditions": "true", "strand": "rival", "or_else": "R3"}])
    m = InstitutionModel(inst, seed=0, agents_per_role=3)
    m.step()  # everyone works -> paid
    ref = Reference(inst, k=1)
    for role in m.roles:
        expected = [a for a in ref.action_insts if a[1] and a[1][0] == role and ref.power(m.state, a[0], a[1])]
        assert m.available_for(role) == expected
    assert ("quit", ("worker",)) in m.available_for("worker")
    assert m.forbidden_for("worker") == [("quit", ("worker",))]
    rep_m = InstitutionModel(inst, seed=0, agents_per_role=3)
    for _ in range(8):
        rep_m.step()
        assert all(a.chosen != ("quit", ("worker",)) for a in rep_m.by_role["worker"])
    # a disability (or_else null) does remove the power
    inst2 = tiny(extra_rules=[{"id": "R4", "attribute": "worker", "deontic": "must_not", "aim": "(quit worker)",
                               "conditions": "true", "strand": "rival", "or_else": None}])
    m2 = InstitutionModel(inst2, seed=0, agents_per_role=3)
    m2.step()
    assert ("quit", ("worker",)) not in m2.available_for("worker")


def test_material_floor_binds():
    """With no income the surplus decays below the floor and the choice set collapses to current practice: a worker
    then keeps `work` even though `quit` pays five times more. With default income it switches."""
    inst = tiny()
    starved = dict(default_income=0.0, initial_surplus=1.0, floor=1.0, floor_cost=0.5, copy_rate=0.0)
    m = InstitutionModel(inst, seed=0, agents_per_role=4, payoffs={"quit": 5.0, "work": 1.0}, params=starved)
    m.step()  # work (quit not yet enabled); surplus 1.0 -> 0.5 < floor
    assert all(a.surplus < m.params["floor"] for a in m.by_role["worker"])
    for _ in range(5):
        m.step()
        assert all(a.practice == ("work", ("worker",)) for a in m.by_role["worker"])
    fed = dict(starved, default_income=1.0)
    m2 = InstitutionModel(inst, seed=0, agents_per_role=4, payoffs={"quit": 5.0, "work": 1.0}, params=fed)
    m2.step(); m2.step()
    assert all(a.practice == ("quit", ("worker",)) for a in m2.by_role["worker"])


def test_income_fluents_accrue_surplus():
    inst = tiny()
    m = InstitutionModel(inst, seed=0, agents_per_role=2, payoffs={"paid": 3.0},
                         params=dict(initial_surplus=2.0, floor_cost=0.0))
    assert m.income_for("worker") == 0.0 and m.income_for("boss") == 0.0
    m.step()  # paid(worker) holds after this step
    assert m.income_for("worker") == 3.0 and m.income_for("boss") == 0.0
    m.step()
    assert all(a.surplus == 5.0 for a in m.by_role["worker"])
    assert all(a.surplus == 2.0 for a in m.by_role["boss"])


def test_payoffs_steer_material_adoption_over_seeds():
    """Over 20 seeds, the share of worker-steps spent on `quit` is substantial when it pays five times `work` and
    nil when it pays a tenth (quit unsets paid, so it can never be held two steps running: the ceiling is ~0.5)."""
    def rate(payoffs):
        tot = 0.0
        for s in range(20):
            rep = run_abm(tiny(), seed=s, steps=10, agents_per_role=6, payoffs=payoffs)
            tot += sum(step["worker"].get("quit(worker)", 0.0) for step in rep.adoption[1:]) / (rep.steps - 1)
        return tot / 20
    hi, lo = rate({"quit": 5.0, "work": 1.0}), rate({"quit": 0.1, "work": 1.0})
    assert hi > 0.3, hi
    assert lo < 0.05, lo


def test_shares_use_same_role_neighbours():
    m = InstitutionModel(tiny(), seed=0, agents_per_role=10)
    for a in m.agents:
        assert all(n.role == a.role for n in a.role_neighbours)
        assert set(a.role_neighbours) <= set(a.neighbours)
    m.step()  # every worker works
    m.agents.do("snapshot")
    w = next(a for a in m.by_role["worker"] if a.role_neighbours)
    assert w.neighbour_shares() == {("work", ("worker",)): 1.0}


def test_synchronous_update():
    """A choice reads the practices snapshotted at the step's start, not those already updated this step."""
    m = InstitutionModel(tiny(), seed=0, agents_per_role=4, params=dict(copy_rate=0.0))
    m.step()
    assert all(a.practice_prev is None for a in m.agents)  # the snapshot taken at the start of step 1 was empty
    m.step()
    assert all(a.practice_prev == ("work", ("worker",)) for a in m.by_role["worker"])


def test_stub_modules_raise():
    for mod in ("coordination", "imagination"):
        assert mod in MODULES
        with pytest.raises(NotImplementedError):
            run_abm(tiny(), seed=0, steps=1, agents_per_role=2, modules=["material", mod])
    with pytest.raises(ValueError):
        run_abm(tiny(), seed=0, steps=1, agents_per_role=2, modules=["telepathy"])


def test_summarize_rates():
    reps = [run_abm(tiny(), seed=s, steps=5, agents_per_role=3) for s in range(3)]
    s = summarize(reps)
    assert s["seeds"] == [0, 1, 2] and len(s["runs"]) == 3
    for role, shares in s["adoption_over_seeds"].items():
        assert abs(sum(shares.values()) - 1.0) < 1e-9, (role, shares)
    assert set(s["fluent_rates_over_seeds"]) == {"paid", "can_quit"}


def test_runs_on_dataset_institution():
    ip, _ = require_dataset()
    insts = {i.id: i for i in load_institutions(ip)}
    inst = insts.get("kibbutz-childrens-house") or next(iter(insts.values()))
    rep = run_abm(inst, seed=0, steps=20, agents_per_role=20)
    _check_shape(rep, inst, 20, 20)
    assert _strip_seed(rep) == _strip_seed(run_abm(inst, seed=0, steps=20, agents_per_role=20))


def test_cli_abm_run(capsys, dataset_env):
    ip, _ = dataset_env
    insts = load_institutions(ip)
    inst_id = "kibbutz-childrens-house" if any(i.id == "kibbutz-childrens-house" for i in insts) else insts[0].id
    assert main(["abm", "run", "--institution", inst_id, "--seed", "3", "--steps", "4", "--agents-per-role", "3",
                 "--institutions", str(ip)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["seed"] == 3 and d["steps"] == 4 and d["agents_per_role"] == 3
    assert main(["abm", "run", "--institution", inst_id, "--seeds", "3", "--steps", "4", "--agents-per-role", "3",
                 "--institutions", str(ip)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["seeds"] == [0, 1, 2] and len(d["runs"]) == 3 and "adoption_over_seeds" in d
    assert main(["abm", "run", "--institution", "no-such-institution", "--institutions", str(ip)]) == 2
