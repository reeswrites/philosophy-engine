from philengine import config
from philengine.cli import main


def test_env_vars_win(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIL_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("PHIL_RUNS_DIR", str(tmp_path / "r"))
    assert config.data_dir() == tmp_path / "d"
    assert config.runs_dir() == tmp_path / "r"


def test_cwd_dirs_used_when_present(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIL_DATA_DIR", raising=False)
    monkeypatch.delenv("PHIL_RUNS_DIR", raising=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "runs").mkdir()
    monkeypatch.chdir(tmp_path)
    assert config.data_dir() == tmp_path / "data"
    assert config.runs_dir() == tmp_path / "runs"


def test_falls_back_to_engine(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIL_DATA_DIR", raising=False)
    monkeypatch.delenv("PHIL_RUNS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.data_dir() == config.ROOT / "data"
    assert config.runs_dir() == config.ROOT / "runs"


def test_cwd_env_file_read_first_and_real_env_wins(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PHIL_TEST_A=cwd\nPHIL_TEST_B=cwd\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PHIL_TEST_B", "real")
    monkeypatch.delenv("PHIL_TEST_A", raising=False)
    config.load_env()
    import os
    assert os.environ["PHIL_TEST_A"] == "cwd"
    assert os.environ["PHIL_TEST_B"] == "real"
    monkeypatch.delenv("PHIL_TEST_A", raising=False)


def test_default_family_resolution_single_family(tmp_path, monkeypatch):
    import argparse
    from pathlib import Path
    from philengine import cli
    monkeypatch.delenv("PHIL_DATA_DIR", raising=False)
    monkeypatch.delenv("PHIL_RUNS_DIR", raising=False)
    (tmp_path / "data" / "rees").mkdir(parents=True)
    (tmp_path / "runs").mkdir()
    f = tmp_path / "data" / "rees" / "arguments.json"
    f.write_text('[{"id": "a1", "name": "x"}]')
    monkeypatch.chdir(tmp_path)
    a = argparse.Namespace(data=None, db=None)
    assert Path(cli._data_path(a)) == f
    assert Path(cli._db_path(a)) == tmp_path / "runs" / "rees.db"


def test_families_lists_cwd_data(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PHIL_DATA_DIR", raising=False)
    (tmp_path / "data" / "mine").mkdir(parents=True)
    (tmp_path / "data" / "mine" / "arguments.json").write_text("[]")
    monkeypatch.chdir(tmp_path)
    assert main(["families"]) == 0
    assert "mine" in capsys.readouterr().out
