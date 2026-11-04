"""Independent brute-force reference semantics for InstitutionJSON (verifier for rules_lower / rules_checks).

Written from plans/institutions-phase0.md ("Rule format", "Checks", the schema-builder notes) and the dataset
README, NOT from rules_lower.py. Meant for tiny institutions only: it enumerates every compliant trace
explicitly (states = sets of true fluent tuples, at most one action per step in step_mode "one", any set of
enabled actions in "many"), so it is exponential in everything.

Semantics implemented (each line is a reading of the plan; where the plan is silent the choice is stated):
  agents      one per role, named after the role.
  tuples      a fluent with arg_roles has exactly one tuple (those roles' agents); untyped: every agent tuple.
  actions     parameters typed by arg_roles (by position), else by the unique non-literal role-name prefix, else
              any agent; a parameter equal to a role is that role's agent; arguments are pairwise distinct.
              attribute scoping: an action some rule names can only be performed by an agent whose role is the
              attribute of a rule on that action.
  rules       the aim's first argument is the attribute's agent; other aim variables are typed by
              Rule.var_roles, then the action's typing; condition variables not in the aim are existentially
              quantified over their type (var_roles / prefix heuristic / any agent).
  enabled     an action instance with at least one may/must rule instance is enabled at t iff some such rule
              instance's condition holds at t; an action no may/must rule names at all may always fire
              (but is never (enabled ...) in a derived fluent, see derived).
  compliant   must: C(t) => A fires at t.  must_not: C(t) => A does not fire at t (hard, strict compliance).
  state rules (rules_lower docstring, "ADR 0009") an aim whose head is a declared fluent F is a state obligation:
              must F when C means C(t) => F(t) at every step 0..k (must_not: C(t) => not F(t)); no action fires.
              The aim's variables are typed by var_roles, then the fluent's arg_roles, then the prefix heuristic;
              the attribute need not appear in the aim.
  frame       F(t+1) = true if some fired action sets it true, else false if some fired action sets it false,
              else F(t).  Effect arguments: parameter, literal role, or wildcard (every agent).
  init        "declared": all false, then defaults, then initial, initial_free fluents unconstrained;
              "empty": fluents touched by an effect are false, the rest unconstrained; "free": all unconstrained.
  verdicts    reachable/open, holds_to_k/violated, persists/fails; "inconsistent" when no compliant trace exists.
  derived     (plan: "can_exit derived from 'some exit action is enabled'"; ADR 0013) a fluent with `derived`
              is not part of the state: it is evaluated on demand from its expression with `params` bound to
              the arguments. (enabled a x ...) is true in a state iff (a, (x, ...)) is an action instance and
              some may/must rule instance on it has its condition true (an action no may/must rule names is
              never (enabled ...), though it may still fire freely: ADR 0013 amendment 2026-11-03) and no
              must_not rule with or_else null on that instance has its condition true. Derived fluents
              never appear in effects or the initial state; a trace that lists one is checked against the
              evaluation rather than the state.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from . import sexpr as sx
from .schemas_rules import InstitutionJSON, Property, TraceStep

_LIT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?$")


class RefError(ValueError):
    pass


def parse_literal(text: str) -> tuple[str, tuple[str, ...]]:
    t = text.strip()
    if t.startswith("("):
        a = sx.parse(t)
        if isinstance(a, sx.Sym):
            return a.name, ()
        if isinstance(a, sx.App):
            return a.pred, tuple(x.name for x in a.args)
        raise RefError(f"not a literal: {text!r}")
    m = _LIT.match(t)
    if not m:
        raise RefError(f"not a literal: {text!r}")
    args = tuple(x.strip() for x in m.group(2).split(",")) if m.group(2) and m.group(2).strip() else ()
    return m.group(1), args


@dataclass(frozen=True)
class RuleInst:
    rule_id: str
    deontic: str
    action: str
    args: tuple
    cond: object  # AST or None
    binding: dict
    free_doms: tuple  # ((name, (agents...)), ...)


class Reference:
    def __init__(self, inst: InstitutionJSON, k: int = 4, init: str | None = None, step_mode: str = "one"):
        self.inst = inst
        self.k = k
        self.step_mode = step_mode
        self.agents = [r.name for r in inst.roles]
        self.roles = set(self.agents)
        self.init = init or ("declared" if inst.declares_init() else "empty")
        self.fluents = {f.name: f for f in inst.fluents}
        self.actions = {a.name: a for a in inst.actions}
        self.derived: dict[str, tuple[list[str], object]] = {}  # name -> (params, AST)
        for f in inst.fluents:
            if f.derived is not None:
                if len(f.params or []) != f.arity:
                    raise RefError(f"derived fluent {f.name}: params/arity mismatch")
                self.derived[f.name] = (list(f.params or []), sx.parse(f.derived))
        for a in inst.actions:
            for e in a.effects:
                if e.fluent in self.derived:
                    raise RefError(f"action {a.name}: effect on derived fluent {e.fluent}")
        # fluent tuples
        self.tuples: dict[str, list[tuple]] = {}
        for f in inst.fluents:
            if f.name in self.derived:
                self.tuples[f.name] = []  # not state
                continue
            if f.arg_roles is None:
                self.tuples[f.name] = list(itertools.product(self.agents, repeat=f.arity))
            else:
                self.tuples[f.name] = [tuple(f.arg_roles)] if all(r in self.roles for r in f.arg_roles) else []
        self.all_atoms = {(n, tup) for n, ts in self.tuples.items() for tup in ts}
        # literal roles: role names used as action params or aim args
        self.lits: set[str] = set()
        for a in inst.actions:
            self.lits |= self.roles & set(a.args)
        for r in inst.rules:
            self.lits |= self.roles & {x.name for x in self._aim(r.aim).args}
        # rule instances
        self.rule_insts: list[RuleInst] = []
        named: dict[str, set[str]] = {}  # action -> attributes of rules naming it
        self.may_must_named: set[str] = set()
        self.state_rules: list[RuleInst] = []  # aim head is a fluent (state obligation)
        for r in inst.rules:
            aim = self._aim(r.aim)
            if aim.pred in self.fluents and aim.pred not in self.actions:
                if r.deontic == "may":
                    raise RefError(f"{r.id}: may on a fluent")
                if aim.pred in self.derived:
                    raise RefError(f"{r.id}: aim is a derived fluent")
                cond = None if r.conditions.strip() == "true" else sx.parse(r.conditions)
                names = [x.name for x in aim.args]
                types = self.aim_types(r)
                free = sorted(self._free_vars(cond) - set(names)) if cond is not None else []
                free_doms = []
                for v in free:
                    ty = r.var_roles.get(v) if v not in self.lits else None
                    if ty is None:
                        ty = self._var_role(v)
                    free_doms.append((v, (ty,) if ty else tuple(self.agents)))
                doms = [[types[n]] if types.get(n) else list(self.agents) for n in names]
                for tup in itertools.product(*doms):
                    b = dict(zip(names, tup))
                    self.state_rules.append(RuleInst(r.id, r.deontic, aim.pred, tuple(b[n] for n in names), cond, b,
                                                     tuple(free_doms)))
                continue
            if aim.pred not in self.actions:
                raise RefError(f"{r.id}: unknown action {aim.pred}")
            named.setdefault(aim.pred, set()).add(r.attribute)
            if r.deontic in ("may", "must"):
                self.may_must_named.add(aim.pred)
            cond = None if r.conditions.strip() == "true" else sx.parse(r.conditions)
            names = [x.name for x in aim.args]
            if len(names) != len(self.actions[aim.pred].args):
                raise RefError(f"{r.id}: aim arity")
            types = self.aim_types(r)
            free = sorted(self._free_vars(cond) - set(names)) if cond is not None else []
            free_doms = []
            for v in free:
                ty = r.var_roles.get(v) if v not in self.lits else None
                if ty is None:
                    ty = self._var_role(v)
                free_doms.append((v, (ty,) if ty else tuple(self.agents)))
            for b in self._bindings(names, types):
                self.rule_insts.append(RuleInst(r.id, r.deontic, aim.pred, tuple(b[n] for n in names), cond, b,
                                                tuple(free_doms)))
        # action instances (typed, distinct, attribute-scoped)
        self.action_insts: list[tuple[str, tuple]] = []
        for a in inst.actions:
            atypes = self._action_types(a)
            for b in self._bindings(a.args, atypes):
                args = tuple(b[p] for p in a.args)
                if a.name in named and (not args or args[0] not in named[a.name]):
                    continue
                self.action_insts.append((a.name, args))
        self.action_inst_set = set(self.action_insts)  # membership tests in power / compliant_step
        self.rules_on: dict[tuple, list[RuleInst]] = {}
        for ri in self.rule_insts:
            self.rules_on.setdefault((ri.action, ri.args), []).append(ri)
        self.disabilities = {r.id for r in inst.rules if r.deontic == "must_not" and r.or_else is None}
        self._traces: list[tuple[frozenset, ...]] | None = None
        self._trace_actions: dict | None = None

    # ------------------------------------------------------------ typing helpers
    @staticmethod
    def _aim(text: str) -> sx.App:
        a = sx.parse(text)
        if not isinstance(a, sx.App):
            raise RefError(f"aim must be an application: {text!r}")
        return a

    def aim_types(self, r) -> dict[str, str | None]:
        """{aim argument name: role or None} for a rule's aim, the ONE typing of rule declarations (used for rule
        instances here and for A5 bearing in the ABM). Action aim: position 0 is the attribute; after it a literal
        role name > the rule's `var_roles` > the action's `arg_roles` (else its prefix heuristic). State aim
        (fluent head): literal role name > `var_roles` > the fluent's `arg_roles` > prefix heuristic."""
        aim = self._aim(r.aim)
        names = [x.name for x in aim.args]
        types: dict[str, str | None] = {}
        if aim.pred in self.fluents and aim.pred not in self.actions:
            fdecl = self.fluents[aim.pred]
            for i, n in enumerate(names):
                if n in self.roles:
                    types[n] = n
                elif n in r.var_roles:
                    types[n] = r.var_roles[n]
                elif fdecl.arg_roles is not None:
                    types[n] = fdecl.arg_roles[i]
                else:
                    types[n] = self._var_role(n)
            return types
        if aim.pred not in self.actions:
            raise RefError(f"{r.id}: unknown action {aim.pred}")
        atypes = self._action_types(self.actions[aim.pred])
        params = self.actions[aim.pred].args
        for i, n in enumerate(names):
            if i == 0:
                types[n] = r.attribute
            elif n in self.roles:
                types[n] = n
            elif n in r.var_roles:
                types[n] = r.var_roles[n]
            else:
                types[n] = atypes.get(params[i]) if i < len(params) else None
        return types

    def _var_role(self, name: str) -> str | None:
        if name in self.roles:
            return name
        c = [r for r in self.agents if r not in self.lits and r.startswith(name)]
        return c[0] if len(c) == 1 else None

    def _action_types(self, a) -> dict:
        out = {p: self._var_role(p) for p in a.args}
        for p, r in zip(a.args, a.arg_roles or []):
            if r is not None:
                out[p] = r
        return out

    def _bindings(self, names, types):
        doms = [[types[n]] if types.get(n) else list(self.agents) for n in names]
        for tup in itertools.product(*doms):
            if len(set(tup)) == len(tup):
                yield dict(zip(names, tup))

    @staticmethod
    def _free_vars(ast) -> set[str]:
        out: set[str] = set()

        def go(x, bound):
            if isinstance(x, sx.Sym):
                return
            if isinstance(x, sx.App):
                for a in x.args:
                    if a.name not in bound:
                        out.add(a.name)
            elif isinstance(x, sx.Not):
                go(x.arg, bound)
            elif isinstance(x, (sx.And, sx.Or)):
                for y in x.args:
                    go(y, bound)
            elif isinstance(x, (sx.Implies, sx.Iff)):
                go(x.left, bound); go(x.right, bound)
            elif isinstance(x, sx.Eq):
                for a in (x.left, x.right):
                    if a.name not in bound:
                        out.add(a.name)
            elif isinstance(x, sx.Quant):
                go(x.body, bound | {v for v, _ in x.vars})
        go(ast, set())
        return out

    # ------------------------------------------------------------ evaluation
    def holds(self, state: frozenset, ast, env: dict) -> bool:
        """State formula (rule condition) in a state."""
        def term(x):
            return env.get(x.name, x.name)

        def go(x):
            if isinstance(x, sx.Sym):
                return self.atom(state, x.name, ())
            if isinstance(x, sx.App):
                if x.pred == "enabled":
                    return self.power(state, x.args[0].name, tuple(term(a) for a in x.args[1:]))
                return self.atom(state, x.pred, tuple(term(a) for a in x.args))
            if isinstance(x, sx.Not):
                return not go(x.arg)
            if isinstance(x, sx.And):
                return all(go(y) for y in x.args)
            if isinstance(x, sx.Or):
                return any(go(y) for y in x.args)
            if isinstance(x, sx.Implies):
                return (not go(x.left)) or go(x.right)
            if isinstance(x, sx.Iff):
                return go(x.left) == go(x.right)
            if isinstance(x, sx.Eq):
                return term(x.left) == term(x.right)
            if isinstance(x, sx.Quant):
                names = [v for v, _ in x.vars]
                res = [self.holds(state, x.body, env | dict(zip(names, tup)))
                       for tup in itertools.product(*[list(self.agents)] * len(names))]
                return all(res) if x.kind == "forall" else any(res)
            raise TypeError(x)
        return go(ast)

    def atom(self, state: frozenset, name: str, args: tuple) -> bool:
        """A fluent application in a state: membership for a state fluent, evaluation for a derived one."""
        if name in self.derived:
            params, ast = self.derived[name]
            decl = self.fluents[name]
            if decl.arg_roles is not None and tuple(args) != tuple(decl.arg_roles):
                return False
            return self.holds(state, ast, dict(zip(params, args)))
        return (name, tuple(args)) in state

    def power(self, state: frozenset, action: str, args: tuple) -> bool:
        """(enabled action args): an action instance some may/must rule instance's condition grants and that no
        disability bars. Computed from the rule instances directly, not via `enabled` (whose unregulated floor is
        for firing, not for power: ADR 0013 amendment 2026-11-03)."""
        act = (action, tuple(args))
        if act not in self.action_inst_set:
            return False
        if not any(self.cond_holds(ri, state) for ri in self.rules_on.get(act, []) if ri.deontic in ("may", "must")):
            return False
        return not any(ri.deontic == "must_not" and ri.rule_id in self.disabilities and self.cond_holds(ri, state)
                       for ri in self.rules_on.get(act, []))

    def cond_holds(self, ri: RuleInst, state: frozenset) -> bool:
        if ri.cond is None:
            return True
        names = [n for n, _ in ri.free_doms]
        doms = [list(d) for _, d in ri.free_doms]
        return any(self.holds(state, ri.cond, ri.binding | dict(zip(names, tup))) for tup in itertools.product(*doms))

    def state_ok(self, state: frozenset) -> list[str]:
        """Reasons a state breaks a state obligation ([] = all state rules satisfied)."""
        bad = []
        for ri in self.state_rules:
            if not self.cond_holds(ri, state):
                continue
            holds = (ri.action, ri.args) in state
            if ri.deontic == "must" and not holds:
                bad.append(f"{ri.rule_id}: must {ri.action}{ri.args} does not hold")
            if ri.deontic == "must_not" and holds:
                bad.append(f"{ri.rule_id}: must_not {ri.action}{ri.args} holds")
        return bad

    def enabled(self, act: tuple, state: frozenset) -> bool:
        name, _ = act
        if name not in self.may_must_named:
            return True
        return any(self.cond_holds(ri, state) for ri in self.rules_on.get(act, []) if ri.deontic in ("may", "must"))

    def compliant_step(self, state: frozenset, fired: frozenset) -> list[str]:
        """Reasons the action set `fired` is not a compliant step from `state` ([] = compliant)."""
        bad = []
        if self.step_mode == "one" and len(fired) > 1:
            bad.append(f"{len(fired)} actions in one step")
        for a in fired:
            if a not in self.action_inst_set:
                bad.append(f"{a} is not an action instance")
            elif not self.enabled(a, state):
                bad.append(f"{a} not enabled")
        for ri in self.rule_insts:
            if ri.deontic == "must" and self.cond_holds(ri, state) and (ri.action, ri.args) not in fired:
                bad.append(f"{ri.rule_id}: must {ri.action}{ri.args} not fired")
            if ri.deontic == "must_not" and self.cond_holds(ri, state) and (ri.action, ri.args) in fired:
                bad.append(f"{ri.rule_id}: must_not {ri.action}{ri.args} fired")
        return bad

    def successor(self, state: frozenset, fired: frozenset) -> frozenset:
        set_true, set_false = set(), set()
        for name, args in fired:
            a = self.actions[name]
            env = dict(zip(a.args, args))
            for e in a.effects:
                doms = []
                for x in e.args:
                    if x in env:
                        doms.append([env[x]])
                    elif x in self.roles:
                        doms.append([x])
                    else:
                        doms.append(list(self.agents))
                for tup in itertools.product(*doms):
                    (set_true if e.value else set_false).add((e.fluent, tup))
        nxt = (set(state) - set_false) | set_true
        return frozenset(nxt & self.all_atoms)

    # ------------------------------------------------------------ enumeration
    def initial_split(self) -> tuple[set, set]:
        """(atoms true at t=0, atoms unconstrained at t=0); every other atom is false at t=0."""
        inst = self.inst
        if self.init == "free":
            fixed, free = set(), set(self.all_atoms)
        elif self.init == "empty":
            touched = {e.fluent for a in inst.actions for e in a.effects}
            fixed = set()
            free = {at for at in self.all_atoms if at[0] not in touched}
        else:
            fixed = set()
            for f, v in inst.defaults.items():
                if v == "true":
                    fixed |= {at for at in self.all_atoms if at[0] == f}
            for lit in inst.initial or []:
                n, args = parse_literal(lit)
                fixed.add((n, args))
            free = {at for at in self.all_atoms if at[0] in set(inst.initial_free)}
            fixed -= free
        return fixed, free

    def is_initial(self, state: frozenset) -> bool:
        fixed, free = self.initial_split()
        return fixed <= state and not (state - fixed - free)

    def initial_states(self) -> list[frozenset]:
        fixed, free = self.initial_split()
        free = sorted(free)
        out = []
        for bits in itertools.product([False, True], repeat=len(free)):
            s = set(fixed) | {at for at, b in zip(free, bits) if b}
            out.append(frozenset(s & self.all_atoms))
        return out

    def steps_from(self, state: frozenset):
        if self.step_mode == "one":
            cands = [frozenset()] + [frozenset([a]) for a in self.action_insts if self.enabled(a, state)]
        else:
            en = [a for a in self.action_insts if self.enabled(a, state)]
            cands = [frozenset(c) for n in range(len(en) + 1) for c in itertools.combinations(en, n)]
        return [c for c in cands if not self.compliant_step(state, c) and not self.state_ok(self.successor(state, c))]

    def traces(self) -> list[tuple[frozenset, ...]]:
        """All compliant traces as state sequences s_0..s_k (deduplicated)."""
        if self._traces is not None:
            return self._traces
        seen: set = set()
        out = []

        def go(prefix):
            if len(prefix) == self.k + 1:
                key = tuple(prefix)
                if key not in seen:
                    seen.add(key); out.append(key)
                return
            for fired in self.steps_from(prefix[-1]):
                go(prefix + [self.successor(prefix[-1], fired)])
        for s0 in self.initial_states():
            if not self.state_ok(s0):
                go([s0])
        self._traces = out
        return out

    # ------------------------------------------------------------ properties
    def prop(self, ast, trace, t: int, env: dict | None = None) -> bool:
        env = {"t": t} | (env or {})
        declared = set(self.fluents)

        def term(x):
            return env.get(x.name, x.name)

        def go(x):
            if isinstance(x, sx.Sym):
                return self.atom(trace[t], x.name, ()) if x.name in declared else False
            if isinstance(x, sx.App):
                if x.pred == "succ":
                    a, b = term(x.args[0]), term(x.args[1])
                    return isinstance(a, int) and isinstance(b, int) and b == a + 1
                if x.pred not in declared:
                    return False
                *aa, st = [term(a) for a in x.args]
                if not isinstance(st, int):
                    raise RefError(f"fluent {x.pred}: last argument {st!r} is not a step")
                if not 0 <= st <= self.k:
                    return False
                return self.atom(trace[st], x.pred, tuple(aa))
            if isinstance(x, sx.Not):
                return not go(x.arg)
            if isinstance(x, sx.And):
                return all(go(y) for y in x.args)
            if isinstance(x, sx.Or):
                return any(go(y) for y in x.args)
            if isinstance(x, sx.Implies):
                return (not go(x.left)) or go(x.right)
            if isinstance(x, sx.Iff):
                return go(x.left) == go(x.right)
            if isinstance(x, sx.Eq):
                return term(x.left) == term(x.right)
            if isinstance(x, sx.Quant):
                doms = [list(range(self.k + 1)) if s == "step" else list(self.agents) for _, s in x.vars]
                names = [v for v, _ in x.vars]
                res = [self.prop(x.body, trace, t, env | dict(zip(names, tup))) for tup in itertools.product(*doms)]
                return all(res) if x.kind == "forall" else any(res)
            raise TypeError(x)
        return go(ast)

    def verdict(self, p: Property, check: str) -> str:
        ast = sx.parse(p.formal)
        trs = self.traces()
        if not trs:
            return "inconsistent"
        K = range(self.k + 1)
        if check == "reachable":
            return "reachable" if any(self.prop(ast, tr, t) for tr in trs for t in K) else "open"
        if check == "invariant":
            return "violated" if any(not self.prop(ast, tr, t) for tr in trs for t in K) else "holds_to_k"
        if check == "persists":
            for tr in trs:
                vals = [self.prop(ast, tr, t) for t in K]
                if any(vals[t1] and not vals[t2] for t1 in K for t2 in K if t2 > t1):
                    return "fails"
            return "persists"
        raise RefError(check)

    # ------------------------------------------------------------ replay
    def replay(self, trace: list[TraceStep], p: Property | None = None, check: str | None = None) -> list[str]:
        """Check an engine counterexample trace step by step. Returns problems ([] = the trace is a compliant
        trace, its fluents match our successor function, property_holds matches our evaluation, and the
        property holds/fails as the check claims)."""
        bad: list[str] = []
        if len(trace) != self.k + 1:
            return [f"trace has {len(trace)} steps, expected k+1={self.k + 1}"]
        states = []
        derived_claims = []  # (step, name, args) the trace lists as true
        for st in trace:
            s = set()
            for f in st.fluents:
                if f.startswith("violated_"):
                    bad.append(f"step {st.step}: sanction fluent {f} in a strict trace")
                    continue
                n, args = parse_literal(f)
                if n in self.derived:
                    derived_claims.append((st.step, n, args))
                    continue
                if (n, args) not in self.all_atoms:
                    bad.append(f"step {st.step}: {f} is not a declared fluent tuple")
                s.add((n, args))
            states.append(frozenset(s))
        for t, n, args in derived_claims:
            if not self.atom(states[t], n, args):
                bad.append(f"step {t}: trace lists derived {n}{args} but it does not follow from the rules")
        for t, st in enumerate(states):
            for n in self.derived:
                decl = self.fluents[n]
                tups = [tuple(decl.arg_roles)] if decl.arg_roles else list(itertools.product(self.agents, repeat=decl.arity))
                for tup in tups:
                    if self.atom(st, n, tup) and (t, n, tup) not in derived_claims:
                        bad.append(f"step {t}: derived {n}{tup} follows from the rules but the trace omits it")
        for t, st in enumerate(states):
            for why in self.state_ok(st):
                bad.append(f"step {t}: {why}")
        if not self.is_initial(states[0]):
            bad.append(f"step 0: {sorted(states[0])} is not a valid initial state under init={self.init}")
        for t in range(self.k):
            fired = frozenset(parse_literal(a) for a in trace[t].actions)
            for why in self.compliant_step(states[t], fired):
                bad.append(f"step {t}: {why}")
            nxt = self.successor(states[t], fired)
            if nxt != states[t + 1]:
                bad.append(f"step {t + 1}: fluents differ from frame+effects: extra={sorted(states[t + 1] - nxt)} "
                           f"missing={sorted(nxt - states[t + 1])}")
        if trace[self.k].actions:
            bad.append(f"step {self.k}: actions fired at the last step")
        if p is not None:
            ast = sx.parse(p.formal)
            vals = [self.prop(ast, states, t) for t in range(self.k + 1)]
            for t, st in enumerate(trace):
                if st.property_holds is not None and st.property_holds != vals[t]:
                    bad.append(f"step {t}: property_holds={st.property_holds} but reference evaluates {vals[t]}")
            if check == "reachable" and not any(vals):
                bad.append("reachable: property holds at no step of the trace")
            if check == "invariant" and all(vals):
                bad.append("violated: property holds at every step of the trace")
            if check == "persists" and not any(vals[a] and not vals[b] for a in range(self.k + 1) for b in range(a + 1, self.k + 1)):
                bad.append("fails: property never holds-then-stops-holding in the trace")
        return bad
