"""Layer 2 slice 3: veil-of-ignorance scorer (abm/score.py) and the layer-2 gate (abm/gate.py, `phil abm gate`).
In-test institutions for the scorer and the gate letters' logic; dataset-backed tests skip without the dataset."""
import json

import pytest

from philengine.abm import gate as g
from philengine.abm import run_abm, score, score_run
from philengine.abm.model import InstitutionModel
from philengine.abm.score import (VOICE_NULL, disagreement, exit_reader, probe, ranks, recognised, spearman,
                                  summarize_scores)
from philengine.cli import main
from philengine.schemas_rules import InstitutionJSON, Property, load_institutions, load_properties

from .helpers import require_dataset
from .test_abm import tiny


def solo(rules=None, quit_cond="true", inst_id="solo") -> InstitutionJSON:
    """One role, so the probe's role is fixed; `can_exit` is the dataset-style derived exit fluent."""
    return InstitutionJSON.model_validate({
        "id": inst_id,
        "roles": [{"name": "worker"}],
        "fluents": [{"name": "paid", "arity": 1, "arg_roles": ["worker"]},
                    {"name": "can_exit", "arity": 1, "arg_roles": ["worker"], "params": ["w"],
                     "derived": "(enabled quit w)"}],
        "actions": [{"name": "work", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": True}]},
                    {"name": "quit", "args": ["worker"], "effects": [{"fluent": "paid", "args": ["worker"], "value": False}]}],
        "rules": rules if rules is not None else [
            {"id": "R1", "attribute": "worker", "deontic": "may", "aim": "(work worker)", "conditions": "true", "strand": "rival"},
            {"id": "R2", "attribute": "worker", "deontic": "may", "aim": "(quit worker)", "conditions": quit_cond, "strand": "rival"}],
        "initial": [],
    })


# ---------------------------------------------------------------- rank statistics
def test_ranks_and_spearman():
    assert ranks([10, 30, 20]) == [1.0, 3.0, 2.0]
    assert ranks([1, 1, 2]) == [1.5, 1.5, 3.0]
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2, 3], [1, 3, 2]) == pytest.approx(0.5)
    assert spearman([1, 1, 1], [1, 2, 3]) is None  # no rank variance: undefined, never 1.0
    assert spearman([1], [1]) is None
    with pytest.raises(ValueError):
        spearman([1, 2], [1])


# ---------------------------------------------------------------- the probe
def test_probe_isolation_from_the_main_run():
    """The probe draws from model.random after the main run: the base report equals run_abm with the same seed,
    whatever the probe does, and the probe is not counted in adoption rates."""
    inst = tiny()
    base, ps = score_run(inst, seed=3, steps=8, probe_steps=5, agents_per_role=4)
    assert base.to_json() == run_abm(inst, seed=3, steps=8, agents_per_role=4).to_json()
    base2, ps2 = score_run(inst, seed=3, steps=8, probe_steps=1, agents_per_role=4)
    assert base2.to_json() == base.to_json()
    assert ps.probe_steps == 5 and ps.seed == 3 and ps.role in {"worker", "boss"}
    assert sum(ps.choice_sources.values()) == 5
    assert set(ps.choice_sources) <= {"copy", "switch", "threshold", "bootstrap", "keep", "obligation", "none"}
    # same seed, same probe
    assert score_run(inst, seed=3, steps=8, probe_steps=5, agents_per_role=4)[1].to_dict() == ps.to_dict()


def test_nulls_are_excluded_from_sums_and_named():
    """tiny() has a derived `can_quit` but no `can_exit`: exit is null with a reason, voice is always null."""
    _, ps = score_run(tiny(), seed=0, steps=4, probe_steps=3, agents_per_role=3)
    assert ps.freedom["exit"] is None and ps.freedom["voice"] is None
    assert "can_exit" in ps.nulls["exit"] and ps.nulls["voice"] == VOICE_NULL
    d = ps.to_dict()
    assert d["freedom_sum"]["excluded"] == ["exit", "voice"]
    assert d["freedom_sum"]["value"] == pytest.approx(ps.freedom["recognition"])
    assert d["flourishing_sum"]["excluded"] == []
    assert d["total"]["excluded"] == ["exit", "voice"]
    assert d["total"]["value"] == pytest.approx(d["freedom_sum"]["value"] + d["flourishing_sum"]["value"])
    s = score(tiny(), seeds=3, steps=4, probe_steps=3, agents_per_role=3)
    assert s["freedom"]["exit"] is None and s["freedom"]["voice"] is None
    assert s["freedom_sum"]["excluded"] == ["exit", "voice"] and len(s["per_seed"]) == 3
    assert s["seeds"] == [0, 1, 2] and s["nulls"]["voice"] == VOICE_NULL


def test_exit_reads_can_exit_through_the_reference_and_sanctions():
    # unconditional, unsanctioned quit: exit every probe step
    _, ps = score_run(solo(), seed=0, steps=3, probe_steps=4, agents_per_role=3)
    assert ps.role == "worker" and ps.freedom["exit"] == 1.0
    # a sanctionable must_not leaves the power (can_exit true) but the exit is sanctioned: 0.0
    rules = solo().model_dump()["rules"] + [{"id": "R3", "attribute": "worker", "deontic": "must_not",
                                             "aim": "(quit worker)", "conditions": "true", "strand": "rival", "or_else": "R1"}]
    _, ps = score_run(solo(rules=rules), seed=0, steps=3, probe_steps=4, agents_per_role=3)
    assert ps.freedom["exit"] == 0.0 and "exit" not in ps.nulls
    # a disability (or_else null) removes the power: can_exit false
    rules[-1]["or_else"] = None
    _, ps = score_run(solo(rules=rules), seed=0, steps=3, probe_steps=4, agents_per_role=3)
    assert ps.freedom["exit"] == 0.0
    # can_exit typed to another role: 0.0 with a note, not null
    inst = tiny()  # has can_quit, not can_exit
    inst.fluents[1].name = "can_exit"
    m = InstitutionModel(inst, seed=0, agents_per_role=2)
    read, note = exit_reader(m, "boss")
    assert read is not None and note and "typed to ['worker']" in note and read(m.state) is False


def test_recognition_names_the_role_in_a_condition():
    assert recognised(solo(), "worker") is False  # every condition is "true"
    assert recognised(solo(quit_cond="(paid worker)"), "worker") is True
    assert recognised(tiny(), "worker") is True and recognised(tiny(), "boss") is False
    _, ps = score_run(solo(quit_cond="(paid worker)"), seed=0, steps=2, probe_steps=3, agents_per_role=3)
    assert ps.freedom["recognition"] == 1.0
    _, ps = score_run(solo(), seed=0, steps=2, probe_steps=3, agents_per_role=3)
    assert ps.freedom["recognition"] == 0.0


def test_meaning_and_pleasure_and_being_known():
    inst = tiny()
    m = InstitutionModel(inst, seed=1, agents_per_role=3)
    assert all(a.last_choice_source == "none" for a in m.agents)
    m.step()
    assert all(a.last_choice_source == "bootstrap" for a in m.by_role["worker"])  # first practice: material bootstrap
    ps = probe(m, probe_steps=4)
    assert 0.0 <= ps.flourishing["meaning"] <= 1.0
    assert ps.flourishing["meaning"] == pytest.approx(ps.choice_sources.get("threshold", 0) / 4)
    assert ps.flourishing["being_known"] >= 0.0 and float(ps.flourishing["being_known"]).is_integer()
    assert isinstance(ps.flourishing["pleasure"], float)
    with pytest.raises(ValueError):
        probe(m, probe_steps=0)


def test_summarize_scores_and_disagreement():
    scores = [score_run(solo(), seed=s, steps=2, probe_steps=2, agents_per_role=2)[1] for s in range(2)]
    s = summarize_scores(scores)
    assert s["freedom"]["exit"] == 1.0 and s["freedom"]["voice"] is None and s["probe_roles"] == {"worker": 2}
    assert s["freedom_sum"] == {"value": 1.0, "excluded": ["voice"]}
    mk = lambda i, f, g_: {"institution": i, "freedom_sum": {"value": f, "excluded": []}, "flourishing_sum": {"value": g_, "excluded": []}}
    d = disagreement([mk("A", 1.0, 0.0), mk("B", 0.0, 1.0), mk("C", 2.0, 2.0)])
    assert d == [{"a": "A", "b": "B", "freedom": [1.0, 0.0], "flourishing": [0.0, 1.0]}]
    assert disagreement([mk("A", 1.0, 1.0), mk("B", 1.0, 0.0)]) == []  # a tie is not a reversal


# ---------------------------------------------------------------- gate letters
def test_gate_c_definitions_on_synthetic_traces():
    ones = [1] * 51
    assert g.rises_toward_one(ones) and not g.stays_flat(ones)
    drop = [1] + [0] * 50  # the no-implicit shape: a step-0 vacuous truth, then false
    assert g.stays_flat(drop) and not g.rises_toward_one(drop)
    climb = [0] * 25 + [1] * 26
    assert g.rises_toward_one(climb) and not g.stays_flat(climb)
    zeros = [0] * 51
    assert g.stays_flat(zeros) and not g.rises_toward_one(zeros)
    fall = [1] * 40 + [0] * 11  # ends low: neither "toward 1" nor flat (late - early is negative, but late < high ok)
    assert not g.rises_toward_one(fall) and g.stays_flat(fall)
    assert g.windows([1, 0, 0, 0, 1]) == (1.0, 1.0)


def test_gate_a_and_b_are_blocked_with_reasons_never_skipped():
    by, props = {}, {}
    configs, not_run = g.available_configs()
    assert configs == [("material",)] and "coordination" in not_run and "{}" in not_run
    a = g.crit_a(by, props, 2, configs, not_run)
    b = g.crit_b(by, props, 2, configs, not_run)
    assert a.status == g.BLOCKED and a.blocked_reason == "no footbinding institution in the dataset"
    assert b.status == g.BLOCKED and b.blocked_reason == "no naming-convention institution in the dataset"
    # institution present, module still a stub: the next blocker, stated
    fb = solo(inst_id=g.FOOTBINDING)
    nm = solo(inst_id=g.NAMING)
    a = g.crit_a({fb.id: fb}, props, 2, configs, not_run)
    b = g.crit_b({nm.id: nm}, props, 2, configs, not_run)
    assert a.status == g.BLOCKED and a.blocked_reason == "coordination module not implemented"
    assert b.status == g.BLOCKED and b.blocked_reason == "coordination module not implemented"
    # with a (hypothetical) coordination configuration, (b) is still blocked on the missing parameter
    b = g.crit_b({nm.id: nm}, props, 2, [("material", "coordination")], {})
    assert b.status == g.BLOCKED and g.B_PARAM in b.blocked_reason


def test_gate_verdict_and_exit_codes():
    mk = lambda k, st: g.Criterion(k, st, "x", blocked_reason="why" if st == g.BLOCKED else None)
    rep = g.GateReport([mk("a", g.PASS), mk("b", g.PASS)], 1, [["material"]], {})
    assert rep.verdict == g.PASS and rep.exit_code == 0 and rep.passed
    rep = g.GateReport([mk("a", g.BLOCKED), mk("b", g.PASS)], 1, [["material"]], {})
    assert rep.verdict == g.BLOCKED and rep.exit_code == 2 and not rep.passed
    rep = g.GateReport([mk("a", g.BLOCKED), mk("b", g.FAIL)], 1, [["material"]], {})
    assert rep.verdict == g.FAIL and rep.exit_code == 1
    text = g.format_gate(rep)
    assert "GATE FAIL" in text and "blocked: why" in text and "assumed thresholds" in text
    d = rep.to_dict()
    assert d["verdict"] == "FAIL" and d["assumptions"]["C_HIGH"] == g.C_HIGH and [c["key"] for c in d["criteria"]] == ["a", "b"]


def _regender_pair():
    """A synthetic kibbutz pair: `paid` rises (work is granted) in the original, stays flat (work barred) in the pair."""
    rules = [{"id": "R1", "attribute": "worker", "deontic": "may", "aim": "(work worker)", "conditions": "true", "strand": "rival"}]
    orig = solo(rules=rules, inst_id=g.KIBBUTZ)
    barred = solo(rules=rules + [{"id": "R2", "attribute": "worker", "deontic": "must_not", "aim": "(work worker)",
                                  "conditions": "true", "strand": "rival", "or_else": None}], inst_id=g.KIBBUTZ_PAIR)
    prop = Property(name=g.PROP_C, formal="(paid worker t)")
    return orig, barred, prop


def test_gate_c_on_a_synthetic_pair_through_the_property():
    orig, barred, prop = _regender_pair()
    tr = g.property_trace(orig, prop, 0, 5, 3)
    assert tr == [0, 1, 1, 1, 1, 1]
    assert g.property_trace(barred, prop, 0, 5, 3) == [0] * 6
    c = g.crit_c({orig.id: orig, barred.id: barred}, {prop.name: prop}, 4, [("material",)], steps=10, agents_per_role=3)
    assert c.status == g.PASS, c.detail
    n = c.numbers["by_config"]["material"]
    assert n[g.KIBBUTZ]["rate"] == 1.0 and n[g.KIBBUTZ_PAIR]["rate"] == 1.0
    assert n[g.KIBBUTZ]["mean_trace"][0] == 0.0 and n[g.KIBBUTZ]["mean_trace"][-1] == 1.0
    assert len(n[g.KIBBUTZ]["per_seed"]) == 4
    # swapped: the original stays flat and the pair "rises" -> FAIL with the numbers, not a tuned pass
    orig.id, barred.id = g.KIBBUTZ_PAIR, g.KIBBUTZ
    c = g.crit_c({orig.id: orig, barred.id: barred}, {prop.name: prop}, 4, [("material",)], steps=10, agents_per_role=3)
    assert c.status == g.FAIL and "rises 0%" in c.detail and "flat 0%" in c.detail
    # missing pieces are BLOCKED with a reason
    assert g.crit_c({}, {prop.name: prop}, 2, [("material",)]).status == g.BLOCKED
    assert g.crit_c({orig.id: orig, barred.id: barred}, {}, 2, [("material",)]).blocked_reason == f"no property {g.PROP_C}"


def test_gate_d_numbers_blocked_below_100_seeds_and_errors_listed():
    insts = [solo(inst_id="x"), tiny()]
    d = g.crit_d(insts, 6, [("material",)], steps=3, probe_steps=2, agents_per_role=3)
    assert d.status == g.BLOCKED and "fewer than 100 seeds (6)" == d.blocked_reason
    n = d.numbers["by_config"]["material"]
    assert n["institutions"] == 2 and n["errors"] == {} and set(n["ranking_half_a"]) == {"x", "tiny-shop"}
    assert d.numbers["halves"] == [[0, 2], [3, 5]]
    assert n["rho"] is None or -1.0 <= n["rho"] <= 1.0
    assert "x" in n["nulls"] and "voice" in n["nulls"]["x"]
    # an institution whose run raises is an error, listed, not skipped
    broken = InstitutionJSON.model_validate({"id": "broken", "roles": [], "fluents": [], "actions": [], "rules": []})
    d = g.crit_d(insts + [broken], 2, [("material",)], steps=2, probe_steps=1, agents_per_role=2)
    n = d.numbers["by_config"]["material"]
    assert "broken" in n["errors"] and n["institutions"] == 2
    assert any("error broken" in l for l in d.lines)


def test_gate_d_fails_on_unstable_ranking_with_enough_seeds(monkeypatch):
    """With >= 100 seeds the verdict is read: a stable ranking passes, an error or a low rho fails."""
    calls = {"n": 0}

    def fake_score(inst, seeds, **kw):
        calls["n"] += 1
        vals = [1.0 + (0.5 if inst.id == "x" else 0.0)] * seeds  # x always above
        return {"institution": inst.id, "freedom_sum": {"value": 0.0, "excluded": []}, "flourishing_sum": {"value": 0.0, "excluded": []},
                "freedom": {}, "flourishing": {}, "total": {"value": 0.0, "excluded": []}, "nulls": {},
                "per_seed": [{"total": {"value": v}} for v in vals]}
    monkeypatch.setattr(g, "score", fake_score)
    insts = [solo(inst_id="x"), solo(inst_id="y"), solo(inst_id="z")]
    d = g.crit_d(insts, 100, [("material",)])
    assert calls["n"] == 3 and d.status == g.PASS  # x above a tied y/z in both halves: average ranks, rho 1.0
    assert d.numbers["by_config"]["material"]["rho"] == pytest.approx(1.0)
    # every institution tied: no rank variance, rho undefined -> FAIL, never a silent 1.0
    monkeypatch.setattr(g, "score", lambda inst, seeds, **kw: {**fake_score(inst, seeds), "per_seed": [{"total": {"value": 1.0}}] * seeds})
    d = g.crit_d(insts, 100, [("material",)])
    assert d.status == g.FAIL and d.numbers["by_config"]["material"]["rho"] is None and "undefined" in d.lines[0]
    # make the three distinct and stable
    monkeypatch.setattr(g, "score", lambda inst, seeds, **kw: {
        **fake_score(inst, seeds), "per_seed": [{"total": {"value": {"x": 3.0, "y": 2.0, "z": 1.0}[inst.id]}}] * seeds})
    d = g.crit_d(insts, 100, [("material",)])
    assert d.status == g.PASS and d.numbers["by_config"]["material"]["rho"] == pytest.approx(1.0)
    # reversed between halves -> FAIL
    monkeypatch.setattr(g, "score", lambda inst, seeds, **kw: {
        **fake_score(inst, seeds),
        "per_seed": [{"total": {"value": {"x": 3.0, "y": 2.0, "z": 1.0}[inst.id]}}] * 50
                    + [{"total": {"value": {"x": 1.0, "y": 2.0, "z": 3.0}[inst.id]}}] * 50})
    d = g.crit_d(insts, 100, [("material",)])
    assert d.status == g.FAIL and d.numbers["by_config"]["material"]["rho"] == pytest.approx(-1.0)


def test_run_gate_on_synthetic_dataset_is_blocked_not_failed():
    orig, barred, prop = _regender_pair()
    rep = g.run_gate([orig, barred], {prop.name: prop}, seeds=3, steps=6, probe_steps=2, agents_per_role=3)
    assert [c.key for c in rep.criteria] == ["a", "b", "c", "d"]
    assert [c.status for c in rep.criteria] == [g.BLOCKED, g.BLOCKED, g.PASS, g.BLOCKED]
    assert rep.verdict == g.BLOCKED and rep.exit_code == 2
    assert rep.configs_run == [["material"]] and "{}" in rep.configs_not_run
    text = g.format_gate(rep, verbose=True)
    assert "GATE BLOCKED" in text and "[c]" in text and "configurations not run" in text
    json.dumps(rep.to_dict())  # serialisable


# ---------------------------------------------------------------- dataset-backed (skip without the dataset)
def test_gate_c_and_d_run_on_the_dataset():
    """(c) on the real kibbutz pair under the material module (20 seeds, a short run); (d) computes its numbers over
    every institution the ABM can load and reports BLOCKED below 100 seeds."""
    ip, pp = require_dataset()
    insts = load_institutions(ip)
    props = load_properties(pp)
    by = {i.id: i for i in insts}
    if g.KIBBUTZ not in by or g.KIBBUTZ_PAIR not in by or g.PROP_C not in props:
        pytest.skip("dataset has no kibbutz pair / care_assigned_by_sex")
    c = g.crit_c(by, props, 20, [("material",)], steps=30, agents_per_role=20)
    assert c.status == g.PASS, c.detail + "\n" + "\n".join(c.lines)
    n = c.numbers["by_config"]["material"]
    assert n[g.KIBBUTZ]["late_mean"] >= g.C_HIGH and n[g.KIBBUTZ_PAIR]["late_mean"] < g.C_HIGH
    d = g.crit_d(insts, 4, [("material",)], steps=5, probe_steps=2, agents_per_role=5)
    assert d.status == g.BLOCKED and d.blocked_reason.startswith("fewer than 100 seeds")
    n = d.numbers["by_config"]["material"]
    assert n["institutions"] + len(n["errors"]) == len(insts)
    assert n["errors"] == {}, n["errors"]


def test_cli_abm_score_and_gate(capsys, dataset_env):
    ip, _ = dataset_env
    inst_id = g.KIBBUTZ if any(i.id == g.KIBBUTZ for i in load_institutions(ip)) else load_institutions(ip)[0].id
    assert main(["abm", "score", "--institution", inst_id, "--seeds", "2", "--steps", "3", "--probe-steps", "2",
                 "--agents-per-role", "3", "--institutions", str(ip)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["seeds"] == [0, 1] and d["freedom"]["voice"] is None and len(d["per_seed"]) == 2
    assert "voice" in d["total"]["excluded"]
    rc = main(["abm", "gate", "--seeds", "2", "--steps", "3", "--probe-steps", "2", "--agents-per-role", "3",
               "--institutions", str(ip), "--json"])
    d = json.loads(capsys.readouterr().out)
    assert d["verdict"] in ("BLOCKED", "FAIL") and rc == d["exit_code"] and rc in (1, 2)
    assert [c["key"] for c in d["criteria"]] == ["a", "b", "c", "d"]
    assert d["criteria"][0]["status"] == "BLOCKED" and d["criteria"][3]["blocked_reason"].startswith("fewer than 100")
    assert d["configs_run"] == [["material"]] and "coordination" in d["configs_not_run"]
    rc = main(["abm", "gate", "--seeds", "2", "--steps", "3", "--probe-steps", "2", "--agents-per-role", "3",
               "--institutions", str(ip)])
    out = capsys.readouterr().out
    assert rc in (1, 2) and "GATE" in out and "criterion" in out and "blocked:" in out
    assert main(["abm", "gate", "--seeds", "1", "--institutions", "/nonexistent/institutions.json"]) == 3
