import json

import pytest

from philengine import cli_rules, rules_cache as rcache, rules_checks as rc
from philengine.rules_cache import RuleCache, make_key
from philengine.schemas_rules import Property

from .test_rules_lower import tiny

PROPS = {
    "worker_paid": Property(name="worker_paid", formal="(exists ((w agent)) (paid w t))"),
    "paid_if_employed": Property(name="paid_if_employed", formal="(forall ((w agent)) (=> (employed w t) (paid w t)))"),
}
WHICH = {"worker_paid": ["reachable"], "paid_if_employed": ["invariant", "persists"]}


def tiny2():
    """A second tiny institution: no boss payment duty, an extra may-rule."""
    return tiny(id="tiny2", rules=[
        {"id": "R1", "attribute": "worker", "deontic": "must_not", "aim": "(quit w)", "conditions": "(employed w)",
         "or_else": None, "strand": "rival"},
        {"id": "R2", "attribute": "boss", "deontic": "may", "aim": "(pay b w)", "conditions": "true",
         "or_else": None, "strand": "tying"}])


def strip(rep):
    d = rep.model_dump(mode="json")
    d.pop("timing")
    d.pop("z3_ms")
    for r in d["results"]:
        r.pop("z3_ms")
    return d


def run(inst, cache, **kw):
    kw.setdefault("k", 3)
    return rc.run_all(inst, PROPS, which=WHICH, cache=cache, **kw)


def test_miss_then_hit_reproduces_everything(tmp_path):
    c = RuleCache(tmp_path)
    r1 = run(tiny(), c)
    assert c.hits == 0 and c.misses > 0
    assert any(t.phase == "check" and not t.cached for t in r1.timing)
    c2 = RuleCache(tmp_path)
    r2 = run(tiny(), c2)
    assert c2.misses == 0 and c2.hits == 1 + 3  # one institution entry + one per property check
    assert strip(r1) == strip(r2)
    assert [r.z3_ms for r in r1.results] == [r.z3_ms for r in r2.results]  # stored result, verbatim
    assert all(t.cached for t in r2.timing) and not any(t.phase == "check" for t in r2.timing)
    assert any(r.trace for r in r2.results)  # traces survive
    assert any(r.vacuous is not None and r.antecedent_reachable is not None for r in r2.results)  # flags survive
    assert len(list(tmp_path.glob("*.json"))) == 4


def test_stale_or_corrupt_entry_is_a_miss(tmp_path):
    c = RuleCache(tmp_path)
    run(tiny(), c)
    for f in tmp_path.glob("*.json"):
        f.write_text("{not json")
    c2 = RuleCache(tmp_path)
    r = run(tiny(), c2)
    assert c2.hits == 0 and r.consistent == "sat"


@pytest.mark.parametrize("change", ["k", "step_mode", "init", "compliance", "z3_version", "code", "schema", "institution",
                                     "formal", "check", "entry", "timeout"])
def test_every_key_component_invalidates(change):
    base = dict(inst=tiny(), entry="property", formal="(paid w t)", check="reachable", k=3, step_mode="one",
                init="empty", compliance="strict", z3_version="4.15.4", code="abc", schema=1, timeout_ms=5000)
    other = dict(base)
    if change == "institution":
        other["inst"] = tiny(id="tiny-other")
    elif change == "formal":
        other["formal"] = "(employed w t)"
    elif change == "check":
        other["check"] = "invariant"
    elif change == "entry":
        other["entry"] = "institution"
    elif change == "k":
        other["k"] = 4
    elif change == "step_mode":
        other["step_mode"] = "many"
    elif change == "init":
        other["init"] = "free"
    elif change == "compliance":
        other["compliance"] = "sanctioned"
    elif change == "z3_version":
        other["z3_version"] = "9.9.9"
    elif change == "code":
        other["code"] = "abd"
    elif change == "schema":
        other["schema"] = 2
    elif change == "timeout":
        other["timeout_ms"] = 6000
    assert make_key(**base) == make_key(**dict(base))  # deterministic
    assert make_key(**base) != make_key(**other)


def test_key_is_canonical_over_institution_field_order():
    a = tiny()
    b = type(a).model_validate(json.loads(json.dumps(a.model_dump(mode="json"), sort_keys=True)))
    kw = dict(entry="property", formal="x", check="reachable", k=3, step_mode="one", init="empty", compliance="strict")
    assert make_key(a, **kw) == make_key(b, **kw)


def test_code_hash_covers_lowering_sources(monkeypatch, tmp_path):
    assert {"rules_lower.py", "rules_reference.py"} <= set(rcache.CODE_FILES)
    h = rcache.code_hash()
    fake = tmp_path / "philengine"
    fake.mkdir()
    for n in rcache.CODE_FILES:
        (fake / n).write_text("x")
    monkeypatch.setattr(rcache, "__file__", str(fake / "rules_cache.py"))
    rcache.code_hash.cache_clear()
    try:
        h1 = rcache.code_hash()
        (fake / "rules_lower.py").write_text("y")
        rcache.code_hash.cache_clear()
        assert rcache.code_hash() != h1 != h
    finally:
        monkeypatch.undo()
        rcache.code_hash.cache_clear()


def test_changed_lowering_misses(tmp_path, monkeypatch):
    c = RuleCache(tmp_path)
    run(tiny(), c)
    monkeypatch.setattr(rcache, "code_hash", lambda: "different-lowering")
    c2 = RuleCache(tmp_path)
    run(tiny(), c2)
    assert c2.hits == 0 and c2.misses > 0


@pytest.mark.parametrize("over", [{"k": 4}, {"step_mode": "many"}, {"init": "free"}, {"compliance": "sanctioned"}])
def test_changed_run_options_miss(tmp_path, over):
    run(tiny(), RuleCache(tmp_path))
    c2 = RuleCache(tmp_path)
    run(tiny(), c2, **over)
    assert c2.hits == 0


def test_changed_property_text_or_institution_misses(tmp_path):
    run(tiny(), RuleCache(tmp_path))
    c = RuleCache(tmp_path)
    rc.run_all(tiny(), {**PROPS, "worker_paid": Property(name="worker_paid", formal="(exists ((w agent)) (employed w t))")},
               k=3, which=WHICH, cache=c)
    assert c.hits == 1 + 2  # institution + the two untouched property checks
    c = RuleCache(tmp_path)
    run(tiny2(), c)
    assert c.hits == 0


def test_default_run_all_has_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIL_RUNS_DIR", str(tmp_path))
    rep = rc.run_all(tiny(), PROPS, k=3, which=WHICH)
    assert rep.consistent == "sat" and not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("make", [tiny, tiny2])
def test_cached_verdict_equals_fresh(tmp_path, make):
    fresh = run(make(), None)
    c = RuleCache(tmp_path)
    stored = run(make(), c)
    hit = run(make(), RuleCache(tmp_path))
    assert strip(hit) == strip(stored)  # a hit is the stored run, byte for byte (traces included)

    # z3 may pick a different (equally valid) model on a re-solve depending on process-global state, so a fresh
    # run is compared on everything except which witness trace it found
    def verdicts(rep):
        d = strip(rep)
        for r in d["results"]:
            r["trace"] = None if r["trace"] is None else len(r["trace"])
        return d
    assert verdicts(hit) == verdicts(fresh)
    assert hit.timing and all(t.cached for t in hit.timing)


def test_unknown_results_are_not_stored(tmp_path, monkeypatch):
    real = rc._check

    def unknown(exprs, **kw):
        res = real(exprs, **kw)
        rc._LOG[-1]["result"] = "unknown"
        return res
    monkeypatch.setattr(rc, "_check", unknown)
    # the checks call the module-level name, so the patch takes effect
    run(tiny(), RuleCache(tmp_path))
    assert not list(tmp_path.glob("*.json"))


def test_timing_records_every_query():
    rep = run(tiny(), None)
    phases = {t.phase for t in rep.timing}
    assert {"ground", "consistent", "check", "vacuity"} <= phases
    q = [t for t in rep.timing if t.phase == "check"]
    assert len(q) == 3 and all(t.solve_ms >= 0 and t.build_ms >= 0 and t.result in ("sat", "unsat") for t in q)
    assert all(t.k == 3 and t.step_mode == "one" and t.init == rep.init and t.z3_version == rep.z3_version for t in rep.timing)


def test_stats_and_clear(tmp_path):
    c = RuleCache(tmp_path)
    run(tiny(), c)
    st = c.stats()
    assert st["entries"] == 4 and st["by_kind"] == {"institution": 1, "property": 3} and st["bytes"] > 0
    assert c.clear() == 4 and c.stats()["entries"] == 0


def _write_dataset(tmp_path):
    d = tmp_path / "data" / "institutions"
    d.mkdir(parents=True)
    inst = tiny().model_dump(mode="json")
    inst["expected_properties"] = {"worker_paid": "reachable"}
    (d / "institutions.json").write_text(json.dumps([inst]))
    (d / "properties.json").write_text(json.dumps([p.model_dump(mode="json") for p in PROPS.values()]))
    return d


def test_cli_no_cache_bypass_and_cache_subcommand(tmp_path, monkeypatch, capsys):
    d = _write_dataset(tmp_path)
    monkeypatch.setenv("PHIL_RUNS_DIR", str(tmp_path / "runs"))
    base = ["check-all", "--institutions", str(d / "institutions.json"), "--properties", str(d / "properties.json"), "--k", "3"]
    P = cli_rules.build_parser().parse_args
    parse = lambda argv: P(["rules", *argv])

    a = parse([*base, "--no-cache", "--timing"])
    assert cli_rules.cmd_check_all(a) == 0
    assert "cache: off" in capsys.readouterr().out
    assert not list((tmp_path / "runs").rglob("*.json"))

    assert cli_rules.cmd_check_all(parse([*base, "--timing"])) == 0
    out = capsys.readouterr().out
    assert "0 hit(s)" in out and "slowest 5 checks" in out
    assert list((tmp_path / "runs" / "rules-cache").glob("*.json"))

    assert cli_rules.cmd_check_all(parse([*base, "--timing"])) == 0
    assert "0 miss(es), hit rate 100%" in capsys.readouterr().out

    assert cli_rules.cmd_check_all(parse([*base, "--timing", "--no-cache"])) == 0
    assert "cache: off" in capsys.readouterr().out

    assert cli_rules.cmd_cache(parse(["cache", "stats"])) == 0
    assert "2 entries" in capsys.readouterr().out
    assert cli_rules.cmd_cache(parse(["cache", "clear"])) == 0
    assert not list((tmp_path / "runs" / "rules-cache").glob("*.json"))
