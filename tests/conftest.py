import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: live Anthropic API tests (need ANTHROPIC_API_KEY)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    skip = pytest.mark.skip(reason="needs ANTHROPIC_API_KEY (put it in .env or export it) to run live LLM tests")
    for it in items:
        if "llm" in it.keywords:
            it.add_marker(skip)
