"""The engine's own fixture, data/example/: four institutions cut from the research dataset (which lives in the private
computational-liberation repo). It is what default_paths() resolves to without PHIL_DATA_DIR or path flags, so it is
what CI's `phil rules check-all` and the informational `phil rules gate` run on. Claims about the full dataset are the
dataset-dependent tests elsewhere (helpers.require_dataset); these only pin the fixture and the fallback."""
import subprocess
import sys
from pathlib import Path

from philengine import rules_checks as rc
from philengine import rules_gate as rg
from philengine.cli import main
from philengine.schemas_rules import EXAMPLE_DIR, default_paths, load_institutions, load_properties

IDS = ["coverture-household", "companion-ownership", "companion-guardianship", "companion-guardian-renamed"]


def test_default_paths_fall_back_to_the_fixture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no ./data/institutions here
    ip, pp = default_paths()
    assert (ip, pp) == (EXAMPLE_DIR / "institutions.json", EXAMPLE_DIR / "properties.json")
    assert ip.is_file() and pp.is_file()
    monkeypatch.setenv("PHIL_DATA_DIR", "/nonexistent/private-instance")
    ip, pp = default_paths()  # the override is honored even when the target is missing: load_* then fails loudly
    assert ip == Path("/nonexistent/private-instance/institutions/institutions.json")
    assert pp == Path("/nonexistent/private-instance/institutions/properties.json")


def test_fixture_loads_and_is_self_contained():
    insts = load_institutions(EXAMPLE_DIR / "institutions.json")
    props = load_properties(EXAMPLE_DIR / "properties.json")
    assert [i.id for i in insts] == IDS
    for i in insts:
        assert set(i.expected_properties) <= set(props), i.id
        refs = set(i.iso_targets()) | set(i.not_isomorphic_to) | set(i.not_isomorphic_to_control or [])
        if i.minimal_pair() is not None:
            refs.add(i.minimal_pair().id)
        assert refs <= set(IDS), (i.id, refs - set(IDS))  # every cross-reference resolves inside the fixture
    assert sum(p.stat().st_size for p in EXAMPLE_DIR.iterdir()) < 100_000  # it stays a fixture


def test_check_all_agrees_on_the_fixture(capsys):
    assert main(["rules", "check-all"]) == 0
    out = capsys.readouterr().out
    assert "agreement: 22/22 = 100%" in out


def test_gate_runs_end_to_end_on_the_fixture():
    out = subprocess.run([sys.executable, "-m", "philengine.cli", "rules", "gate"], capture_output=True, text=True)
    assert out.returncode in (0, 1), out.stderr
    assert "criterion" in out.stdout and "GATE" in out.stdout
    insts = load_institutions(EXAMPLE_DIR / "institutions.json")
    by = {i.id: i for i in insts}
    assert rg.crit_f(by, insts).status == "PASS"  # the cosmetic-reform pair is in the fixture
    assert rg.crit_d(by).status == "deferred"  # kibbutz is not
