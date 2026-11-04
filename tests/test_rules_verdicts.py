import json

from philengine import cli_rules, rules_verdicts as rv, scoreboard

from .test_rules_lower import tiny

F = "(exists ((w agent)) (paid w t))"
PROPS = [{"name": "worker_paid", "kind": "structure", "formal": F},
         {"name": "worker_paid_twin", "kind": "structure", "formal": F},  # identical formal text, other name
         {"name": "paid_if_employed", "kind": "structure", "formal": "(forall ((w agent)) (=> (employed w t) (paid w t)))"}]


def _dataset(tmp_path):
    d = tmp_path / "ds"
    d.mkdir()
    inst = tiny().model_dump(mode="json")
    inst["expected_properties"] = {"worker_paid": "reachable", "worker_paid_twin": "reachable", "paid_if_employed": "invariant"}
    (d / "i.json").write_text(json.dumps([inst]))
    (d / "p.json").write_text(json.dumps(PROPS))
    return ["--institutions", str(d / "i.json"), "--properties", str(d / "p.json"), "--k", "3"]


class cli_rules_:
    @staticmethod
    def main(argv):
        a = cli_rules.build_parser().parse_args(["rules", *argv])
        return a.fn(a)


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIL_RUNS_DIR", str(tmp_path / "runs"))
    ds = _dataset(tmp_path)
    base = tmp_path / "base.json"
    assert cli_rules_.main(["verdicts", "--out", str(base), *ds]) == 0
    return ds, base


def test_baseline_shape_twin_rows_and_self_diff(tmp_path, monkeypatch, capsys):
    ds, base = setup(tmp_path, monkeypatch)
    b = json.loads(base.read_text())
    assert set(b) == {"format", "engine_hash", "z3", "params", "rows"}
    assert b["params"] == {"k": 3, "init": None, "compliance": "strict", "step_mode": "one"}
    names = [r["property"] for r in b["rows"]]
    assert "worker_paid" in names and "worker_paid_twin" in names  # two rows for identical formal text
    assert b["rows"] == sorted(b["rows"], key=lambda r: (r["institution"], r["property"], r["check"]))
    out = tmp_path / "d.json"
    assert cli_rules_.main(["diff", "--baseline", str(base), *ds, "--json", str(out)]) == 0
    assert "0 changed, 0 added, 0 removed" in capsys.readouterr().out
    assert json.loads(out.read_text())["ok"] is True


def _mutate(base, tmp_path, fn):
    b = json.loads(base.read_text())
    fn(b)
    p = tmp_path / "mut.json"
    p.write_text(json.dumps(b))
    return p


def test_changed_removed_added_and_exit_codes(tmp_path, monkeypatch, capsys):
    ds, base = setup(tmp_path, monkeypatch)

    def flip(b):
        b["rows"][0]["verdict"] = "violated" if b["rows"][0]["verdict"] != "violated" else "holds"
    old = json.loads(base.read_text())["rows"][0]["verdict"]
    p = _mutate(base, tmp_path, flip)
    assert cli_rules_.main(["diff", "--baseline", str(p), *ds]) == 1
    out = capsys.readouterr().out
    assert "1 changed, 0 added, 0 removed" in out and f"-> {old}" in out

    # a baseline row the engine no longer produces: removed, fails
    p = _mutate(base, tmp_path, lambda b: b["rows"].append({"institution": "tiny", "property": "gone", "check": "reachable", "verdict": "holds"}))
    assert cli_rules_.main(["diff", "--baseline", str(p), *ds]) == 1
    assert "0 changed, 0 added, 1 removed" in capsys.readouterr().out

    # a current row missing from the baseline: added, reported, does not fail
    p = _mutate(base, tmp_path, lambda b: b["rows"].pop(0))
    assert cli_rules_.main(["diff", "--baseline", str(p), *ds]) == 0
    assert "0 changed, 1 added, 0 removed" in capsys.readouterr().out


def test_diff_rows_unit():
    d = rv.diff_rows({("a", "p", "c"): "holds", ("a", "q", "c"): "holds"}, {("a", "p", "c"): "violated", ("b", "r", "c"): "holds"})
    assert (len(d["changed"]), len(d["added"]), len(d["removed"]), d["ok"]) == (1, 1, 1, False)
    assert d["summary"] == "1 changed, 1 added, 1 removed (of 2 rows)"


def test_scoreboard_append_twice_one_header(tmp_path):
    p = tmp_path / "sb.md"
    scoreboard.append_row(p, {"date": "2026-01-01", "engine": "abc", "command": "x", "rows": 3})
    scoreboard.append_row(p, {"date": "2026-01-02", "engine": "dirty+abc", "command": "y", "rows": 4})
    lines = p.read_text().splitlines()
    assert len(lines) == 4 and lines[0].startswith("| date |") and lines[1].startswith("| ---")
    assert sum(l.startswith("| date") for l in lines) == 1
    assert lines[2].startswith("| 2026-01-01 | abc | x | 3 |") and "| - |" in lines[2]


def test_scoreboard_flag_on_check_all_and_diff(tmp_path, monkeypatch):
    ds, base = setup(tmp_path, monkeypatch)
    sb = tmp_path / "sb.md"
    assert cli_rules_.main(["check-all", *ds, "--scoreboard", str(sb)]) in (0, 1)
    assert cli_rules_.main(["diff", "--baseline", str(base), *ds, "--scoreboard", str(sb)]) == 0
    lines = sb.read_text().splitlines()
    assert len(lines) == 4
    assert "rules check-all" in lines[2] and "rules diff" in lines[3]
    cells = [c.strip() for c in lines[3].strip("|").split("|")]
    assert cells[4] == "0" and cells[3] == "5"  # 5 rows
