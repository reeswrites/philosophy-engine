"""Layer 2 ABM, slice 1: report shape, seed determinism, dataset run, module stubs, CLI."""
import json

import pytest

from philengine.abm import AbmReport, InstitutionModel, run_abm
from philengine.abm.model import MODULES
from philengine.cli import main
from philengine.schemas_rules import InstitutionJSON, load_institutions

from .helpers import require_dataset


def tiny() -> InstitutionJSON:
    return InstitutionJSON.model_validate({
        "id": "tiny-shop",
        "roles": [{"name": "worker"}, {"name": "boss"}],
        "fluents": [{"name": "paid", "arity": 1, "arg_roles": ["worker"]},
                    {"name": "can_quit", "arity": 1, "arg_roles": ["worker"], "params": ["w"],
                     "derived": "(enabled quit w)"}],
        "actions": [{"name": "work", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": True}]},
                    {"name": "quit", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": False}]},
                    {"name": "pay", "args": ["boss", "worker"]},
                    {"name": "sweep", "args": ["worker"]}],
        "rules": [{"id": "R1", "attribute": "worker", "deontic": "may", "aim": "(work worker)", "conditions": "true", "strand": "rival"},
                  {"id": "R2", "attribute": "worker", "deontic": "may", "aim": "(quit worker)", "conditions": "(paid worker)", "strand": "rival"},
                  {"id": "R3", "attribute": "boss", "deontic": "must", "aim": "(pay boss worker)", "conditions": "(paid worker)",
                   "strand": "rival", "or_else": "R1"}],
        "initial": [],
    })


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
    a = run_abm(tiny(), seed=7, steps=12, agents_per_role=5).to_json()
    b = run_abm(tiny(), seed=7, steps=12, agents_per_role=5).to_json()
    assert a == b


def test_different_seeds_may_differ():
    reps = {run_abm(tiny(), seed=s, steps=12, agents_per_role=8).to_json() for s in range(6)}
    assert len(reps) > 1, "six seeds produced one identical report: the rng is not threaded through the run"


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


def test_payoffs_steer_material_adoption():
    inst = tiny()
    rep = run_abm(inst, seed=1, steps=10, agents_per_role=6, payoffs={"quit": 5.0, "work": 1.0})
    final = rep.final_adoption()["worker"]
    assert final.get("quit(worker)", 0.0) > 0.5


def test_stub_modules_raise():
    for mod in ("coordination", "imagination"):
        assert mod in MODULES
        with pytest.raises(NotImplementedError):
            run_abm(tiny(), seed=0, steps=1, agents_per_role=2, modules=["material", mod])
    with pytest.raises(ValueError):
        run_abm(tiny(), seed=0, steps=1, agents_per_role=2, modules=["telepathy"])


def test_runs_on_dataset_institution():
    ip, _ = require_dataset()
    insts = {i.id: i for i in load_institutions(ip)}
    inst = insts.get("kibbutz-childrens-house") or next(iter(insts.values()))
    rep = run_abm(inst, seed=0, steps=20, agents_per_role=20)
    _check_shape(rep, inst, 20, 20)
    assert rep.to_json() == run_abm(inst, seed=0, steps=20, agents_per_role=20).to_json()


def test_cli_abm_run(capsys, dataset_env):
    ip, _ = dataset_env
    insts = load_institutions(ip)
    inst_id = "kibbutz-childrens-house" if any(i.id == "kibbutz-childrens-house" for i in insts) else insts[0].id
    assert main(["abm", "run", "--institution", inst_id, "--seed", "3", "--steps", "4", "--agents-per-role", "3",
                 "--institutions", str(ip)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["seed"] == 3 and d["steps"] == 4 and d["agents_per_role"] == 3
    assert main(["abm", "run", "--institution", "no-such-institution", "--institutions", str(ip)]) == 2
