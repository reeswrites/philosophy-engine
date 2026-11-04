"""One adaptive agent per (role, index): holds its role, adoption state (`practice`), surplus, threshold, trust.

Choice at a step (plan: "Step", slice-1 subset):
  1. a `must` rule instance on this role whose condition holds is followed (ASSUMED: never breached in slice 1);
  2. material: below the surplus `floor` the choice set collapses to the current practice (scarcity narrows choice);
  3. with probability `copy_rate`, imitate the neighbour whose last action earned most (Axelrod-style);
  4. else take the available action whose neighbour adoption share meets this agent's `threshold` (Granovetter);
  5. else material payoff-following: the available action with the highest payoff (ties broken by the model rng);
  6. else keep the practice.
Every random draw goes through `model.random`, seeded once per run.
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
        self.chosen: ActionInst | None = None
        self.last_action: ActionInst | None = None
        self.last_payoff = 0.0
        self.obligation: ActionInst | None = None  # the must instance that bound this agent at the last step
        self.threshold = model.random.random()
        self.surplus = float(model.params["initial_surplus"])
        self.neighbours: list["InstitutionAgent"] = []
        self.trust: dict[int, float] = {}  # neighbour unique_id -> trust in [0, 1]

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
        available = m.available_for(self.role)
        if "material" in m.modules and self.surplus < p["floor"]:
            available = [self.practice] if self.practice in available else []
        if not available:
            self.chosen = None
            return
        chosen: ActionInst | None = None
        if m.random.random() < p["copy_rate"]:
            earners = [n for n in self.neighbours if n.last_action in available]
            if earners:
                best = max(earners, key=lambda n: n.last_payoff)
                if best.last_payoff > self.last_payoff:
                    chosen = best.last_action
        if chosen is None:
            shares = self.neighbour_shares()
            over = [a for a in available if shares.get(a, 0.0) >= self.threshold and shares.get(a, 0.0) > 0]
            if over:
                chosen = max(over, key=lambda a: shares[a])
        if chosen is None and "material" in m.modules:
            top = max(m.payoff(a) for a in available)
            cands = [a for a in available if m.payoff(a) == top]
            chosen = m.random.choice(cands)
        if chosen is None:
            chosen = self.practice if self.practice in available else None
        self.chosen = chosen
        if chosen is not None:
            self.practice = chosen

    def neighbour_shares(self) -> dict[ActionInst, float]:
        if not self.neighbours:
            return {}
        counts: dict[ActionInst, int] = {}
        for n in self.neighbours:
            if n.practice is not None:
                counts[n.practice] = counts.get(n.practice, 0) + 1
        return {a: c / len(self.neighbours) for a, c in counts.items()}

    # ------------------------------------------------------------ settlement
    def settle(self) -> None:
        """Book this step's payoff, decay surplus by the floor cost, update trust toward neighbours."""
        m = self.model
        p = m.params
        pay = m.payoff(self.chosen) if self.chosen is not None else 0.0
        self.last_payoff = pay
        self.last_action = self.chosen
        if "material" in m.modules:
            self.surplus = max(0.0, self.surplus + pay - p["floor_cost"])
        for n in self.neighbours:
            if n.obligation is None:
                continue
            t = self.trust.get(n.unique_id, p["initial_trust"])
            if n.chosen == n.obligation:
                t += p["trust_delta"]
            else:
                t -= p["trust_beta"] * p["trust_delta"]
            self.trust[n.unique_id] = min(1.0, max(0.0, t))
