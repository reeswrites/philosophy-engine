import json
from pathlib import Path

from philengine.schemas import FormalizationJSON

FIX = Path(__file__).parent / "fixtures" / "formalizations"


def load(name: str) -> FormalizationJSON:
    return FormalizationJSON.model_validate(json.loads((FIX / f"{name}.json").read_text()))
