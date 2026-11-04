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


# ---------------------------------------------------------------- slice 2: breach (A4), trust (A5), pledge (A3), sweep (A7)

def shop_with_rest(or_else="R1", rest_payoff=10.0):
    """The boss must pay once the worker is paid (sanctionable iff or_else); `rest` is a tempting alternative."""
    return tiny(extra_actions=[{"name": "rest", "args": ["boss"]}],
                extra_rules=[{"id": "R5", "attribute": "boss", "deontic": "may", "aim": "(rest boss)",
                              "conditions": "true", "strand": "rival"}]), {"rest": rest_payoff, "pay": 1.0}


def _no_sanction(inst):
    for r in inst.rules:
        if r.id == "R3":
            r.or_else = None
    return inst


def test_breach_when_payoff_beats_expected_sanction():
    inst, pay = shop_with_rest()
    cheap = InstitutionModel(inst, seed=0, agents_per_role=4, payoffs=pay, params=dict(sanction_weight=1.0, copy_rate=0.0))
    cheap.step(); cheap.step()  # step 2: paid(worker) holds, boss is obliged to pay; rest nets 10 - 1*3 > 1
    assert cheap.obligations_for("boss") == [("pay", ("boss", "worker"))]
    assert all(a.chosen == ("rest", ("boss",)) and a.breached == ["R3"] for a in cheap.by_role["boss"])
    assert cheap.breaches[-1]["boss"] == 1.0 and cheap.sanctioned[-1]["boss"] == 1.0
    assert all(a.last_payoff == 10.0 - 1.0 for a in cheap.by_role["boss"])  # sanction lands on the realised payoff
    dear = InstitutionModel(inst, seed=0, agents_per_role=4, payoffs=pay, params=dict(sanction_weight=100.0, copy_rate=0.0))
    dear.step(); dear.step()
    assert all(a.chosen == ("pay", ("boss", "worker")) and a.breached == [] for a in dear.by_role["boss"])
    assert dear.breaches[-1]["boss"] == 0.0
    # two sanctionable musts breached in one step: realised charge is the sum, matching the expected net in choose
    twice = tiny(extra_actions=[{"name": "rest", "args": ["boss"]}],
                 extra_rules=[{"id": "R5", "attribute": "boss", "deontic": "may", "aim": "(rest boss)",
                               "conditions": "true", "strand": "rival"},
                              {"id": "R6", "attribute": "boss", "deontic": "must", "aim": "(pay boss worker)",
                               "conditions": "(paid worker)", "strand": "rival", "or_else": "R1"}])
    double = InstitutionModel(twice, seed=0, agents_per_role=4, payoffs=pay, params=dict(sanction_weight=1.0, copy_rate=0.0))
    double.step(); double.step()  # rest nets 10 - 2*3 > 1 (two rules, three sanction steps each)
    assert all(a.chosen == ("rest", ("boss",)) and sorted(a.breached) == ["R3", "R6"] for a in double.by_role["boss"])
    assert all(a.sanction_now == 2.0 and a.last_payoff == 10.0 - 2.0 for a in double.by_role["boss"])


def test_graduated_sanction_and_sanction_steps():
    """Updated 2026-11-04 (slice-2 review item a): the expected sanction is the per-step charge times
    sanction_steps, the same total the agent then pays over the window; before, expectation was priced for one
    step while the charge ran for sanction_steps steps."""
    inst, pay = shop_with_rest()
    m = InstitutionModel(inst, seed=0, agents_per_role=2, payoffs=pay,
                         params=dict(sanction_weight=1.0, sanction_escalation=2.0, sanction_steps=2, copy_rate=0.0))
    boss = m.by_role["boss"][0]
    m.step()
    assert boss.sanction_charge("R3") == 1.0 and boss.expected_sanction("R3") == 2.0  # 1.0 per step * 2 steps
    assert boss.expected_sanction("R1") == 0.0  # R1 is a may: no sanction
    m.step()  # first breach: rest nets 10 - 2 > 1
    assert boss.breach_count == 1 and boss.sanction_now == 1.0 and boss.sanctioned
    assert boss.sanction_charge("R3") == 2.0 and boss.expected_sanction("R3") == 4.0  # graduated
    m.step()  # second breach: rest nets 10 - 4 > 1
    assert boss.breach_count == 2 and boss.sanction_now == 2.0 and boss.last_payoff == 8.0
    assert boss.sanctioned_until == m.t - 1 + 2


def test_must_without_or_else_is_free_to_breach():
    inst, pay = shop_with_rest()
    _no_sanction(inst)
    m = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs=pay, params=dict(sanction_weight=100.0, copy_rate=0.0))
    m.step(); m.step()
    assert all(a.chosen == ("rest", ("boss",)) and a.breached == ["R3"] and not a.sanctioned for a in m.by_role["boss"])
    assert m.sanctioned[-1]["boss"] == 0.0 and m.breaches[-1]["boss"] == 1.0


def test_sanctionable_must_not_is_breached_only_when_worth_it():
    forbid = {"id": "R4", "attribute": "worker", "deontic": "must_not", "aim": "(quit worker)",
              "conditions": "true", "strand": "rival", "or_else": "R3"}
    inst = tiny(extra_rules=[forbid])
    tempted = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs={"quit": 5.0, "work": 1.0},
                               params=dict(sanction_weight=1.0, copy_rate=0.0))
    tempted.step(); tempted.step()
    assert all(a.chosen == ("quit", ("worker",)) and a.breached == ["R4"] for a in tempted.by_role["worker"])
    deterred = InstitutionModel(inst, seed=0, agents_per_role=3, payoffs={"quit": 5.0, "work": 1.0},
                                params=dict(sanction_weight=10.0, copy_rate=0.0))
    deterred.step(); deterred.step()
    assert all(a.chosen == ("work", ("worker",)) for a in deterred.by_role["worker"])


def _worker_boss_pairs(m):
    return [(w, b) for w in m.by_role["worker"] for b in w.neighbours if b.role == "boss"]


def test_trust_rises_on_kept_and_falls_on_breached_obligation_bearing_on_me():
    inst, pay = shop_with_rest()
    kept = InstitutionModel(inst, seed=0, agents_per_role=6, payoffs=pay, params=dict(sanction_weight=100.0))
    kept.step(); kept.step()
    pairs = _worker_boss_pairs(kept)
    assert pairs
    assert all(w.trust[b.unique_id] == 0.5 + 0.1 for w, b in pairs)  # +delta on a kept obligation bearing on me
    broken = InstitutionModel(inst, seed=0, agents_per_role=6, payoffs=pay, params=dict(sanction_weight=1.0))
    broken.step(); broken.step()
    assert all(w.trust[b.unique_id] == 0.5 - 2.0 * 0.1 for w, b in _worker_boss_pairs(broken))  # -beta*delta
    # the obligation bears on the worker, not on other bosses: boss-boss trust never moves
    for b in broken.by_role["boss"]:
        assert all(b.trust.get(n.unique_id) is None for n in b.neighbours if n.role == "boss")


def test_obligation_without_role_argument_moves_no_trust():
    inst = tiny(extra_actions=[{"name": "train", "args": ["boss"]}],
                extra_rules=[{"id": "R6", "attribute": "boss", "deontic": "must", "aim": "(train boss)",
                              "conditions": "true", "strand": "rival", "or_else": "R1"}])
    m = InstitutionModel(inst, seed=0, agents_per_role=5)
    m.step()
    assert all(a.obligation_outcomes and a.obligation_outcomes[0][0] == ("train", ("boss",)) for a in m.by_role["boss"])
    assert all(w.trust == {} for w in m.by_role["worker"])


def test_pledge_sets_flag_not_practice_and_counts_in_shares():
    inst = tiny(extra_actions=[{"name": "quit_pledge", "args": ["worker"]}],
                extra_rules=[{"id": "R7", "attribute": "worker", "deontic": "may", "aim": "(quit_pledge worker)",
                              "conditions": "true", "strand": "rival"}])
    m = InstitutionModel(inst, seed=0, agents_per_role=6, payoffs={"quit_pledge": 3.0, "work": 1.0, "quit": 0.5},
                         params=dict(copy_rate=0.0))
    assert m.is_pledge(("quit_pledge", ("worker",))) and m.pledge_base(("quit_pledge", ("worker",))) == ("quit", ("worker",))
    m.step()  # pledging pays most: everyone pledges quit, nobody's practice changes (none -> stays none)
    assert all(a.pledge == ("quit", ("worker",)) and a.practice is None for a in m.by_role["worker"])
    m.agents.do("snapshot")
    w = next(a for a in m.by_role["worker"] if a.role_neighbours)
    assert w.neighbour_shares() == {("quit", ("worker",)): 1.0}
    assert m.adoption[-1]["worker"] == {"none": 1.0}


def test_sweep_grid_rows_and_rates():
    from philengine.abm.sweep import parse_param, sweep
    assert parse_param("copy_rate=0:1:3") == ("copy_rate", [0.0, 0.5, 1.0])
    assert parse_param("floor=2") == ("floor", [2.0]) and parse_param("floor=2:9:1") == ("floor", [2.0])
    with pytest.raises(ValueError):
        parse_param("floor=1:2")
    inst, pay = shop_with_rest()
    out = sweep(inst, {"sanction_weight": [0.0, 100.0], "payoff.rest": [10.0]}, seeds=3, steps=4, agents_per_role=3,
                payoffs=pay)
    assert len(out["grid"]) == 2 and all(len(g["rows"]) == 3 for g in out["grid"])
    assert [g["params"] for g in out["grid"]] == [{"sanction_weight": 0.0, "payoff.rest": 10.0},
                                                   {"sanction_weight": 100.0, "payoff.rest": 10.0}]
    cheap, dear = out["grid"]
    assert cheap["rates"]["breach_rate_over_seeds"]["boss"] > dear["rates"]["breach_rate_over_seeds"]["boss"] == 0.0
    assert "runs" not in cheap["rates"] and cheap["rates"]["seeds"] == [0, 1, 2]
    with pytest.raises(ValueError):
        sweep(inst, {"telepathy": [1.0]}, seeds=1, steps=1, agents_per_role=2)


def test_cli_abm_sweep(capsys, dataset_env):
    ip, _ = dataset_env
    inst_id = load_institutions(ip)[0].id
    assert main(["abm", "sweep", "--institution", inst_id, "--seeds", "2", "--param", "copy_rate=0:1:2",
                 "--steps", "3", "--agents-per-role", "2", "--institutions", str(ip)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["seeds"] == 2 and len(d["grid"]) == 2 and all(len(g["rows"]) == 2 for g in d["grid"])
    assert main(["abm", "sweep", "--institution", inst_id, "--seeds", "1", "--param", "nope=0:1:2",
                 "--institutions", str(ip)]) == 2
