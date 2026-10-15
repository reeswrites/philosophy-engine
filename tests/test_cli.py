import pytest

from philengine.cli import main


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("cli") / "t.db")
    assert main(["ingest", "--db", p]) == 0
    assert main(["run", "--db", p, "--mock"]) == 0
    return p


def test_status_show_calls(db, capsys):
    assert main(["status", "--db", db]) == 0
    assert "select" in capsys.readouterr().out
    assert main(["show", "cogito", "--db", db]) == 0
    out = capsys.readouterr().out
    assert "CHOSEN" in out and "rejected:" in out and "verdict=valid" in out
    assert main(["calls", "--db", db]) == 0
    assert "total calls" in capsys.readouterr().out
    assert main(["show", "nope", "--db", db]) == 1


def test_report_and_gate(db, tmp_path, capsys):
    out = tmp_path / "r.md"
    assert main(["report", "--db", db, "--out", str(out)]) == 0
    md = out.read_text()
    for h in ("## Arguments", "## Objection coverage", "## Isomorphism", "## Concept registry", "## Review queue"):
        assert h in md
    assert "| cogito | valid | valid | yes" in md
    capsys.readouterr()
    assert main(["gate", "--db", db]) == 0
    assert "GATE: PASS" in capsys.readouterr().out


def test_gate_fails_without_run(tmp_path, capsys):
    p = str(tmp_path / "e.db")
    main(["ingest", "--db", p])
    assert main(["gate", "--db", p]) == 1


def test_gate_fails_on_partial_run(tmp_path, capsys):
    p = str(tmp_path / "p.db")
    assert main(["run", "--db", p, "--mock", "--stage", "reconstruct", "--stage", "formalize", "--args", "cogito"]) == 0
    assert main(["gate", "--db", p]) == 1
    assert "missing stages" in capsys.readouterr().out
