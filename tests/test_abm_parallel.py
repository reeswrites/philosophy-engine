"""Performance work must not move a result: (1) same-seed reports of the in-test institutions are pinned by hash
per module configuration (the hashes were computed on commit 20f60d7, BEFORE the per-(role, step) memoisation of
`breaches()` in agent.py / model.py; they must never be updated to match a changed result); (2) the process pool
over seeds (abm/parallel.py) returns exactly what the serial loop returns, for every seed loop that uses it
(`run_abm_many`, `sweep`, `necessary_modules`, `score`, the gate letters) and for the CLI `--workers` flag."""
import hashlib
import json

import pytest

from philengine.abm import gate as g
from philengine.abm import parallel
from philengine.abm.model import run_abm, run_abm_many
from philengine.abm.score import score
from philengine.abm.sweep import necessary_modules, sweep
from philengine.cli import main

from .test_abm import shop_with_rest, tiny
from .test_abm_coordination import PAY, convention, pledge_entry
from .test_abm_score_gate import _regender_pair

CONFIGS = [("material",), ("coordination",), ("material", "coordination")]


def _toys():
    inst, pay = shop_with_rest()
    return {"tiny": (tiny(), None), "shop": (inst, pay), "convention": (convention(), PAY),
            "pledge": (pledge_entry(), {"stop": 2.0, "coordinated": ["stop"]})}


def _report(name, mods):
    inst, pay = _toys()[name]
    params = {"committed_minority": 0.25} if name == "convention" and "coordination" in mods else None
    return run_abm(inst, seed=3, steps=20, agents_per_role=8, modules=mods, payoffs=pay, params=params)


# sha256[:16] of AbmReport.to_json() on commit 20f60d7 (before any performance change)
PINNED = {
    ("tiny", "material"): "ffcb75abe13351e3", ("tiny", "coordination"): "277fcda73c5a1a6b",
    ("tiny", "material+coordination"): "3c3323f18b20bdae",
    ("shop", "material"): "2b11385790d1a6f9", ("shop", "coordination"): "2af4ead989fef79a",
    ("shop", "material+coordination"): "635fbce4f6323bd0",
    ("convention", "material"): "b788f7ac4e607fa4", ("convention", "coordination"): "afbe268e1748daeb",
    ("convention", "material+coordination"): "3512b3d89baed616",
    ("pledge", "material"): "e77974db9d52b5c1", ("pledge", "coordination"): "ba10c91be2be799d",
    ("pledge", "material+coordination"): "5d4565559d804dd7",
}


@pytest.mark.parametrize("name,mods", [(n, m) for n in ("tiny", "shop", "convention", "pledge") for m in CONFIGS])
def test_same_seed_report_hash_is_pinned(name, mods):
    h = hashlib.sha256(_report(name, mods).to_json().encode()).hexdigest()[:16]
    assert h == PINNED[(name, "+".join(mods))], f"{name} under {mods}: the report changed (hash {h})"


# ---------------------------------------------------------------- the pool returns what the serial loop returns
def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k != "timing"}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


def test_workers_one_is_serial_and_timing_is_recorded():
    assert parallel.resolve_workers(1) == 1 and parallel.resolve_workers(None) == 1
    assert parallel.run_map(lambda a, b: a + b, [(1, 2), (3, 4)], workers=1) == [3, 7]
    tm = parallel.timing(2.0, 10, 1)
    assert tm["runs_per_second"] == 5.0 and tm["workers"] == 1 and tm["runs"] == 10
    out = sweep(tiny(), {"copy_rate": [0.0, 1.0]}, seeds=2, steps=3, agents_per_role=3, workers=1)
    assert out["timing"]["runs"] == 4 and set(out["timing"]["per_point"]) == {"copy_rate=0.0", "copy_rate=1.0"}


needs_fork = pytest.mark.skipif(not parallel.fork_available(), reason="no fork start method, or a multi-threaded "
                                "process (a pytest-xdist worker): the pool is never used here; the serial run covers it")


@needs_fork
def test_pool_matches_serial_for_every_seed_loop():
    inst, pay = shop_with_rest()
    serial = [r.to_json() for r in run_abm_many(inst, range(5), 1, steps=6, agents_per_role=4, payoffs=pay)]
    assert [r.to_json() for r in run_abm_many(inst, range(5), 3, steps=6, agents_per_role=4, payoffs=pay)] == serial
    assert serial == [run_abm(inst, seed=s, steps=6, agents_per_role=4, payoffs=pay).to_json() for s in range(5)]
    axes = {"sanction_weight": [0.0, 100.0], "payoff.rest": [10.0]}
    a = sweep(inst, axes, seeds=4, steps=4, agents_per_role=3, payoffs=pay, workers=1)
    b = sweep(inst, axes, seeds=4, steps=4, agents_per_role=3, payoffs=pay, workers=3)
    assert _strip(a) == _strip(b) and a["timing"]["workers"] == 1 and b["timing"]["workers"] == 3
    # a lambda predicate travels to the fresh forked pool by inheritance
    nm = [necessary_modules(convention(), lambda m: g.name_share(m.adoption[-1], "speaker", "new_name") >= 0.5,
                            seeds=4, steps=8, agents_per_role=8, payoffs=PAY, params={"committed_minority": 0.5},
                            workers=w) for w in (1, 2)]
    assert _strip(nm[0]) == _strip(nm[1]) and "necessary_modules.predicate" not in parallel._INHERITED
    sc = [score(inst, 5, steps=5, probe_steps=3, agents_per_role=4, payoffs=pay, workers=w) for w in (1, 4)]
    assert _strip(sc[0]) == _strip(sc[1])
    # the whole gate on the synthetic pair, inside one command-level pool
    orig, barred, prop = _regender_pair()
    with parallel.pool(3) as n:
        assert n == 3 and parallel.resolve_workers(None) == 3
        pooled = g.run_gate([orig, barred], {prop.name: prop}, seeds=4, steps=5, probe_steps=2, agents_per_role=3,
                            workers=3).to_dict()
    plain = g.run_gate([orig, barred], {prop.name: prop}, seeds=4, steps=5, probe_steps=2, agents_per_role=3).to_dict()
    assert _strip(pooled) == _strip(plain)
    assert set(pooled["timing"]["per_letter"]) == {"a", "b", "c", "d"} and pooled["timing"]["workers"] == 3
    assert all(c["timing"]["workers"] == 3 for c in pooled["criteria"] if c["timing"])
    assert "per_institution" in pooled["criteria"][3]["timing"]


@needs_fork
def test_cli_workers_flag_gives_identical_output(tmp_path, capsys):
    raw = json.loads(json.dumps(convention().model_dump(mode="json")))
    raw["payoffs"] = dict(PAY)
    ip = tmp_path / "institutions.json"
    ip.write_text(json.dumps([raw]))
    (tmp_path / "properties.json").write_text("[]")
    outs = []
    for w in ("1", "3"):
        assert main(["abm", "run", "--institution", "toy-convention", "--seeds", "4", "--steps", "3", "--agents-per-role", "4",
                     "--modules", "coordination", "--institutions", str(ip), "--workers", w]) == 0
        outs.append(json.loads(capsys.readouterr().out))
    assert _strip(outs[0]) == _strip(outs[1]) and outs[1]["timing"]["workers"] == 3 and outs[0]["timing"]["workers"] == 1
    for w in ("1", "2"):
        rc = main(["abm", "gate", "--seeds", "2", "--steps", "3", "--probe-steps", "2", "--agents-per-role", "3",
                   "--institutions", str(ip), "--properties", str(tmp_path / "properties.json"), "--json", "--workers", w])
        assert rc in (1, 2)
        outs.append(json.loads(capsys.readouterr().out))
    assert _strip(outs[2]) == _strip(outs[3])
    rc = main(["abm", "gate", "--seeds", "2", "--steps", "3", "--probe-steps", "2", "--agents-per-role", "3",
               "--institutions", str(ip), "--properties", str(tmp_path / "properties.json"), "--workers", "2"])
    text = capsys.readouterr().out
    assert "timing (wall clock):" in text and "  total: " in text and "  d: " in text
