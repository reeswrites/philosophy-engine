import json
from pathlib import Path

from philengine.schemas import FormalizationJSON

FIX = Path(__file__).parent / "fixtures" / "formalizations"


def load(name: str) -> FormalizationJSON:
    return FormalizationJSON.model_validate(json.loads((FIX / f"{name}.json").read_text()))


# ---------------------------------------------------------------- the institutions dataset lives outside the engine
# PHIL_DATA_DIR as the invoker set it, captured once. conftest then unsets it for every test (the engine's own
# data/phase0 must resolve regardless), so dataset lookups go through this value instead of the live environment.
import os as _os
DATASET_ENV = _os.environ.get("PHIL_DATA_DIR")
def dataset_root():
    """Directory holding institutions/{institutions,properties}.json, or None when no dataset is available.

    This is the full research dataset (private repo computational-liberation), which the dataset-dependent tests
    assert claims about by institution id; the engine's own data/example/ fixture is NOT a candidate (its tests are in
    test_example_fixture.py). PHIL_DATA_DIR wins outright (so PHIL_DATA_DIR=/nonexistent means "no dataset"); else
    ./data when the cwd is a private instance; else the sibling checkout ../computational-liberation/data."""
    def ok(p: Path) -> bool:
        return (p / "institutions" / "institutions.json").is_file() and (p / "institutions" / "properties.json").is_file()

    env = DATASET_ENV
    if env:
        p = Path(env).expanduser()
        return p if ok(p) else None
    for p in (Path.cwd() / "data", Path(__file__).resolve().parent.parent.parent / "computational-liberation" / "data"):
        if ok(p):
            return p
    return None


NO_DATASET = ("institutions dataset not found (set PHIL_DATA_DIR or check out ../computational-liberation); "
              "dataset-dependent test skipped")


def dataset_paths():
    """(institutions.json, properties.json) or None."""
    r = dataset_root()
    return None if r is None else (r / "institutions" / "institutions.json", r / "institutions" / "properties.json")


def require_dataset():
    """For use inside a test or helper: the dataset paths, or pytest.skip with a clear reason."""
    import pytest
    p = dataset_paths()
    if p is None:
        pytest.skip(NO_DATASET)
    return p
