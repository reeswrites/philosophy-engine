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
  state_obligations_for(role)  (A8, ADR 0015 amendment 2026-11-04; ADR 0009 must-be) fluent atoms P of `must-be P
                        when C` rule instances whose attribute is the role and whose C holds now
                        (`state_obligation_rules` gives the rule ids). `state_breaches(role, a)` lists the atoms
                        (and rule ids) that choosing `a` (or None) breaches: P is false in
                        `Reference.successor(state, {a})`. So if P already holds, any action not clearing it
                        keeps it; if P is false, only an action setting it true keeps it. The reading is LOCAL:
                        the current shared state plus this agent's own action; other agents' same-step actions
                        are not seen (state is role-level and shared, ADR 0015 A2 deferred). Strict enabledness
                        (ADR 0013) stands: an obliged agent keeps P only through actions available to it; when P
                        is false and no available action sets it, the breach is unavoidable and reported once
                        per run in `warnings` (encoder diagnostic). A `must_not` state rule (must-not-be) is read
                        symmetrically, breached iff P is true in the successor (ASSUMED).
  bears_on(o, me, actor)  A5: an obligation (action instance or fluent atom) bears on role `me` iff `me` is among
                        the aim's DECLARED argument roles other than the actor's: the action's `arg_roles` for
                        positions after the actor, the fluent's `arg_roles` for a must-be, each as the reference
                        types them (declared `arg_roles`, else a literal role name, else the rule's `var_roles`,
                        else the prefix heuristic; ASSUMED fallback), never the instance's values.
  no lawful action      (slice-2 review item d) when musts in force on a role leave no lawful option (two musts on
                        different actions, a must on a forbidden action, a must-be no action can keep together
                        with another must), the readings record it and `warnings` reports it once per run naming
                        the rule ids as an inconsistent encoding; the agents then choose among every available
                        action (never a crash).
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
    "sanction_weight": 1.0,  # A4: per-step charge while sanctioned for breaching a rule with or_else
    "sanction_steps": 3,  # A4: steps an agent stays sanctioned after a breach; expected sanction = weight * steps
    "sanction_escalation": 1.5,  # A4: graduated multiplier on the per-step charge per prior breach
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
        self._attribute = {r.id: r.attribute for r in inst.rules}
        self._action_names = {a.name for a in inst.actions}
        self._bears: dict[str, frozenset[str]] = {}  # rule id -> declared argument roles other than the actor's
        self._must_rules_by_head_attr: dict[tuple[str, str], list[str]] = {}  # (aim head, attribute) -> must ids
        for r in inst.rules:
            self._bears[r.id] = self._declared_bearing_roles(r)
            if r.deontic in ("must", "must_not"):
                head = self.ref._aim(r.aim).pred
                self._must_rules_by_head_attr.setdefault((head, r.attribute), []).append(r.id)
        # state rules by attribute role (A8): the reference instantiates them without the attribute in the args
        self._state_rules_by_role: dict[str, list] = {r: [] for r in self.ref.agents}
        for ri in self.ref.state_rules:
            if ri.deontic in ("must", "must_not"):
                self._state_rules_by_role.setdefault(self._attribute[ri.rule_id], []).append(ri)
        self.unavoidable: dict[str, tuple[str, int, int]] = {}  # rule id -> (role, first step, steps)
        self.no_lawful: dict[tuple[str, tuple[str, ...]], tuple[int, int]] = {}  # (role, rule ids) -> (first, n)
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

    def _declared_bearing_roles(self, rule) -> frozenset[str]:
        """A5: the aim's declared argument roles other than the actor's (the rule's attribute), typed as the
        reference types declarations (arg_roles, literal role name, var_roles, prefix); never instance values."""
        aim = self.ref._aim(rule.aim)
        names = [x.name for x in aim.args]
        roles: list[str | None] = []
        if aim.pred in self.ref.actions:
            atypes = self.ref._action_types(self.ref.actions[aim.pred])
            params = self.ref.actions[aim.pred].args
            for i, n in enumerate(names[1:], start=1):
                if n in self.ref.roles:
                    roles.append(n)
                elif n in rule.var_roles:
                    roles.append(rule.var_roles[n])
                else:
                    roles.append(atypes.get(params[i]) if i < len(params) else None)
        elif aim.pred in self.ref.fluents:
            fdecl = self.ref.fluents[aim.pred]
            for i, n in enumerate(names):
                if fdecl.arg_roles is not None and i < len(fdecl.arg_roles):
                    roles.append(fdecl.arg_roles[i])
                elif n in self.ref.roles:
                    roles.append(n)
                elif n in rule.var_roles:
                    roles.append(rule.var_roles[n])
                else:
                    roles.append(self.ref._var_role(n))
        return frozenset(r for r in roles if r is not None and r != rule.attribute)

    def bears_on(self, obligation: tuple, me: str, actor: str) -> bool:
        """Does an obligation (action instance or fluent atom) held by an agent of role `actor` bear on role `me`?
        Static: resolved through every must rule with that attribute on that aim head, from declared argument
        roles (A5), independent of which rule is in force now."""
        rids = self._must_rules_by_head_attr.get((obligation[0], actor), ())
        return any(me in self._bears.get(r, frozenset()) for r in rids)

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

    def _readings(self, role: str) -> tuple[list[ActionInst], dict[ActionInst, list[str]], dict[ActionInst, list[str]],
                                            dict[tuple, list[str]], dict[tuple, list[str]]]:
        """(available, {forbidden act: must_not rule ids}, {obligation act: must rule ids},
        {must-be atom: rule ids}, {must-not-be atom: rule ids}) for a role in the current state; cached per state.
        Also records, once per (role, state) and so once per step, the two encoder diagnostics: a state obligation
        no available action can keep (unavoidable breach) and musts that leave no lawful option (conflict)."""
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
        must_be: dict[tuple, list[str]] = {}
        must_not_be: dict[tuple, list[str]] = {}
        for ri in self._state_rules_by_role.get(role, []):
            if not self.ref.cond_holds(ri, self.state):
                continue
            if ri.deontic == "must":
                must_be.setdefault((ri.action, ri.args), []).append(ri.rule_id)
            elif self.sanctionable(ri.rule_id):
                must_not_be.setdefault((ri.action, ri.args), []).append(ri.rule_id)
        self._cache[role] = (available, forbidden, musts, must_be, must_not_be)
        self._diagnose(role, available, forbidden, musts, must_be, must_not_be)
        return self._cache[role]

    def _diagnose(self, role, available, forbidden, musts, must_be, must_not_be) -> None:
        if not (musts or must_be or must_not_be):
            return
        options: list[ActionInst | None] = [None, *available]
        # keep-set of every obligation in force: the options that keep it
        keep: dict[str, set] = {}
        for act, rids in musts.items():
            for r in rids:
                keep.setdefault(r, set()).add(act)
        state_rule_ids = [r for rids in (*must_be.values(), *must_not_be.values()) for r in rids]
        for o in options:
            broken = {r for rs in self.state_breaches(role, o).values() for r in rs}
            for r in state_rule_ids:
                keep.setdefault(r, set())
                if r not in broken:
                    keep[r].add(o)
        unavoidable = False
        for r in (r for rids in must_be.values() for r in rids):
            if not keep[r]:
                unavoidable = True
                rl, first, n = self.unavoidable.get(r, (role, self.t, 0))
                self.unavoidable[r] = (rl, first, n + 1)
        if unavoidable:
            return  # not a conflict between rules: one rule alone cannot be kept
        lawful = [o for o in options if all(o in s for s in keep.values()) and o not in forbidden]
        if not lawful:
            ids = tuple(sorted(set(keep) | {r for o in options if o in forbidden for r in forbidden[o]}))
            first, n = self.no_lawful.get((role, ids), (self.t, 0))
            self.no_lawful[(role, ids)] = (first, n + 1)

    def diagnostics(self) -> list[str]:
        """Once-per-run encoder warnings (A8 unavoidable breaches, item-d conflicting musts), from the counters."""
        out = []
        for r, (role, first, n) in sorted(self.unavoidable.items()):
            out.append(f"unavoidable breach: {r} (must-be, role {role}) could not be kept by any available action on "
                       f"{n} step(s), first at step {first}: no available action establishes the fluent")
        for (role, ids), (first, n) in sorted(self.no_lawful.items()):
            out.append(f"inconsistent encoding: rules {', '.join(ids)} leave role {role} no lawful action on {n} "
                       f"step(s), first at step {first}")
        return out

    def state_obligations_for(self, role: str) -> list[tuple]:
        return list(self._readings(role)[3])

    def state_obligation_rules(self, role: str) -> dict[tuple, list[str]]:
        return self._readings(role)[3]

    def state_breaches(self, role: str, a: ActionInst | None) -> dict[tuple, list[str]]:
        """{fluent atom: rule ids} of the state obligations on `role` that choosing `a` (None = nothing) breaches:
        must-be atoms false, must-not-be atoms true, in the reference successor of the current state under `a`
        alone (local reading, see the module docstring)."""
        key = ("_sb", role, a)
        if key in self._cache:
            return self._cache[key]
        must_be, must_not_be = self._readings(role)[3], self._readings(role)[4]
        out: dict[tuple, list[str]] = {}
        if must_be or must_not_be:
            succ = self.ref.successor(self.state, frozenset([a]) if a is not None else frozenset())
            for atom, rids in must_be.items():
                if atom not in succ:
                    out[atom] = list(rids)
            for atom, rids in must_not_be.items():
                if atom in succ:
                    out.setdefault(atom, []).extend(rids)
        self._cache[key] = out
        return out

    def keeps(self, role: str, a: ActionInst | None) -> bool:
        """Does choosing `a` keep every state obligation on `role` now?"""
        return not self.state_breaches(role, a)

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
                         sanctioned=list(self.sanctioned), warnings=list(self.warnings) + self.diagnostics())


def run_abm(inst: InstitutionJSON, seed: int = 0, steps: int = DEFAULT_STEPS,
            agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, modules=("material",),
            payoffs: dict[str, float] | None = None, params: dict | None = None) -> AbmReport:
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs, params=params)
    for _ in range(steps):
        m.step()
    return m.report()
