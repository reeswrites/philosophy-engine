"""One adaptive agent per (role, index): holds its role, adoption state (`practice`), pledge, surplus, threshold,
trust, breach and sanction state.

Choice at a step (plan: "Step"; decisions A3-A5 in computational-liberation/docs/decisions-pending.md), in this
priority order (ASSUMED):
  1. lawful set: the obligations (must instances whose condition holds) if any, else the available actions no
     sanctionable must_not forbids now. A `must` is a choice, not a constraint (A4): any available action whose
     net payoff (payoff minus expected sanction for the rules it breaches) beats the best lawful net payoff joins
     the candidate set. A rule with `or_else: null` carries no sanction, so breaching it is free; a must_not with
     `or_else: null` is a disability and `Reference.power` already removed it (ADR 0013).
  2. material: below the surplus `floor` the candidates collapse to the current practice plus the obligations.
  3. with probability `copy_rate`, imitate the neighbour whose last action earned most (Axelrod-style), if it earned
     more than this agent did;
  4. else material payoff-following: switch to the candidate whose net payoff strictly beats the current practice's;
  5. else take the candidate whose same-role neighbour share (practice or pledge, A3) meets this `threshold`;
  6. else, with no usable practice, material bootstrap: the best net-paying candidate (ties by the model rng);
  7. else keep the practice; with obligations and no practice, a random obligation.
Choosing a `*_pledge` action sets `pledge` to the base instance and leaves practice unchanged (A3 stand-in).
Updates are synchronous: every choice reads the practices and pledges snapshotted at the start of the step. Every
random draw goes through `model.random`, seeded once per run.

Sanctions (A4): breaching a rule with `or_else` makes the agent sanctioned for `sanction_steps`; while sanctioned
the realised payoff (and surplus) is reduced by `sanction_weight * sanction_escalation ** (prior breaches)`, the
same quantity the agent expects before breaching (graduated: repeat breaches raise it).
Trust (A5): my trust in neighbour n moves when n keeps (+delta) or breaches (-beta*delta) an obligation bearing on
me: the obligation instance's action has my role among its non-actor arguments.
"""
from __future__ import annotations

import mesa

ActionInst = tuple[str, tuple]
PLEDGE_SUFFIX = "_pledge"


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
        self.pledge: ActionInst | None = None  # base instance this agent has publicly pledged (A3 stand-in)
        self.pledge_prev: ActionInst | None = None
        self.chosen: ActionInst | None = None
        self.last_action: ActionInst | None = None
        self.last_payoff = 0.0
        self.obligation_outcomes: list[tuple[ActionInst, bool]] = []  # (obligation, kept) at the last step
        self.breached: list[str] = []  # rule ids breached at the last step
        self.breach_count = 0  # sanctionable breaches so far (graduated sanction exponent)
        self.sanctioned_until = -1  # step index; sanctioned while model.t < this
        self.sanction_now = 0.0  # weight applied while sanctioned
        self.threshold = model.random.random()
        self.surplus = float(model.params["initial_surplus"])
        self.neighbours: list["InstitutionAgent"] = []
        self.role_neighbours: list["InstitutionAgent"] = []
        self.trust: dict[int, float] = {}  # neighbour unique_id -> trust in [0, 1]

    def snapshot(self) -> None:
        self.practice_prev = self.practice
        self.pledge_prev = self.pledge

    # ------------------------------------------------------------ sanctions
    def expected_sanction(self, rule_id: str) -> float:
        p = self.model.params
        if not self.model.sanctionable(rule_id):
            return 0.0
        return p["sanction_weight"] * p["sanction_escalation"] ** self.breach_count

    @property
    def sanctioned(self) -> bool:
        return self.model.t < self.sanctioned_until

    # ------------------------------------------------------------ choice
    def choose(self) -> None:
        m = self.model
        p = m.params
        available = m.available_for(self.role)
        obl = m.obligation_rules(self.role)  # {act: [must rule ids]}
        forb = m.forbidding_rules(self.role)  # {act: [sanctionable must_not rule ids]}

        def breaches(a: ActionInst | None) -> list[str]:
            out = list(forb.get(a, [])) if a is not None else []
            out += [r for o, rs in obl.items() if o != a for r in rs]
            return out

        net = {a: m.payoff(a) - sum(self.expected_sanction(r) for r in breaches(a)) for a in available}
        lawful = [a for a in available if a in obl] if obl else [a for a in available if a not in forb]
        if lawful:
            best_lawful = max(net[a] for a in lawful)
            candidates = lawful + [a for a in available if a not in lawful and net[a] > best_lawful]
        else:
            candidates = list(available)
        if "material" in m.modules and self.surplus < p["floor"]:
            candidates = [a for a in candidates if a == self.practice or a in obl]
        chosen: ActionInst | None = None
        if candidates:
            if m.random.random() < p["copy_rate"]:
                earners = [n for n in self.neighbours if n.last_action in candidates]
                if earners:
                    best = max(earners, key=lambda n: n.last_payoff)
                    if best.last_payoff > self.last_payoff:
                        chosen = best.last_action
            if chosen is None and "material" in m.modules and self.practice in candidates:
                better = [a for a in candidates if net[a] > net[self.practice]]
                if better:
                    top = max(net[a] for a in better)
                    chosen = m.random.choice([a for a in better if net[a] == top])
            if chosen is None:
                shares = self.neighbour_shares()
                over = [a for a in candidates if shares.get(a, 0.0) >= self.threshold and shares.get(a, 0.0) > 0]
                if over:
                    chosen = max(over, key=lambda a: shares[a])
            if chosen is None and self.practice not in candidates and "material" in m.modules:
                top = max(net[a] for a in candidates)
                chosen = m.random.choice([a for a in candidates if net[a] == top])
            if chosen is None:
                if self.practice in candidates:
                    chosen = self.practice
                elif obl:
                    chosen = m.random.choice([a for a in candidates if a in obl] or candidates)
        self.chosen = chosen
        self.obligation_outcomes = [(o, o == chosen) for o in obl]
        self.breached = breaches(chosen)
        sanctionable = [r for r in self.breached if m.sanctionable(r)]
        if sanctionable:
            self.sanction_now = self.expected_sanction(sanctionable[0])
            self.breach_count += 1
            self.sanctioned_until = m.t + int(p["sanction_steps"])
        if chosen is not None:
            if m.is_pledge(chosen):
                self.pledge = m.pledge_base(chosen)
            else:
                self.practice = chosen

    def neighbour_shares(self) -> dict[ActionInst, float]:
        """Share of same-role neighbours whose practice or pledge (at the step's start) is each action."""
        if not self.role_neighbours:
            return {}
        counts: dict[ActionInst, int] = {}
        for n in self.role_neighbours:
            seen = {n.practice_prev, n.pledge_prev} - {None}
            for a in seen:
                counts[a] = counts.get(a, 0) + 1
        return {a: c / len(self.role_neighbours) for a, c in counts.items()}

    # ------------------------------------------------------------ settlement
    def settle(self) -> None:
        """Book this step's realised payoff (sanction deducted while sanctioned), accrue income-fluent surplus minus
        the floor cost, update directed trust toward neighbours."""
        m = self.model
        p = m.params
        penalty = self.sanction_now if self.sanctioned else 0.0
        self.last_payoff = (m.payoff(self.chosen) if self.chosen is not None else 0.0) - penalty
        self.last_action = self.chosen
        if "material" in m.modules:
            self.surplus = max(0.0, self.surplus + m.income_for(self.role) - p["floor_cost"] - penalty)
        for n in self.neighbours:
            for o, kept in n.obligation_outcomes:
                if self.role not in o[1][1:]:
                    continue  # does not bear on me (A5)
                t = self.trust.get(n.unique_id, p["initial_trust"])
                t += p["trust_delta"] if kept else -p["trust_beta"] * p["trust_delta"]
                self.trust[n.unique_id] = min(1.0, max(0.0, t))
