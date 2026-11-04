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
    # 2026-11-04 (review finding 4): sums carry mean_measured = value / measured components (exit 1.0, recognition 0.0)
    assert s["freedom_sum"] == {"value": 1.0, "excluded": ["voice"], "mean_measured": 0.5}
    assert summarize_scores(scores)["total"]["mean_measured"] == pytest.approx(s["total"]["value"] / 5)
    mk = lambda i, f, g_: {"institution": i, "freedom_sum": {"value": f, "excluded": []}, "flourishing_sum": {"value": g_, "excluded": []}}
    d = disagreement([mk("A", 1.0, 0.0), mk("B", 0.0, 1.0), mk("C", 2.0, 2.0)])
    assert d == [{"a": "A", "b": "B", "freedom": [1.0, 0.0], "flourishing": [0.0, 1.0]}]
    assert disagreement([mk("A", 1.0, 1.0), mk("B", 1.0, 0.0)]) == []  # a tie is not a reversal


# ---------------------------------------------------------------- gate letters
def test_gate_c_definitions_on_synthetic_traces():
    # 2026-11-04 (review finding 2): `stays_flat` renamed `ends_below_high`; it accepts a 1 -> 0 drop by design
    ones = [1] * 51
    assert g.rises_toward_one(ones) and not g.ends_below_high(ones)
    drop = [1] + [0] * 50  # the no-implicit shape: a step-0 vacuous truth, then false
    assert g.ends_below_high(drop) and not g.rises_toward_one(drop)
    climb = [0] * 25 + [1] * 26
    assert g.rises_toward_one(climb) and not g.ends_below_high(climb)
    zeros = [0] * 51
    assert g.ends_below_high(zeros) and not g.rises_toward_one(zeros)
    fall = [1] * 40 + [0] * 11  # ends low: not "toward 1"; ends_below_high (it is a drop, not flatness)
    assert not g.rises_toward_one(fall) and g.ends_below_high(fall)
    assert not hasattr(g, "stays_flat")
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
    """A synthetic kibbutz pair (2026-11-04 redesign, review finding 1): `quit` is the forbidden instance in the
    original (R3 must_not, sanctioned by R1) and lawful in the pair; `work` is the lawful sibling at payoff 1.0."""
    rules = [{"id": "R1", "attribute": "worker", "deontic": "may", "aim": "(work worker)", "conditions": "true", "strand": "rival"},
             {"id": "R2", "attribute": "worker", "deontic": "may", "aim": "(quit worker)", "conditions": "true", "strand": "rival"}]
    orig = solo(rules=rules + [{"id": "R3", "attribute": "worker", "deontic": "must_not", "aim": "(quit worker)",
                                "conditions": "true", "strand": "rival", "or_else": "R1"}], inst_id=g.KIBBUTZ)
    pair = solo(rules=rules, inst_id=g.KIBBUTZ_PAIR)
    prop = Property(name=g.PROP_C, formal="(paid worker t)")
    return orig, pair, prop


C_SMALL = dict(forbidden="quit(worker)", role="worker", sanction_grid=[0.0, 0.25, 1.0], payoff_grid=[1.0, 2.0])


def test_gate_c_two_axis_sweep_on_a_synthetic_pair():
    """Preregistered from the choice rule (net = payoff - sanction_weight * 1.5**k * 3; a forbidden instance is a
    candidate only when its net strictly beats the best lawful net, 1.0): payoff 1.0 never admits quit; payoff 2.0
    admits it at w=0 for good, at w=0.25 for one step (2-0.75 > 1, then 2-1.125 < 1: escalation evicts it), never
    at w=1. The pair adopts quit wherever it out-pays, at every w."""
    orig, pair, prop = _regender_pair()
    r = g.c_run(orig, __import__("philengine.sexpr", fromlist=["parse"]).parse(prop.formal), 0, 5, 3, ("material",),
                {"quit(worker)": 2.0}, {"sanction_weight": 0.0}, "worker", "quit(worker)")
    assert r["share"] == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0] and r["candidate"] is True and len(r["prop"]) == 6
    c = g.crit_c({orig.id: orig, pair.id: pair}, {prop.name: prop}, 4, [("material",)], steps=12, agents_per_role=3, **C_SMALL)
    assert c.status == g.PASS, c.detail + "\n" + "\n".join(c.lines)
    k = c.numbers["by_config"]["material"][g.KIBBUTZ]
    q = c.numbers["by_config"]["material"][g.KIBBUTZ_PAIR]
    assert k["band"] == [0.25, 1.0] and k["adopted_below_band"] == {"2.0": [0.0]} and k["out_paying"] == [2.0]
    assert k["excluded_independent_of_sanction"] is False and k["forbidden_at_step0"] is True and k["ever_candidate"]
    assert k["grid"]["0.0"]["2.0"]["adopted_rate"] == 1.0 and k["grid"]["0.25"]["2.0"]["excluded_rate"] == 1.0
    assert k["grid"]["0.0"]["1.0"]["excluded_rate"] == 1.0  # equal pay: the strict rule never admits it
    assert q["forbidden_at_step0"] is False and q["ok"] and q["not_adopted_at"] == []
    assert all(q["grid"][str(w)]["2.0"]["adopted_rate"] == 1.0 for w in C_SMALL["sanction_grid"])
    assert len(k["grid"]["0.0"]["2.0"]["per_seed"]) == 4 and "property_late_mean" in k["grid"]["0.0"]["2.0"]
    assert any("sanction_weight \\ payoff" in l for l in c.lines) and any("E100%" in l and "A100%" in l for l in c.lines)
    # swapped ids: the "original" is adopted everywhere (no band) -> FAIL named as sanction-independent, not tuned
    orig.id, pair.id = g.KIBBUTZ_PAIR, g.KIBBUTZ
    c = g.crit_c({orig.id: orig, pair.id: pair}, {prop.name: prop}, 4, [("material",)], steps=12, agents_per_role=3, **C_SMALL)
    assert c.status == g.FAIL and "band NONE" in c.detail
    assert c.numbers["by_config"]["material"][g.KIBBUTZ]["excluded_independent_of_sanction"] is True
    assert any("independent of sanction_weight: YES (vacuous)" in l for l in c.lines)
    # missing pieces are BLOCKED with a reason
    assert g.crit_c({}, {prop.name: prop}, 2, [("material",)]).status == g.BLOCKED
    assert g.crit_c({orig.id: orig, pair.id: pair}, {}, 2, [("material",)]).blocked_reason == f"no property {g.PROP_C}"


def test_gate_c_vacuity_guard_is_blocked_not_pass(monkeypatch):
    orig, pair, prop = _regender_pair()
    by, props = {orig.id: orig, pair.id: pair}, {prop.name: prop}
    # the default C_FORBIDDEN is not an instance of the synthetic pair
    c = g.crit_c(by, props, 2, [("material",)], steps=3, agents_per_role=2)
    assert c.status == g.BLOCKED and "not an action instance" in c.blocked_reason
    assert g.crit_c(by, props, 2, [("material",)], steps=3, agents_per_role=2, forbidden="quit").status == g.BLOCKED
    # a disability (or_else null) removes the power: never available -> BLOCKED, not a vacuous PASS
    orig.rules[-1].or_else = None
    c = g.crit_c(by, props, 2, [("material",)], steps=3, agents_per_role=2, **C_SMALL)
    assert c.status == g.BLOCKED and "never available" in c.blocked_reason
    # never a candidate at any grid point (no payoff key reaches it): BLOCKED with the reason
    orig, pair, prop = _regender_pair()
    real = g.c_run
    monkeypatch.setattr(g, "c_run", lambda *a, **k: {**real(*a, **k), "candidate": False})
    c = g.crit_c({orig.id: orig, pair.id: pair}, props, 2, [("material",)], steps=3, agents_per_role=2, **C_SMALL)
    assert c.status == g.BLOCKED and "never a candidate" in c.blocked_reason and "vacuous" in c.blocked_reason


def _fake_c_run(orig_share, pair_share):
    """c_run stand-in: share trace 0/1 from (sanction_weight, payoff) per entry; candidate True."""
    def run(inst, ast, seed, steps, apr, modules, payoffs, params, role, label):
        w, p = params["sanction_weight"], payoffs[label]
        v = (orig_share if inst.id == g.KIBBUTZ else pair_share)(w, p)
        return {"share": [0.0] + [float(v)] * steps, "prop": [1 - int(v)] * (steps + 1), "candidate": True}
    return run


def test_gate_c_criterion_on_a_synthetic_grid(monkeypatch):
    orig, pair, prop = _regender_pair()
    by, props = {orig.id: orig, pair.id: pair}, {prop.name: prop}
    kw = dict(forbidden="quit(worker)", role="worker", sanction_grid=[0.0, 0.5, 1.0, 2.0], payoff_grid=[1.0, 1.5, 3.0])
    run = lambda: g.crit_c(by, props, 5, [("material",)], steps=4, agents_per_role=2, **kw)
    # the sanction governs: adopted below w=1 wherever it out-pays, excluded from w=1 up; the pair adopts everywhere
    monkeypatch.setattr(g, "c_run", _fake_c_run(lambda w, p: p > 1 and w < 1, lambda w, p: p > 1))
    c = run()
    k = c.numbers["by_config"]["material"][g.KIBBUTZ]
    assert c.status == g.PASS and k["band"] == [1.0, 2.0] and k["adopted_below_band"] == {"1.5": [0.0, 0.5], "3.0": [0.0, 0.5]}
    # excluded at every grid point: independent of sanction_weight -> FAIL, named vacuous
    monkeypatch.setattr(g, "c_run", _fake_c_run(lambda w, p: False, lambda w, p: p > 1))
    c = run()
    assert c.status == g.FAIL and c.numbers["by_config"]["material"][g.KIBBUTZ]["excluded_independent_of_sanction"]
    # adopted at every out-paying point whatever w: no band -> FAIL
    monkeypatch.setattr(g, "c_run", _fake_c_run(lambda w, p: p > 1, lambda w, p: p > 1))
    assert run().status == g.FAIL
    # a band but no collapse below it for one out-paying payoff -> FAIL
    monkeypatch.setattr(g, "c_run", _fake_c_run(lambda w, p: p > 2 and w < 1, lambda w, p: p > 1))
    c = run()
    assert c.status == g.FAIL and c.numbers["by_config"]["material"][g.KIBBUTZ]["adopted_below_band"]["1.5"] == []
    # the pair refuses it at one sanction weight -> FAIL with the point named
    monkeypatch.setattr(g, "c_run", _fake_c_run(lambda w, p: p > 1 and w < 1, lambda w, p: p > 1 and w < 2))
    c = run()
    assert c.status == g.FAIL and c.numbers["by_config"]["material"][g.KIBBUTZ_PAIR]["not_adopted_at"] == [(2.0, 1.5), (2.0, 3.0)]
    # the old property reading survives as an extra line at the default point, never as the criterion
    assert any(l.startswith("  extra (not a criterion)") for l in c.lines)
    # budget cap (C_SEEDS_MAX, 2026-11-04): (c) runs min(seeds, C_SEEDS_MAX) per grid point and says so
    monkeypatch.setattr(g, "C_SEEDS_MAX", 3)
    c = run()
    assert c.numbers["seeds"] == 3 and c.numbers["seeds_asked"] == 5 and any("budget: (c) ran 3 of the 5 seeds" in l for l in c.lines)


def test_gate_a_persistence_arm_and_vacuous_seeds(monkeypatch):
    """2026-11-04 (review finding 6a): persistence = collapse rate <= 1 - SEED_RATE_MIN over the seeds where the
    practice held at step 0; a trace starting at 0 is vacuous, excluded and counted."""
    fb = solo(inst_id=g.FOOTBINDING)  # no `*_pledge` action: persistence is expected under every configuration
    prop = Property(name=g.A_PROP, formal="(paid worker t)")
    cfg = [("material", "coordination")]  # hypothetical: the body is reached by faking the traces

    def traces(per_seed):
        monkeypatch.setattr(g, "property_trace", lambda inst, p, seed, steps, apr, cfg_, pay=None, params=None: per_seed[seed])
    # 79% collapse is not persistence
    traces([[1, 0]] * 79 + [[1, 1]] * 21)
    a = g.crit_a({fb.id: fb}, {prop.name: prop}, 100, cfg, {})
    assert a.status == g.FAIL and a.numbers["collapse_rate"]["material+coordination"] == pytest.approx(0.79)
    traces([[1, 0]] * 20 + [[1, 1]] * 80)
    assert g.crit_a({fb.id: fb}, {prop.name: prop}, 100, cfg, {}).status == g.PASS
    traces([[1, 0]] * 21 + [[1, 1]] * 79)
    assert g.crit_a({fb.id: fb}, {prop.name: prop}, 100, cfg, {}).status == g.FAIL
    # vacuous seeds are excluded from the rate and counted
    traces([[0, 0]] * 50 + [[1, 1]] * 45 + [[1, 0]] * 5)
    a = g.crit_a({fb.id: fb}, {prop.name: prop}, 100, cfg, {})
    assert a.status == g.PASS and a.numbers["vacuous_seeds"]["material+coordination"] == 50
    assert a.numbers["collapse_rate"]["material+coordination"] == pytest.approx(0.1) and "50 vacuous" in a.lines[0]
    traces([[0, 0]] * 10)
    a = g.crit_a({fb.id: fb}, {prop.name: prop}, 10, cfg, {})
    assert a.status == g.FAIL and a.numbers["collapse_rate"]["material+coordination"] is None and "undefined" in a.lines[0]


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
    # 2026-11-04 (review finding 3b): ties are shown as average ranks and marked; the caveat is on the (d) line
    n = d.numbers["by_config"]["material"]
    assert n["avg_rank_half_a"] == {"x": 1.0, "y": 2.5, "z": 2.5} and n["ranking_half_a"][0] == "x"
    assert any("y: " in l and "avg rank 2.5 tie" in l for l in d.lines) and any("x: " in l and "avg rank 1)" in l for l in d.lines)
    assert any("necessary, not sufficient" in l and "static per role" in l for l in d.lines)
    assert "mean_measured_total" in n and any("mean over measured components" in l for l in d.lines)
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
    # (c) is BLOCKED here: the dataset's forbidden instance is not an instance of the synthetic pair (vacuity guard)
    assert [c.status for c in rep.criteria] == [g.BLOCKED, g.BLOCKED, g.BLOCKED, g.BLOCKED]
    assert "not an action instance" in rep.criteria[2].blocked_reason
    assert rep.verdict == g.BLOCKED and rep.exit_code == 2
    assert rep.configs_run == [["material"]] and "{}" in rep.configs_not_run
    text = g.format_gate(rep, verbose=True)
    assert "GATE BLOCKED" in text and "[d]" in text and "configurations not run" in text
    # 2026-11-04 (review finding 7): a BLOCKED letter's computed detail is in the text without --verbose
    plain = g.format_gate(rep)
    assert "[d]" in plain and "computed: Spearman" in plain and "avg rank" not in plain and "avg rank" in text
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
    # 2026-11-04 redesign (review finding 1): a small two-axis grid of the dataset sweep (the full grid runs in
    # `phil abm gate`); preregistered: band [1.0], payoff 2.0 adopted at sanction_weight 0 only, the pair everywhere
    c = g.crit_c(by, props, 5, [("material",)], steps=20, agents_per_role=10, sanction_grid=[0.0, 1.0], payoff_grid=[1.0, 2.0])
    assert c.status == g.PASS, c.detail + "\n" + "\n".join(c.lines)
    n = c.numbers["by_config"]["material"]
    assert n[g.KIBBUTZ]["band"] == [1.0] and n[g.KIBBUTZ]["adopted_below_band"] == {"2.0": [0.0]}
    assert n[g.KIBBUTZ]["forbidden_at_step0"] and not n[g.KIBBUTZ_PAIR]["forbidden_at_step0"]
    assert n[g.KIBBUTZ]["grid"]["0.0"]["2.0"]["property_late_mean"] == 0.0  # the property breaks when adopted
    assert n[g.KIBBUTZ]["grid"]["1.0"]["1.0"]["property_rises_rate"] == 1.0  # the old reading, as information
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
    # 2026-11-04 (review finding 7): score errors exit 3 like gate
    assert main(["abm", "score", "--institution", "no-such", "--seeds", "1", "--institutions", str(ip)]) == 3
    assert main(["abm", "score", "--institution", inst_id, "--seeds", "0", "--institutions", str(ip)]) == 3
    capsys.readouterr()


# ---------------------------------------------------------------- per-instance payoffs (A1 extension, 2026-11-04)
def test_instance_payoff_key_overrides_action_key_and_sweeps():
    from philengine.abm.sweep import sweep
    inst = solo()
    m = InstitutionModel(inst, seed=0, agents_per_role=2, payoffs={"quit": 2.0, "quit(worker)": 5.0})
    assert m.payoff(("quit", ("worker",))) == 5.0  # instance key wins
    assert m.payoff(("work", ("worker",))) == 1.0  # default
    assert InstitutionModel(inst, seed=0, agents_per_role=2, payoffs={"quit": 2.0}).payoff(("quit", ("worker",))) == 2.0
    assert m.income_fluents == {}  # an instance key is never read as an income fluent
    m2 = InstitutionModel(inst, seed=0, agents_per_role=2, payoffs={"quit(worker)": 5.0, "paid": 3.0})
    assert m2.income_fluents == {"paid": 3.0}
    out = sweep(inst, {"payoff.quit(worker)": [0.5, 5.0]}, seeds=2, steps=3, agents_per_role=3)
    assert [g_["params"] for g_ in out["grid"]] == [{"payoff.quit(worker)": 0.5}, {"payoff.quit(worker)": 5.0}]
    low, high = out["grid"]
    assert low["rates"]["adoption_over_seeds"]["worker"].get("quit(worker)", 0.0) < \
        high["rates"]["adoption_over_seeds"]["worker"]["quit(worker)"] == 1.0
    with pytest.raises(ValueError, match="instances"):
        sweep(inst, {"payoff.quit(boss)": [1.0]}, seeds=1, steps=1, agents_per_role=2)
