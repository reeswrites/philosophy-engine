"""AbmReport: the JSON record of one ABM run (plan: "Reproducibility").

Fields: institution, seed, modules (the mechanism switches that were on), params, steps, agents_per_role,
adoption (per step, per role: share of that role's agents whose practice is each action instance; "none" = no
practice yet), fluent_rates (final step: share of a state fluent's tuples that are true; derived fluents are
evaluated through the reference), warnings. Score vectors and necessary_modules are later slices.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class AbmReport:
    institution: str
    seed: int
    modules: list[str]
    params: dict
    steps: int
    agents_per_role: int
    roles: list[str]
    adoption: list[dict[str, dict[str, float]]] = field(default_factory=list)  # [step][role][action] -> share
    fluent_rates: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int | None = 1) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def final_adoption(self) -> dict[str, dict[str, float]]:
        return self.adoption[-1] if self.adoption else {}
