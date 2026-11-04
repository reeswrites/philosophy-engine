"""One adaptive agent per (role, index): holds its role, adoption state (`practice`), surplus, threshold, trust.

Choice at a step (plan: "Step", slice-1 subset), in this priority order (ASSUMED):
  1. a `must` rule instance on this role whose condition holds is followed (never breached in slice 1);
  2. the candidate set is the role's available actions (`Reference.power`) minus those a must_not forbids now
     (strict compliance on the firing side, ASSUMED);
  3. material: below the surplus `floor` the candidate set collapses to the current practice (scarcity narrows choice);
  4. with probability `copy_rate`, imitate the neighbour whose last action earned most (Axelrod-style), if it earned
     more than this agent did;
  5. else material payoff-following: switch to the candidate that pays strictly more than the current practice
     (ties among the best broken by the model rng);
  6. else take the candidate whose same-role neighbour adoption share meets this agent's `threshold` (Granovetter);
  7. else, with no usable practice, material bootstrap: the best-paying candidate (ties broken by the model rng);
  8. else keep the practice.
Updates are synchronous: every choice reads the practices snapshotted at the start of the step. Every random draw
goes through `model.random`, seeded once per run.
"""
from __future__ import annotations

import mesa

ActionInst = tuple[str, tuple]


def action_label(a: ActionInst | None) -> str:
    if a is None:
        return "none"
    name, args = a
    return f"{name}({','.join(args)})"


class InstitutionAgent(mesa.Agent):
    def __init__(self, model, role: str):
        super().__init__(model)
        self.role = role
        self.practice: ActionInst | None = None
        self.practice_prev: ActionInst | None = None  # snapshot at the start of the step (synchronous update)
        self.chosen: ActionInst | None = None
        self.last_action: ActionInst | None = None
        self.last_payoff = 0.0
        self.obligation: ActionInst | None = None  # the must instance that bound this agent at the last step
        self.threshold = model.random.random()
        self.surplus = float(model.params["initial_surplus"])
        self.neighbours: list["InstitutionAgent"] = []
        self.role_neighbours: list["InstitutionAgent"] = []
        self.trust: dict[int, float] = {}  # neighbour unique_id -> trust in [0, 1]

    def snapshot(self) -> None:
        self.practice_prev = self.practice

    # ------------------------------------------------------------ choice
    def choose(self) -> None:
        m = self.model
        p = m.params
        self.obligation = None
        musts = m.obligations_for(self.role)
        if musts:
            self.obligation = self.chosen = m.random.choice(musts)
            self.practice = self.chosen
            return
        forbidden = m.forbidden_for(self.role)
        candidates = [a for a in m.available_for(self.role) if a not in forbidden]
        if "material" in m.modules and self.surplus < p["floor"]:
            candidates = [self.practice] if self.practice in candidates else []
        if not candidates:
            self.chosen = None
            return
        chosen: ActionInst | None = None
        if m.random.random() < p["copy_rate"]:
            earners = [n for n in self.neighbours if n.last_action in candidates]
            if earners:
                best = max(earners, key=lambda n: n.last_payoff)
                if best.last_payoff > self.last_payoff:
                    chosen = best.last_action
        if chosen is None and "material" in m.modules and self.practice in candidates:
            better = [a for a in candidates if m.payoff(a) > m.payoff(self.practice)]
            if better:
                top = max(m.payoff(a) for a in better)
                chosen = m.random.choice([a for a in better if m.payoff(a) == top])
        if chosen is None:
            shares = self.neighbour_shares()
            over = [a for a in candidates if shares.get(a, 0.0) >= self.threshold and shares.get(a, 0.0) > 0]
            if over:
                chosen = max(over, key=lambda a: shares[a])
        if chosen is None and self.practice not in candidates and "material" in m.modules:
            top = max(m.payoff(a) for a in candidates)
            chosen = m.random.choice([a for a in candidates if m.payoff(a) == top])
        if chosen is None:
            chosen = self.practice if self.practice in candidates else None
        self.chosen = chosen
        if chosen is not None:
            self.practice = chosen

    def neighbour_shares(self) -> dict[ActionInst, float]:
        """Share of same-role neighbours whose practice (at the step's start) is each action."""
        if not self.role_neighbours:
            return {}
        counts: dict[ActionInst, int] = {}
        for n in self.role_neighbours:
            if n.practice_prev is not None:
                counts[n.practice_prev] = counts.get(n.practice_prev, 0) + 1
        return {a: c / len(self.role_neighbours) for a, c in counts.items()}

    # ------------------------------------------------------------ settlement
    def settle(self) -> None:
        """Book this step's action payoff (for imitation), accrue income-fluent surplus minus the floor cost, update
        trust toward neighbours."""
        m = self.model
        p = m.params
        self.last_payoff = m.payoff(self.chosen) if self.chosen is not None else 0.0
        self.last_action = self.chosen
        if "material" in m.modules:
            self.surplus = max(0.0, self.surplus + m.income_for(self.role) - p["floor_cost"])
        for n in self.neighbours:
            if n.obligation is None:
                continue
            t = self.trust.get(n.unique_id, p["initial_trust"])
            if n.chosen == n.obligation:
                t += p["trust_delta"]
            else:
                t -= p["trust_beta"] * p["trust_delta"]
            self.trust[n.unique_id] = min(1.0, max(0.0, t))
