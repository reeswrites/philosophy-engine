"""Transfer graph and the derived `rebundling` check (philengine.rules_ablate, plans/priority.md slice 3)."""
import json

import pytest

from philengine import rules_ablate as ra
from philengine import rules_cache
from philengine import rules_checks as rc
from philengine.schemas_rules import InstitutionJSON, Property

from .test_rules_ablate import keeper

K = 4
# a second, identical bar on exit: either R2 or R4 alone keeps the ward held, so neither carries held_persists in E and
# each carries it once the other is gone (the known answer: two edges of weight 1, both rebundling)
DUP = {"id": "R4", "attribute": "ward", "deontic": "must_not", "aim": "(exit w)", "conditions": "(held w)",
       "or_else": None, "strand": "tying"}
REB = Property(name="rebundling", kind="failure_mode", check="rebundling",
               formal="derived: some rule r1 has a freedom transfer edge to a rule that reads tying in E minus r1")


def edges(g, graph="freedom"):
    return {(e.source, e.target): e.weight for e in g.edges[graph]}


def test_redundant_bars_transfer_to_each_other():
    inst, props = keeper((DUP,))
    g = ra.transfer_graph(inst, props, K)
    assert edges(g) == {("R2", "R4"): 1, ("R4", "R2"): 1}
    assert edges(g, "goods") == {}
    assert g.base["R2"]["freedom_up"] == 0 and g.after["R4"]["R2"]["freedom_up"] == 1
    e = g.edges["freedom"][0]
    assert (e.before, e.after, e.families_added, e.target_reading_before, e.target_reading_after) == (
        0, 1, ["held_persists"], "unread", "tying")
    assert e.rebundling and not e.unranked
    assert g.rebundling == {"R2": ["R4"], "R4": ["R2"]}
    assert g.out_transfer["freedom"] == {"R1": 0, "R2": 1, "R3": 0, "R4": 1}
    assert g.in_transfer["freedom"] == {"R1": 0, "R2": 1, "R3": 0, "R4": 1}
    assert ra.rebundling(inst, "R2", props, K, graph=g) and not ra.rebundling(inst, "R1", props, K, graph=g)
    with pytest.raises(KeyError):
        ra.rebundling(inst, "R9", props, K, graph=g)


def test_single_bar_has_no_edge():
    inst, props = keeper()
    g = ra.transfer_graph(inst, props, K)
    assert edges(g) == {} and g.rebundling == {} and g.base["R2"]["freedom_up"] == 1


def test_weight_is_the_definition():
    """weight(r1 -> r2) = load(r2 | E minus r1) - load(r2 | E), recomputed by hand from two plain ablations."""
    inst, props = keeper((DUP,))
    g = ra.transfer_graph(inst, props, K)
    base = {a.rule_id: a for a in ra.ablate(inst, props, K, variants=("deleted",))}
    for r1 in g.rules:
        inst1, _ = ra.without_rule(inst, r1)
        rows = {a.rule_id: a for a in ra.ablate(inst1, props, K, variants=("deleted",))}
        for r2 in g.rules:
            if r2 != r1:
                assert edges(g).get((r1, r2), 0) == max(0, rows[r2].load_freedom_up - base[r2].load_freedom_up)
                assert g.after[r1][r2]["freedom"] == rows[r2].load_freedom


def test_rule_order_does_not_change_the_graph():
    inst, props = keeper((DUP,))
    d = inst.model_dump()
    d["rules"] = d["rules"][::-1]
    g, g2 = ra.transfer_graph(inst, props, K), ra.transfer_graph(InstitutionJSON.model_validate(d), props, K)
    assert edges(g) == edges(g2) and {s: sorted(t) for s, t in g.rebundling.items()} == {s: sorted(t) for s, t in g2.rebundling.items()}


def test_goods_lost_target_is_not_rebundling():
    """The same edge whose target also loses a good in E minus r1 reads `hard case (primary)`, so it is not rebundling."""
    inst, props = keeper((DUP,))
    props["kept"] = Property(name="kept", kind="goods", polarity="good", check="persists", encoders=["e1", "e2"],
                             contested=[], formal="(=> (held ward t) (held ward t+1))".replace("t+1", "t"),
                             subject="(held ward t)", primary_measure="guaranteed", primary_measure_reason="test fixture")
    g = ra.transfer_graph(inst, props, K)
    assert edges(g) == {("R2", "R4"): 1, ("R4", "R2"): 1}
    for e in g.edges["freedom"]:
        assert e.rebundling == (e.target_reading_after == "tying")


def test_cache_shares_the_doubly_ablated_runs(tmp_path):
    inst, props = keeper((DUP,))
    cold = rules_cache.RuleCache(tmp_path / "c")
    g = ra.transfer_graph(inst, props, K, cache=cold)
    assert cold.hits > 0 and cold.misses > 0
    n = len(inst.rules)
    # institutions asked for: E, n singly ablated, then per source its base again and n-1 doubly ablated ones;
    # distinct: 1 + n + n(n-1)/2. Every run_all asks the cache the same number of times here (all consistent).
    asked, distinct = 1 + n + n + n * (n - 1), 1 + n + n * (n - 1) // 2
    assert cold.rate() == pytest.approx(1 - distinct / asked)
    warm = rules_cache.RuleCache(tmp_path / "c")
    g2 = ra.transfer_graph(inst, props, K, cache=warm)
    assert warm.misses == 0 and g2.to_dict() == g.to_dict() == ra.transfer_graph(inst, props, K).to_dict()


def test_multi_k_and_table():
    inst, props = keeper((DUP,))
    by_k, dis = ra.transfer_multi_k(inst, props, (3, 4))
    assert set(by_k) == {3, 4} and dis == {"freedom": [], "goods": [], "rebundling": []}
    txt = ra.transfer_table(by_k[4])
    assert "R2      R4      +1" in txt and "rebundling(E, r1): R2 -> R4; R4 -> R2" in txt
    json.dumps(by_k[4].to_dict())


def test_derived_check_through_run_all():
    inst, props = keeper((DUP,))
    props["rebundling"] = REB
    inst.expected_properties["rebundling"] = "reachable"
    rep = rc.run_all(inst, props, k=K)
    r = next(x for x in rep.results if x.property == "rebundling")
    assert (r.check, r.verdict) == ("rebundling", "reachable") and "R2 -> R4 (+1: held_persists)" in r.reason
    inst1, props1 = keeper()
    props1["rebundling"] = REB
    rep1 = rc.run_all(inst1, props1, k=K, which={"rebundling": ["reachable"]})
    assert [(x.check, x.verdict, x.z3_unknown) for x in rep1.results] == [("rebundling", "open", False)]


def test_ablation_never_reads_a_derived_property():
    inst, props = keeper((DUP,))
    before = ra.ablate(inst, props, K)
    props["rebundling"] = REB
    inst.expected_properties["rebundling"] = "reachable"
    which, na = ra.applicable_which(inst, props)
    assert "rebundling" not in which and "rebundling" not in na
    after = ra.ablate(inst, props, K)
    assert [a.to_dict() for a in before] == [a.to_dict() for a in after]
    assert ra.transfer_graph(inst, props, K).rebundling == {"R2": ["R4"], "R4": ["R2"]}


def test_derived_check_requires_failure_mode_kind():
    with pytest.raises(ValueError, match="derived check"):
        Property(name="rebundling", kind="structure", check="rebundling", formal="x")


def test_inconsistent_source_has_no_out_edges(monkeypatch):
    inst, props = keeper((DUP,))
    real = ra.ablate

    def fake(i, *a, **kw):
        rows = real(i, *a, **kw)
        if len(i.rules) == 4:
            next(r for r in rows if r.rule_id == "R1").inconsistent_after = True
        return rows
    monkeypatch.setattr(ra, "ablate", fake)
    g = ra.transfer_graph(inst, props, K)
    assert g.inconsistent_sources == ["R1"] and "R1" not in g.after
    assert ("R2", "R1") in g.undefined and edges(g) == {("R2", "R4"): 1, ("R4", "R2"): 1}


def test_cli_transfer(tmp_path, capsys):
    inst, props = keeper((DUP,))
    props["rebundling"] = REB
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([p.model_dump(mode="json", exclude_none=True) for p in props.values()]))
    from philengine.cli import build_parser
    a = build_parser().parse_args(["rules", "transfer", "--entry", "t-keeper", "--k", "3,4", "--no-cache",
                                   "--institutions", str(tmp_path / "i.json"), "--properties", str(tmp_path / "p.json"),
                                   "--json", str(tmp_path / "o.json")])
    assert a.fn(a) == 0
    out = capsys.readouterr().out
    assert "rebundling(E, r1): R2 -> R4; R4 -> R2" in out and "cache: off" in out and "k-disagreement: none" in out
    d = json.loads((tmp_path / "o.json").read_text())
    e = d["entries"]["t-keeper"]
    assert e["ordered_pairs"] == 12 and e["by_k"]["4"]["rebundling"] == {"R2": ["R4"], "R4": ["R2"]}
    a = build_parser().parse_args(["rules", "transfer", "--entry", "nope", "--institutions", str(tmp_path / "i.json"),
                                   "--properties", str(tmp_path / "p.json")])
    assert a.fn(a) == 2
