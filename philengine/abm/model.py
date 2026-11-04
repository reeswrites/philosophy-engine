"""Mesa 3.x model over one InstitutionJSON (plan: "Design", "Step", "Modules").

The institutional state is the reference's role-level state (a frozenset of (fluent, tuple) atoms); every reading
of the rules goes through `rules_reference.Reference`:
  available_for(role)   action instances (a, (role, ...)) that are powers in the current state: exactly
                        `Reference.power` (ADR 0013 reading: some may/must rule instance's condition holds and no
                        `or_else: null` disability bars it). A sanctionable must_not leaves the action available.
                        An action no may/must rule names is never available to an agent.
  forbidden_for(role)   instances a sanctionable must_not rule instance forbids now (`forbidding_rules` gives the
                        rule ids); breaching one is a choice weighed against the expected sanction (A4).
  obligations_for(role) must rule instances on (a, (role, ...)) whose condition holds now (`obligation_rules`
                        gives the rule ids); likewise a choice (A4).
  sanctionable(rule)    the rule has `or_else` (a sanction exists); `or_else: null` on a must = free to breach.
  is_pledge / pledge_base  an action named `X_pledge` with X declared is a pledge for X (A3 stand-in).
  successor             `Reference.successor` on the union of distinct instances agents chose this step.
  income_for(role)      sum of `payoffs[f]` over state atoms (f, tuple) with the role in the tuple, for fluent
                        names in the payoffs block (plan: "surplus accrues from income fluents"). With no income
                        fluent declared, `params["default_income"]` per step (ASSUMED).
  fluent_rates          `Reference.atom` per tuple (state and derived fluents alike).

Payoffs (ASSUMED, see package docstring): `load_payoffs` reads an optional top-level `payoffs` dict from the
institution's raw entry in institutions.json. A key naming an action is that action's payoff (imitation and
payoff-following); a key naming a fluent is an income fluent. Absent, every action pays `default_payoff`.
Initial state: the reference's declared/empty split, with every unconstrained atom false (ASSUMED).

Mechanism modules: `material` (slice 1); `coordination`, `imagination` raise NotImplementedError.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import mesa

from ..rules_reference import Reference
from ..schemas_rules import InstitutionJSON
from .agent import PLEDGE_SUFFIX, ActionInst, InstitutionAgent, action_label
from .graph import DEFAULT_K, DEFAULT_P, small_world
from .report import AbmReport

MODULES = ("material", "coordination", "imagination")
DEFAULT_STEPS = 50
DEFAULT_AGENTS_PER_ROLE = 20
# Every value here is a slice-1 placeholder to be SWEPT, not calibrated (plan: "Non-goals"); see the package
# docstring for the proposed range of each.
DEFAULT_PARAMS: dict[str, float] = {
    "copy_rate": 0.3,  # probability of success imitation at a step
    "default_payoff": 1.0,  # payoff of an action no `payoffs` entry names
    "default_income": 1.0,  # per-step income when the payoffs block names no income fluent
    "initial_surplus": 2.0,
    "floor": 1.0,  # material: below this surplus the choice set collapses to current practice
    "floor_cost": 0.5,  # material: surplus decays by this each step
    "initial_trust": 0.5,
    "trust_delta": 0.1,
    "trust_beta": 2.0,
    "sanction_weight": 1.0,  # A4: expected and realised sanction for breaching a rule with or_else
    "sanction_steps": 3,  # A4: steps an agent stays sanctioned after a breach
    "sanction_escalation": 1.5,  # A4: graduated sanction multiplier per prior breach
}


def _check_modules(modules) -> list[str]:
    out = []
    for m in modules:
        if m not in MODULES:
            raise ValueError(f"unknown mechanism module {m!r}; have {MODULES}")
        if m in ("coordination", "imagination"):
            raise NotImplementedError(f"mechanism module {m!r} is not in slice 1 (stub)")
        out.append(m)
    return out


def load_payoffs(path: str | Path, inst_id: str) -> dict[str, float] | None:
    """The optional `payoffs` block of the institution's raw entry ({action or fluent: float}), or None."""
    raw = json.loads(Path(path).read_text())
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("id") == inst_id:
            p = item.get("payoffs")
            return {str(k): float(v) for k, v in p.items()} if isinstance(p, dict) else None
    return None


class InstitutionModel(mesa.Model):
    def __init__(self, inst: InstitutionJSON, seed: int = 0, agents_per_role: int = DEFAULT_AGENTS_PER_ROLE,
                 modules=("material",), payoffs: dict[str, float] | None = None, params: dict | None = None,
                 graph_k: int = DEFAULT_K, graph_p: float = DEFAULT_P):
        super().__init__(rng=seed)
        self.inst = inst
        self.seed_value = seed
        self.agents_per_role = agents_per_role
        self.modules = _check_modules(modules)
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.payoffs = dict(payoffs or {})
        self.warnings: list[str] = []
        self.ref = Reference(inst, k=1)
        self.t = 0
        self._sanctionable = {r.id: r.or_else is not None for r in inst.rules}
        self._action_names = {a.name for a in inst.actions}
        fluent_names = {f.name for f in inst.fluents}
        self.income_fluents = {k: v for k, v in self.payoffs.items() if k in fluent_names}
        fixed, free = self.ref.initial_split()
        if free:
            self.warnings.append(f"{len(free)} unconstrained initial atom(s) set false")
        self.state: frozenset = frozenset(fixed) & self.ref.all_atoms
        self.roles = [r.name for r in inst.roles]
        self.by_role: dict[str, list[InstitutionAgent]] = {r: [] for r in self.roles}
        population: list[InstitutionAgent] = []
        for role in self.roles:
            for _ in range(agents_per_role):
                a = InstitutionAgent(self, role)
                self.by_role[role].append(a)
                population.append(a)
        g, warn = small_world(len(population), seed, graph_k, graph_p)
        if warn:
            self.warnings.append(warn)
        for i, a in enumerate(population):
            a.neighbours = [population[j] for j in g.neighbors(i)]
            a.role_neighbours = [n for n in a.neighbours if n.role == a.role]
        self.adoption: list[dict[str, dict[str, float]]] = []
        self.breaches: list[dict[str, float]] = []  # [step][role] -> share of agents that breached a rule
        self.sanctioned: list[dict[str, float]] = []  # [step][role] -> share sanctioned
        self._cache: dict[str, tuple] = {}

    # ------------------------------------------------------------ rule readings (through the reference)
    def sanctionable(self, rule_id: str) -> bool:
        return self._sanctionable.get(rule_id, False)

    def is_pledge(self, a: ActionInst) -> bool:
        n = a[0]
        return n.endswith(PLEDGE_SUFFIX) and n[: -len(PLEDGE_SUFFIX)] in self._action_names

    def pledge_base(self, a: ActionInst) -> ActionInst:
        return (a[0][: -len(PLEDGE_SUFFIX)], a[1])

    def payoff(self, a: ActionInst | None) -> float:
        if a is None:
            return 0.0
        return self.payoffs.get(a[0], self.params["default_payoff"])

    def income_for(self, role: str) -> float:
        if not self.income_fluents:
            return self.params["default_income"]
        return sum(v for f, v in self.income_fluents.items()
                   for atom in self.state if atom[0] == f and role in atom[1])

    def _readings(self, role: str) -> tuple[list[ActionInst], dict[ActionInst, list[str]], dict[ActionInst, list[str]]]:
        """(available, {forbidden act: must_not rule ids}, {obligation act: must rule ids}) for a role in the
        current state; cached per state."""
        if role in self._cache:
            return self._cache[role]
        available: list[ActionInst] = []
        forbidden: dict[ActionInst, list[str]] = {}
        musts: dict[ActionInst, list[str]] = {}
        for act in self.ref.action_insts:
            if not act[1] or act[1][0] != role:
                continue
            if not self.ref.power(self.state, act[0], act[1]):
                continue
            available.append(act)
            for ri in self.ref.rules_on.get(act, []):
                if ri.deontic == "must_not" and self.sanctionable(ri.rule_id) and self.ref.cond_holds(ri, self.state):
                    forbidden.setdefault(act, []).append(ri.rule_id)
                if ri.deontic == "must" and self.ref.cond_holds(ri, self.state):
                    musts.setdefault(act, []).append(ri.rule_id)
        self._cache[role] = (available, forbidden, musts)
        return available, forbidden, musts

    def available_for(self, role: str) -> list[ActionInst]:
        return self._readings(role)[0]

    def forbidden_for(self, role: str) -> list[ActionInst]:
        return list(self._readings(role)[1])

    def forbidding_rules(self, role: str) -> dict[ActionInst, list[str]]:
        return self._readings(role)[1]

    def obligations_for(self, role: str) -> list[ActionInst]:
        return list(self._readings(role)[2])

    def obligation_rules(self, role: str) -> dict[ActionInst, list[str]]:
        return self._readings(role)[2]

    # ------------------------------------------------------------ step
    def step(self) -> None:
        self._cache = {}
        self.agents.do("snapshot")  # synchronous update: choices read last step's practices
        self.agents.shuffle_do("choose")
        fired = frozenset(a.chosen for a in self.agents if a.chosen is not None)
        self.agents.do("settle")
        self.state = self.ref.successor(self.state, fired)
        self._cache = {}  # readings are per state
        self.adoption.append(self.adoption_shares())
        self.breaches.append(self._role_rate(lambda a: bool(a.breached)))
        self.sanctioned.append(self._role_rate(lambda a: a.sanctioned))
        self.t += 1

    def _role_rate(self, pred) -> dict[str, float]:
        return {role: (sum(1 for a in members if pred(a)) / len(members)) if members else 0.0
                for role, members in self.by_role.items()}

    def adoption_shares(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for role, members in self.by_role.items():
            counts: dict[str, int] = {}
            for a in members:
                lab = action_label(a.practice)
                counts[lab] = counts.get(lab, 0) + 1
            out[role] = {k: counts[k] / len(members) for k in sorted(counts)} if members else {}
        return out

    def fluent_rates(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for f in self.inst.fluents:
            if f.name in self.ref.derived:
                tups = [tuple(f.arg_roles)] if f.arg_roles else list(itertools.product(self.ref.agents, repeat=f.arity))
            else:
                tups = self.ref.tuples.get(f.name, [])
            out[f.name] = (sum(1 for t in tups if self.ref.atom(self.state, f.name, t)) / len(tups)) if tups else 0.0
        return out

    def report(self) -> AbmReport:
        return AbmReport(institution=self.inst.id, seed=self.seed_value, modules=list(self.modules),
                         params=dict(self.params, payoffs=dict(self.payoffs)), steps=len(self.adoption),
                         agents_per_role=self.agents_per_role, roles=list(self.roles), adoption=list(self.adoption),
                         fluent_rates=self.fluent_rates(), breaches=list(self.breaches),
                         sanctioned=list(self.sanctioned), warnings=list(self.warnings))


def run_abm(inst: InstitutionJSON, seed: int = 0, steps: int = DEFAULT_STEPS,
            agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, modules=("material",),
            payoffs: dict[str, float] | None = None, params: dict | None = None) -> AbmReport:
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs, params=params)
    for _ in range(steps):
        m.step()
    return m.report()
