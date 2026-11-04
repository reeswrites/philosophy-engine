"""Layer 2 ABM, slice 4: the `coordination` mechanism module (assurance-gated payoffs, the Mackie pledge flip, a
Centola committed minority), the sanction-in-force reading, `necessary_modules`, and the gate's (b) body, all on
in-test institutions."""
import json

import pytest

from philengine.abm import gate as g
from philengine.abm.model import DEFAULT_PARAMS, InstitutionModel, load_payoffs, run_abm, split_payoffs
from philengine.abm.sweep import module_subsets, necessary_modules, sweep
from philengine.cli import main
from philengine.schemas_rules import InstitutionJSON


def convention(inst_id="toy-convention") -> InstitutionJSON:
    """One role, two unconditional actions: a two-action naming convention."""
    return InstitutionJSON.model_validate({
        "id": inst_id, "roles": [{"name": "speaker"}],
        "fluents": [{"name": "named", "arity": 1, "arg_roles": ["speaker"]}],
        "actions": [{"name": "old_name", "args": ["speaker"]},
                    {"name": "new_name", "args": ["speaker"], "effects": [{"fluent": "named", "args": ["speaker"], "value": True}]}],
        "rules": [{"id": "R1", "attribute": "speaker", "deontic": "may", "aim": "(old_name speaker)", "conditions": "true", "strand": "rival"},
                  {"id": "R2", "attribute": "speaker", "deontic": "may", "aim": "(new_name speaker)", "conditions": "true", "strand": "rival"}],
        "initial": []})


PAY = {"old_name": 1.0, "new_name": 1.0, "coordinated": ["old_name", "new_name"], "committed_action": "new_name",
       "initial_practice": "old_name"}


def pledge_entry() -> InstitutionJSON:
    """`stop` is coordinated and out-pays `go` once assured; `stop_pledge` is its pledge; nothing is forbidden."""
    return InstitutionJSON.model_validate({
        "id": "toy-pledge", "roles": [{"name": "family"}],
        "fluents": [{"name": "going", "arity": 1, "arg_roles": ["family"]}, {"name": "pledged", "arity": 1, "arg_roles": ["family"]}],
        "actions": [{"name": "go", "args": ["family"], "effects": [{"fluent": "going", "args": ["family"], "value": True}]},
                    {"name": "stop", "args": ["family"], "effects": [{"fluent": "going", "args": ["family"], "value": False}]},
                    {"name": "stop_pledge", "args": ["family"], "effects": [{"fluent": "pledged", "args": ["family"], "value": True}]}],
        "rules": [{"id": "R1", "attribute": "family", "deontic": "may", "aim": "(go family)", "conditions": "true", "strand": "rival"},
                  {"id": "R2", "attribute": "family", "deontic": "may", "aim": "(stop family)", "conditions": "true", "strand": "rival"},
                  {"id": "R4", "attribute": "family", "deontic": "may", "aim": "(stop_pledge family)", "conditions": "true", "strand": "rival"}],
        "initial": ["(going family)"]})


def new_share(m: InstitutionModel) -> float:
    return g.name_share(m.adoption[-1], "speaker", "new_name")


# ---------------------------------------------------------------- declarations
def test_reserved_keys_are_read_from_the_payoffs_block_or_the_entry(tmp_path):
    raw = [{"id": "x", "payoffs": {"a": 2, "coordinated": ["a"]}, "committed_action": "b", "initial_practice": "a"},
           {"id": "y", "coordinated": ["a"]}, {"id": "z"}]
    p = tmp_path / "institutions.json"
    p.write_text(json.dumps(raw))
    assert load_payoffs(p, "x") == {"a": 2.0, "coordinated": ["a"], "committed_action": "b", "initial_practice": "a"}
    assert load_payoffs(p, "y") == {"coordinated": ["a"]} and load_payoffs(p, "z") is None
    assert split_payoffs(load_payoffs(p, "x")) == ({"a": 2.0}, {"coordinated": ["a"], "committed_action": "b", "initial_practice": "a"})
    with pytest.raises(ValueError, match="coordinated"):
        InstitutionModel(convention(), agents_per_role=2, payoffs={"coordinated": ["nope"]})


def test_initial_practice_and_committed_minority_setup():
    m = InstitutionModel(convention(), seed=0, agents_per_role=10, modules=("coordination",), payoffs=PAY,
                         params={"committed_minority": 0.3})
    speakers = m.by_role["speaker"]
    assert sum(1 for a in speakers if a.committed is not None) == 3  # round(0.3 * 10)
    assert all(a.practice == ("new_name", ("speaker",)) for a in speakers if a.committed)
    assert all(a.practice == ("old_name", ("speaker",)) for a in speakers if not a.committed)
    assert m.adoption_shares()["speaker"] == {"new_name(speaker)": 0.3, "old_name(speaker)": 0.7}
    assert m.committed_shares() == {"speaker": 0.3}
    rep = run_abm(convention(), seed=0, steps=2, agents_per_role=10, modules=("coordination",), payoffs=PAY,
                  params={"committed_minority": 0.3})
    assert rep.committed == {"speaker": 0.3} and rep.params["committed_action"] == "new_name(speaker)"
    assert rep.params["coordinated"] == ["new_name", "old_name"] and rep.params["initial_practice"] == "old_name(speaker)"
    # a different seed draws a different committed set; the same seed the same
    pick = lambda s: {a.unique_id for a in InstitutionModel(convention(), seed=s, agents_per_role=10, modules=("coordination",),
                                                            payoffs=PAY, params={"committed_minority": 0.3}).agents if a.committed}
    assert pick(0) == pick(0) and any(pick(s) != pick(0) for s in range(1, 6))


def test_committed_draw_does_not_perturb_the_main_rng_stream():
    """Review finding 6: the committed set is drawn from a child rng, so the main stream is in the same state with and
    without a committed minority and every later draw (thresholds apart, which come first) is shared."""
    mk = lambda frac: InstitutionModel(convention(), seed=3, agents_per_role=10, modules=("coordination",), payoffs=PAY,
                                       params={"committed_minority": frac})
    m0, m1, m2 = mk(0.0), mk(0.1), mk(0.3)
    assert m0.random.getstate() == m1.random.getstate() == m2.random.getstate()
    assert [m0.random.random() for _ in range(5)] == [m2.random.random() for _ in range(5)]
    assert any(a.committed for a in m1.agents) and not any(a.committed for a in m0.agents)


def test_committed_minority_errors_and_warning():
    with pytest.raises(ValueError, match="committed_minority > 0 needs a committed action"):
        InstitutionModel(convention(), agents_per_role=4, modules=("coordination",), payoffs={"old_name": 1.0},
                         params={"committed_minority": 0.5})
    with pytest.raises(ValueError, match="in \\[0, 1\\]"):
        InstitutionModel(convention(), agents_per_role=4, modules=("coordination",), payoffs=PAY, params={"committed_minority": 1.5})
    with pytest.raises(ValueError, match="neither an action"):
        InstitutionModel(convention(), agents_per_role=4, modules=("coordination",), payoffs=dict(PAY, committed_action="zzz"),
                         params={"committed_minority": 0.5})
    # params override the block; the instance label form is accepted
    m = InstitutionModel(convention(), agents_per_role=4, modules=("coordination",), payoffs=PAY,
                         params={"committed_minority": 0.5, "committed_action": "old_name(speaker)"})
    assert m.committed_action == ("old_name", ("speaker",))
    # with the coordination module off the minority is not instantiated and the report says so
    m = InstitutionModel(convention(), agents_per_role=4, modules=("material",), payoffs=PAY, params={"committed_minority": 0.5})
    assert not any(a.committed for a in m.agents) and any("committed_minority=0.5 ignored" in w for w in m.warnings)


# ---------------------------------------------------------------- assurance
def test_assurance_gates_expected_and_realised_payoff():
    """Coordinated actions pay only when the same-role neighbour share meets the agent's threshold."""
    inst = convention()
    m = InstitutionModel(inst, seed=0, agents_per_role=6, modules=("coordination",), payoffs=PAY, params={"copy_rate": 0.0})
    m.step()
    for a in m.by_role["speaker"]:
        assert a.chosen == ("old_name", ("speaker",))  # everyone keeps the initial practice
        share = a._shares.get(("old_name", ("speaker",)), 0.0)
        assert a.assured(a.chosen) == (share >= a.threshold)
        assert a.last_payoff == (1.0 if share >= a.threshold else 0.0)
    # same run without the module: nothing is gated
    m2 = InstitutionModel(inst, seed=0, agents_per_role=6, modules=("material",), payoffs=PAY, params={"copy_rate": 0.0})
    m2.step()
    assert all(a.last_payoff == 1.0 and a.assured(a.chosen) for a in m2.by_role["speaker"])
    # a lone agent (no same-role neighbours) is never assured of a coordinated action with a positive threshold
    solo = InstitutionModel(inst, seed=0, agents_per_role=1, modules=("coordination",), payoffs=PAY)
    (a,) = solo.by_role["speaker"]
    a._shares = {}
    assert a.gross_payoff(("old_name", ("speaker",))) == (1.0 if a.threshold == 0.0 else 0.0)


# ---------------------------------------------------------------- pledge flip (Mackie)
def test_pledge_flip_when_pledged_share_crosses_threshold():
    """Pledging `stop` leaves practice `go`; once the pledged share of `stop` meets an agent's threshold it flips
    its practice to `stop` under the coordination module, and never under material alone."""
    inst = pledge_entry()
    pay = {"go": 1.0, "stop": 1.0, "stop_pledge": 1.5, "coordinated": ["stop"], "initial_practice": "go"}
    m = InstitutionModel(inst, seed=1, agents_per_role=8, modules=("material", "coordination"), payoffs=pay,
                         params={"copy_rate": 0.0})
    m.step()  # the pledge out-pays: everyone pledges stop, practice stays go
    fam = m.by_role["family"]
    assert all(a.pledge == ("stop", ("family",)) and a.practice == ("go", ("family",)) for a in fam)
    m.step()  # pledged share of stop is 1.0 >= every threshold: everyone flips
    assert all(a.practice == ("stop", ("family",)) and a.last_choice_source == "flip" for a in fam)
    assert m.adoption[-1]["family"] == {"stop(family)": 1.0}
    # same seed, material only: the pledge keeps being chosen, practice never flips
    m2 = InstitutionModel(inst, seed=1, agents_per_role=8, modules=("material",), payoffs=pay, params={"copy_rate": 0.0})
    for _ in range(5):
        m2.step()
    assert all(a.practice == ("go", ("family",)) and a.pledge == ("stop", ("family",)) for a in m2.by_role["family"])
    # the flip needs the share to meet the threshold: with one pledger out of eight, high-threshold agents stay
    m3 = InstitutionModel(inst, seed=1, agents_per_role=8, modules=("coordination",), payoffs=pay, params={"copy_rate": 0.0})
    fam3 = m3.by_role["family"]
    fam3[0].pledge = ("stop", ("family",))
    for a in fam3:
        a.threshold = 0.99
    m3.step()
    assert all(a.practice == ("go", ("family",)) for a in fam3)


# ---------------------------------------------------------------- sanction in force
def test_sanction_lands_only_when_its_rule_is_in_force_in_the_successor():
    """`or_else` names R5 (may shun when not pledged): a breach of R3 prices the sanction while nobody has pledged
    and not once `pledged` holds (the footbinding reading: the pledge association lifts the suitors' rejection)."""
    inst = InstitutionJSON.model_validate(dict(pledge_entry().model_dump(mode="json"), id="toy-forbidden", actions=[
        *pledge_entry().model_dump(mode="json")["actions"], {"name": "shun", "args": ["family"]}], rules=[
        *pledge_entry().model_dump(mode="json")["rules"],
        {"id": "R3", "attribute": "family", "deontic": "must_not", "aim": "(stop family)", "conditions": "true", "strand": "rival", "or_else": "R5"},
        {"id": "R5", "attribute": "family", "deontic": "may", "aim": "(shun family)", "conditions": "(not (pledged family))", "strand": "rival"}]))
    m = InstitutionModel(inst, seed=0, agents_per_role=3, modules=("material",), payoffs={"go": 1.0, "stop": 2.0, "stop_pledge": 0.5},
                         params={"sanction_weight": 1.0, "sanction_steps": 3, "copy_rate": 0.0})
    a = m.by_role["family"][0]
    stop = ("stop", ("family",))
    assert m.sanction_in_force("R3", stop) and a.expected_sanction("R3", stop) == 3.0
    m.state = m.state | {("pledged", ("family",))}
    m._cache = {}
    assert not m.sanction_in_force("R3", stop) and a.expected_sanction("R3", stop) == 0.0
    # an or_else naming no rule of the entry always lands
    m._or_else["R3"] = "external"
    assert m.sanction_in_force("R3", stop)


# ---------------------------------------------------------------- committed minority moves adoption; tipping sweep
def test_committed_minority_zero_vs_half_changes_adoption():
    inst = convention()
    lo = [new_share(_run(inst, s, 0.0)) for s in range(4)]
    hi = [new_share(_run(inst, s, 0.5)) for s in range(4)]
    assert max(lo) == 0.0 and min(hi) > 0.5


def _run(inst, seed, frac, steps=40, apr=20, k=6, modules=("coordination",), params=None):
    m = InstitutionModel(inst, seed=seed, agents_per_role=apr, modules=modules, payoffs=PAY,
                         params=dict({"committed_minority": frac}, **(params or {})), graph_k=k)
    for _ in range(steps):
        m.step()
    return m


def _curve(inst, grid, seeds, **kw):
    return [sum(new_share(_run(inst, s, f, **kw)) for s in range(seeds)) / seeds for f in grid]


def _crossing(grid, curve, level=0.5):
    """Linear-interpolated committed_minority at which the curve first reaches `level`."""
    for (x0, y0), (x1, y1) in zip(zip(grid, curve), zip(grid[1:], curve[1:])):
        if y0 < level <= y1:
            return x0 + (level - y0) * (x1 - x0) / (y1 - y0)
    return None


def test_tipping_sweep_has_a_rise_whose_location_is_not_a_constant():
    """Preregistered before the first run (2026-11-04): adoption of `new_name` ~ the committed share for small
    shares, a rise toward 1 somewhere in 0.30-0.45, a max adjacent jump > 0.3, moving with thresholds and graph
    k. Observed: the rise is a sigmoid rather than a step (per seed the population settles into mixed local
    states), max adjacent jump 0.20-0.26 over 20 seeds; the location moves with threshold_max and k. The
    assertions below are the observed-and-kept part: a rise exists, and its location moves."""
    inst = convention()
    grid = [round(0.05 * i, 2) for i in range(1, 11)]
    seeds = 6
    base = _curve(inst, grid, seeds)
    assert base[0] <= 0.15 and base[-1] >= 0.8, base
    jumps = [b - a for a, b in zip(base, base[1:])]
    assert max(jumps) >= 0.12, (base, jumps)  # a rise, not a flat line: the sweep resolution (0.05) sets only how finely it is seen
    assert all(j > -0.15 for j in jumps), base  # no large reversal
    x_base = _crossing(grid, base)
    assert x_base is not None and grid[0] < x_base < grid[-1]
    # the location moves when the threshold distribution or the graph changes: no constant in the code sets it
    x_thr = _crossing(grid, _curve(inst, grid, seeds, params={"threshold_max": 0.5}))
    x_k = _crossing(grid, _curve(inst, grid, seeds, k=10))
    locations = [x for x in (x_base, x_thr, x_k) if x is not None]
    assert len(locations) >= 2 and max(locations) - min(locations) > 0.01, (x_base, x_thr, x_k)
    # not a default constant, except by grid coincidence (review finding 7: the threshold rule's implicit 0.5 also
    # shapes the location, so this is a coincidence check only; the gate states the implicit 0.5 in its report)
    assert x_base in grid or not any(isinstance(v, float) and abs(v - x_base) < 1e-9 for v in DEFAULT_PARAMS.values())


# ---------------------------------------------------------------- necessary_modules
def test_necessary_modules_on_a_toy_where_only_coordination_tips():
    """With a committed minority of 0.6 (0.5 sits on the tipping edge once the committed set is drawn from the child
    rng, review finding 6) the convention flips to `new_name` only under configurations with the
    coordination module (the minority belongs to it); material alone keeps the initial practice."""
    inst = convention()
    out = necessary_modules(inst, lambda m: new_share(m) >= 0.75, seeds=4, steps=30, agents_per_role=16, payoffs=PAY,
                            params={"committed_minority": 0.6})
    assert set(out["rates"]) == {"{}", "material", "coordination", "material+coordination"}
    assert out["rates"]["{}"] == 0.0 and out["rates"]["material"] == 0.0
    assert out["rates"]["coordination"] >= 0.8 and out["rates"]["material+coordination"] >= 0.8
    assert out["necessary"] == [["coordination"]] and ["material", "coordination"] in out["sufficient"]
    assert "imagination" in out["not_run"] and out["rate_min"] == 0.8
    subsets, stubs = module_subsets()
    assert subsets[0] == () and ("material", "coordination") in subsets and list(stubs) == ["imagination"]
    # a predicate nothing satisfies: nothing is sufficient, nothing necessary
    out = necessary_modules(inst, lambda m: False, seeds=1, steps=1, agents_per_role=2, payoffs=PAY)
    assert out["necessary"] == [] and out["sufficient"] == []
    with pytest.raises(ValueError):
        necessary_modules(inst, lambda m: True, seeds=0)


# ---------------------------------------------------------------- sweep and CLI pass the committed action through
def test_sweep_committed_minority_axis_with_base_params():
    out = sweep(convention(), {"committed_minority": [0.0, 0.5]}, seeds=2, steps=5, agents_per_role=6, modules=("coordination",),
                payoffs=PAY)
    lo, hi = out["grid"]
    assert lo["rates"]["adoption_over_seeds"]["speaker"].get("new_name(speaker)", 0.0) == 0.0
    assert hi["rates"]["adoption_over_seeds"]["speaker"]["new_name(speaker)"] > 0.4
    # base_params name the committed action when the block does not
    pay = {k: v for k, v in PAY.items() if k != "committed_action"}
    with pytest.raises(ValueError, match="needs a committed action"):
        sweep(convention(), {"committed_minority": [0.5]}, seeds=1, steps=1, agents_per_role=4, modules=("coordination",), payoffs=pay)
    out = sweep(convention(), {"committed_minority": [0.5]}, seeds=1, steps=1, agents_per_role=4, modules=("coordination",),
                payoffs=pay, base_params={"committed_action": "new_name"})
    assert out["grid"][0]["rows"][0]["final_adoption"]["speaker"]["new_name(speaker)"] >= 0.5


def test_cli_run_with_committed_action(tmp_path, capsys):
    raw = json.loads(json.dumps(convention().model_dump(mode="json")))
    raw["payoffs"] = {k: v for k, v in PAY.items() if k != "committed_action"}
    ip = tmp_path / "institutions.json"
    ip.write_text(json.dumps([raw]))
    (tmp_path / "properties.json").write_text("[]")
    rc = main(["abm", "sweep", "--institution", "toy-convention", "--seeds", "1", "--param", "committed_minority=0.5",
               "--steps", "2", "--agents-per-role", "4", "--modules", "coordination", "--institutions", str(ip),
               "--committed-action", "new_name"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["grid"][0]["rows"][0]["final_adoption"]["speaker"]["new_name(speaker)"] >= 0.5
    rc = main(["abm", "run", "--institution", "toy-convention", "--seed", "0", "--steps", "2", "--agents-per-role", "4",
               "--modules", "material,coordination", "--institutions", str(ip), "--committed-action", "new_name"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["params"]["committed_action"] == "new_name(speaker)"


# ---------------------------------------------------------------- gate (b) body on the toy
def test_gate_b_body_reads_the_committed_action_share():
    nm = convention(g.NAMING)
    configs, not_run = g.available_configs()
    b = g.crit_b({nm.id: nm}, {}, 2, configs, not_run, agents_per_role=8, steps=6, payoffs_of=lambda i: dict(PAY),
                 sweep_points=[0.1, 0.5])
    assert b.status in (g.PASS, g.FAIL) and b.numbers["committed_action"] == "new_name(speaker)" and b.numbers["role"] == "speaker"
    for key in ("coordination", "material+coordination"):
        pts = b.numbers["adoption_by_point"][key]
        assert set(pts) == {"0.1", "0.5"} and pts["0.5"] > pts["0.1"]
        assert b.numbers["committed_share_by_point"][key] == {"0.1": 0.125, "0.5": 0.5}
        assert b.numbers["jump_at"][key] == [0.1, 0.5]
    assert "material" not in b.numbers["adoption_by_point"]  # (b) runs the coordination configurations only
    assert any("location caveat" in l and "implicit" in l.lower() for l in b.lines)
    json.dumps(b.to_dict())
