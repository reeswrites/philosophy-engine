"""AbmReport: the JSON record of one ABM run (plan: "Reproducibility").

Fields: institution, seed, modules (the mechanism switches that were on), params, steps, agents_per_role,
adoption (per step, per role: share of that role's agents whose practice is each action instance; "none" = no
practice yet), fluent_rates (final step: share of a state fluent's tuples that are true; derived fluents are
evaluated through the reference), breaches (per step, per role: share that breached a rule BY CHOICE, A4),
unavoidable (per step, per role: share under a must-be no option could keep; not a breach of choice, not
sanctioned, 2026-11-04 review finding 3), sanctioned, warnings. Score vectors and necessary_modules are later
slices.
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
    breaches: list[dict[str, float]] = field(default_factory=list)  # [step][role] -> share that breached by choice
    unavoidable: list[dict[str, float]] = field(default_factory=list)  # [step][role] -> share under unavoidable must-be
    sanctioned: list[dict[str, float]] = field(default_factory=list)  # [step][role] -> share under sanction
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int | None = 1) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def final_adoption(self) -> dict[str, dict[str, float]]:
        return self.adoption[-1] if self.adoption else {}

    def breach_rate(self) -> dict[str, float]:
        """Per role: share of agent-steps on which a rule was breached by choice (unavoidable breaches excluded)."""
        return _mean_over_steps(self.breaches)

    def unavoidable_rate(self) -> dict[str, float]:
        """Per role: share of agent-steps under a must-be no option could keep (an encoder diagnostic, not a
        choice; see `breach_rate`)."""
        return _mean_over_steps(self.unavoidable)

    def sanctioned_rate(self) -> dict[str, float]:
        return _mean_over_steps(self.sanctioned)


def _mean_over_steps(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    out: dict[str, float] = {}
    for row in rows:
        for role, v in row.items():
            out[role] = out.get(role, 0.0) + v / len(rows)
    return out


def summarize(reports: list[AbmReport]) -> dict:
    """Rates over seeds (plan: "Frequency, not entailment"): mean final adoption share per role and action, mean
    final fluent rate, plus every per-seed report. Statements about an encoding plus a policy, not a population."""
    n = len(reports)
    adoption: dict[str, dict[str, float]] = {}
    fluents: dict[str, float] = {}
    breach: dict[str, float] = {}
    unavoidable: dict[str, float] = {}
    sanctioned: dict[str, float] = {}
    for r in reports:
        for role, shares in r.final_adoption().items():
            acc = adoption.setdefault(role, {})
            for a, s in shares.items():
                acc[a] = acc.get(a, 0.0) + s / n
        for f, v in r.fluent_rates.items():
            fluents[f] = fluents.get(f, 0.0) + v / n
        for role, v in r.breach_rate().items():
            breach[role] = breach.get(role, 0.0) + v / n
        for role, v in r.unavoidable_rate().items():
            unavoidable[role] = unavoidable.get(role, 0.0) + v / n
        for role, v in r.sanctioned_rate().items():
            sanctioned[role] = sanctioned.get(role, 0.0) + v / n
    return {
        "institution": reports[0].institution if reports else None,
        "seeds": [r.seed for r in reports],
        "modules": reports[0].modules if reports else [],
        "steps": reports[0].steps if reports else 0,
        "adoption_over_seeds": {role: dict(sorted(v.items())) for role, v in sorted(adoption.items())},
        "fluent_rates_over_seeds": dict(sorted(fluents.items())),
        "breach_rate_over_seeds": dict(sorted(breach.items())),
        "unavoidable_rate_over_seeds": dict(sorted(unavoidable.items())),
        "sanctioned_rate_over_seeds": dict(sorted(sanctioned.items())),
        "runs": [r.to_dict() for r in reports],
    }
