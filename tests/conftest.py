import os

import pytest


def pytest_configure(config):
    from . import helpers  # captures PHIL_DATA_DIR as the invoker set it, before it is dropped below
    os.environ.pop("PHIL_DATA_DIR", None)  # import-time snapshots (config.DATA_DIR) must see the engine's own data/
    config.addinivalue_line("markers", "llm: live Anthropic API tests (need ANTHROPIC_API_KEY; run with -m llm)")
    config.addinivalue_line("markers", "slow: long-running differential / dataset tests (deselect with -m 'not slow')")


def pytest_collection_modifyitems(config, items):
    from philengine import config as phil_config
    phil_config.load_env()  # .env alone must be enough to enable -m llm
    if "llm" not in (config.getoption("markexpr") or ""):
        reason = "live LLM test (costs money): run explicitly with `-m llm`"
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        reason = "needs ANTHROPIC_API_KEY (put it in .env or export it) to run live LLM tests"
    else:
        return
    skip = pytest.mark.skip(reason=reason)
    for it in items:
        if "llm" in it.keywords:
            it.add_marker(skip)


@pytest.fixture
def dataset_env(monkeypatch):
    """Skip when no institutions dataset is available; else point PHIL_DATA_DIR at it (so CLI calls and subprocesses
    resolve it too) and return (institutions.json, properties.json)."""
    from .helpers import dataset_root, require_dataset
    paths = require_dataset()
    monkeypatch.setenv("PHIL_DATA_DIR", str(dataset_root()))
    return paths


@pytest.fixture(autouse=True)
def _engine_data_by_default(monkeypatch):
    """PHIL_DATA_DIR names where the *institutions dataset* lives (see helpers.dataset_root); the engine's own data/
    (phase0 arguments, and the data/example/ fixture that default_paths() falls back to) must resolve regardless, so
    tests start without it. dataset_env sets it back explicitly."""
    monkeypatch.delenv("PHIL_DATA_DIR", raising=False)
