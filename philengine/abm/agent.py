"""One adaptive agent per (role, index): holds its role, adoption state (`practice`), pledge, surplus, threshold,
trust, breach and sanction state.

Choice at a step (plan: "Step"; decisions A3-A5 in computational-liberation/docs/decisions-pending.md; A8 state
obligations in ADR 0015, amendment 2026-11-04), in this priority order (ASSUMED):
  1. lawful set: the available actions that breach nothing in force now: no sanctionable must_not forbids them, every
     action-aimed must on this role is met, and every state-aimed must (ADR 0009 must-be, A8) is kept. Choosing
     nothing is lawful too iff it breaches nothing (no action must is in force and every must-be fluent already
     holds): it is the zero-payoff baseline, never a candidate by itself. A `must` is a choice, not a constraint
     (A4): any available action whose net payoff (payoff minus expected sanction for the rules it breaches) beats
     the best lawful net payoff joins the candidate set. A rule with `or_else: null` carries no sanction, so
     breaching it is free; a must_not with `or_else: null` is a disability and `Reference.power` already removed
     it (ADR 0013). A must-be no option keeps (`model.unavoidable_rules`: neither nothing nor any available action
     re-establishes P) is an UNAVOIDABLE breach, not a breach of choice: it is left out of `breaches`, prices no
     sanction, and is booked in `unavoidable` instead (2026-11-04 review finding 3; A4: breach is a choice). With
     no lawful option at all (conflicting musts) every available action is a candidate and the model records the
     diagnostic once per run (`report.warnings`).
  2. material: below the surplus `floor` the candidates collapse to the current practice plus, for each
     obligation in force, the candidates that keep it: the must action for an action must, the keep-set (the
     candidates whose successor leaves P true) for a must-be. Symmetric across the two kinds (finding 7b); the
     floor never admits an action only because it is lawful.
  3. with probability `copy_rate`, imitate the neighbour whose last action earned most (Axelrod-style), if it earned
     more than this agent did;
  4. else material payoff-following: switch to the candidate whose net payoff strictly beats the current practice's;
  5. else take the candidate whose same-role neighbour share (practice or pledge, A3) meets this `threshold`;
  6. else, with no usable practice, material bootstrap: the best net-paying candidate (ties by the model rng);
  7. else keep the practice; with obligations in force and no usable practice, a random lawful candidate.
Choosing a `*_pledge` action sets `pledge` to the base instance and leaves practice unchanged (A3 stand-in).
Updates are synchronous: every choice reads the practices and pledges snapshotted at the start of the step. Every
random draw goes through `model.random`, seeded once per run.

State obligations (A8): `must-be P when C` on role r, with C true now, obliges each agent of role r to choose an
action whose effects leave P true in the successor state (`model.keeps`: the reference's `successor` applied to the
current shared state plus this agent's own action alone). Breaching one by choice is charged exactly like an
action-rule breach and feeds trust (A5) through the fluent's declared argument roles. When no option keeps P the
breach is unavoidable: not a choice, so not charged, not in `breached`, and not an obligation outcome for trust
(ASSUMED: trust reads what a neighbour chose, and here nothing was open to choose); the agent lists the rule ids
in `unavoidable` and the model counts them per step.

Sanctions (A4; one quantity for expectation and realisation, slice-2 review item): breaching a rule with `or_else`
makes the agent sanctioned for `sanction_steps` steps; at each of those steps the realised payoff (and surplus) is
reduced by the per-step charge `sanction_weight * sanction_escalation ** (prior breaches)`. The sanction the agent
EXPECTS before breaching is the total of that charge over the window, per-step charge * sanction_steps
(`expected_sanction`), so expected == realised when the agent does not breach again inside the window; a further
breach inside the window replaces the running sanction with the new (graduated, higher) one rather than stacking
(ASSUMED).
Trust (A5): my trust in neighbour n moves when n keeps (+delta) or breaches (-beta*delta) an obligation bearing on
me: my role is among the aim's DECLARED argument roles other than the actor's (`model.bears_on`, from the action's or
fluent's `arg_roles` as the reference types them, never from instance values).
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
        # (obligation, kept) at the last step; an obligation is an action instance (must-do) or a fluent atom (must-be)
        self.obligation_outcomes: list[tuple[tuple, bool]] = []
        self.breached: list[str] = []  # rule ids breached BY CHOICE at the last step
        self.unavoidable: list[str] = []  # must-be rule ids no option could keep at the last step (not a breach)
        self.breach_count = 0  # sanctionable breaches so far (graduated sanction exponent)
        self.sanctioned_until = -1  # step index; sanctioned while model.t < this
        self.sanction_now = 0.0  # per-step charge applied while sanctioned
        # which rule of `choose` produced `chosen` at the last step (slice-3 scorer, "meaning"): one of
        # copy | switch | threshold | bootstrap | keep | obligation | none
        self.last_choice_source = "none"
        # the candidate set `choose` picked from at the last step (after the material floor), additive, read by the
        # gate's (c) vacuity guard (2026-11-04 review finding 1): was the forbidden instance ever a candidate?
        self.last_candidates: list[ActionInst] = []
        self.threshold = model.random.random()
        self.surplus = float(model.params["initial_surplus"])
        self.neighbours: list["InstitutionAgent"] = []
        self.role_neighbours: list["InstitutionAgent"] = []
        self.trust: dict[int, float] = {}  # neighbour unique_id -> trust in [0, 1]

    def snapshot(self) -> None:
        self.practice_prev = self.practice
        self.pledge_prev = self.pledge

    # ------------------------------------------------------------ sanctions
    def sanction_charge(self, rule_id: str) -> float:
        """Per-step charge while sanctioned for breaching `rule_id` now (0 if the rule carries no sanction)."""
        p = self.model.params
        if not self.model.sanctionable(rule_id):
            return 0.0
        return p["sanction_weight"] * p["sanction_escalation"] ** self.breach_count

    def expected_sanction(self, rule_id: str) -> float:
        """Total the agent expects to pay for breaching `rule_id` now: the per-step charge over `sanction_steps`."""
        return self.sanction_charge(rule_id) * int(self.model.params["sanction_steps"])

    @property
    def sanctioned(self) -> bool:
        return self.model.t < self.sanctioned_until

    # ------------------------------------------------------------ choice
    def choose(self) -> None:
        m = self.model
        p = m.params
        available = m.available_for(self.role)
        obl = m.obligation_rules(self.role)  # {act: [must rule ids]} (action-aimed)
        sobl = m.state_obligation_rules(self.role)  # {fluent atom: [must-be rule ids]} (state-aimed, A8)
        forb = m.forbidding_rules(self.role)  # {act: [sanctionable must_not rule ids]}
        unavoidable = m.unavoidable_rules(self.role)  # must-be ids no option keeps now: not a choice (finding 3)

        def breaches(a: ActionInst | None) -> list[str]:
            """Rule ids choosing `a` breaches BY CHOICE (an unavoidable must-be is breached whatever `a` is)."""
            out = list(forb.get(a, [])) if a is not None else []
            out += [r for o, rs in obl.items() if o != a for r in rs]
            out += [r for rs in m.state_breaches(self.role, a).values() for r in rs if r not in unavoidable]
            return out

        def keeps_some_state_obligation(a: ActionInst) -> bool:
            broken = m.state_breaches(self.role, a)
            return any(atom not in broken for atom in sobl)

        net = {a: m.payoff(a) - sum(self.expected_sanction(r) for r in breaches(a)) for a in available}
        lawful = [a for a in available if not breaches(a)]
        none_lawful = not breaches(None)
        if lawful or none_lawful:
            best_lawful = max([net[a] for a in lawful] + ([0.0] if none_lawful else []))
            candidates = lawful + [a for a in available if a not in lawful and net[a] > best_lawful]
        else:
            candidates = list(available)  # nothing lawful: conflicting musts, diagnosed by the model
        if "material" in m.modules and self.surplus < p["floor"]:
            candidates = [a for a in candidates
                          if a == self.practice or a in obl or keeps_some_state_obligation(a)]
        self.last_candidates = list(candidates)
        chosen: ActionInst | None = None
        source = "none"
        if candidates:
            if m.random.random() < p["copy_rate"]:
                earners = [n for n in self.neighbours if n.last_action in candidates]
                if earners:
                    best = max(earners, key=lambda n: n.last_payoff)
                    if best.last_payoff > self.last_payoff:
                        chosen = best.last_action
                        source = "copy"
            if chosen is None and "material" in m.modules and self.practice in candidates:
                better = [a for a in candidates if net[a] > net[self.practice]]
                if better:
                    top = max(net[a] for a in better)
                    chosen = m.random.choice([a for a in better if net[a] == top])
                    source = "switch"
            if chosen is None:
                shares = self.neighbour_shares()
                over = [a for a in candidates if shares.get(a, 0.0) >= self.threshold and shares.get(a, 0.0) > 0]
                if over:
                    chosen = max(over, key=lambda a: shares[a])
                    source = "threshold"
            if chosen is None and self.practice not in candidates and "material" in m.modules:
                top = max(net[a] for a in candidates)
                chosen = m.random.choice([a for a in candidates if net[a] == top])
                source = "bootstrap"
            if chosen is None:
                if self.practice in candidates:
                    chosen = self.practice
                    source = "keep"
                elif obl or sobl:
                    chosen = m.random.choice([a for a in candidates if a in lawful] or candidates)
                    source = "obligation"
        self.chosen = chosen
        self.last_choice_source = source
        broken_atoms = m.state_breaches(self.role, chosen)
        self.obligation_outcomes = [(o, o == chosen) for o in obl] + [
            (atom, atom not in broken_atoms) for atom, rids in sobl.items() if not set(rids) <= unavoidable]
        self.breached = breaches(chosen)
        self.unavoidable = sorted(unavoidable)
        sanctionable = [r for r in self.breached if m.sanctionable(r)]
        if sanctionable:
            self.sanction_now = sum(self.sanction_charge(r) for r in sanctionable)
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
                if not m.bears_on(o, self.role, n.role):
                    continue  # does not bear on me (A5): declared argument roles, not instance values
                t = self.trust.get(n.unique_id, p["initial_trust"])
                t += p["trust_delta"] if kept else -p["trust_beta"] * p["trust_delta"]
                self.trust[n.unique_id] = min(1.0, max(0.0, t))
