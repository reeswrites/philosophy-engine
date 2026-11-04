import os

import pytest


def pytest_configure(config):
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
