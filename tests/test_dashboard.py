import json
import re

from philengine import dashboard
from philengine.cli import main
from philengine.llm import MockLLMClient
from philengine.pipeline import ALL_STAGES, run_all
from philengine.store import Store


def _mock_store():
    st = Store(":memory:")
    st.ingest()
    rid = st.new_run({"from_human": False}, mock=True)
    run_all(st, rid, MockLLMClient(st, rid), None, ALL_STAGES, {"from_human": False}, True, False)
    return st, rid


def test_dashboard_from_memory_run(tmp_path):
    st, rid = _mock_store()
    out = dashboard.write_dashboard(st, rid, tmp_path / "d.html")
    html = out.read_text()
    assert out.exists() and "cogito" in html and "Gate: PASS" in html
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))
    assert len(data["arguments"]) == 15
    assert data["gate"]["passed"] and data["run"]["mock"]
    srcs = re.findall(r'<script src="([^"]+)"', html)
    assert srcs == [dashboard.D3_URL] and "cdnjs.cloudflare.com" in srcs[0]


def test_cli_dashboard(tmp_path):
    p = str(tmp_path / "t.db")
    assert main(["ingest", "--db", p]) == 0 and main(["run", "--db", p, "--mock"]) == 0
    o = tmp_path / "x" / "dash.html"
    assert main(["dashboard", "--db", p, "--out", str(o)]) == 0 and "cogito" in o.read_text()
