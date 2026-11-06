"""InstitutionJSON -> validated rule set -> bounded unrolling in z3 (plan: bounded model checking, k = 6).

Encoding (fully grounded over a finite agent domain, so z3 sees no quantifiers):
  agents        one agent per role, named after the role (the finite `agent` sort of properties.json).
  steps         0..k; fluents get a Bool per (fluent, args, t), actions a Bool per (action, args, t), t < k.
  frame axioms  F(args, t+1) <-> (some firing action at t sets it true) or (F(args, t) and no firing action sets it false).
  init          "empty": fluents touched by some effect are false at t=0, exogenous fluents (never in an effect) are
                free at t=0 and persist; "free": every fluent is free at t=0; "declared": every fluent is false at
                t=0 except as the institution says: `defaults` (fluent -> true/false for every tuple), then
                `initial` (literals true at t=0), then `initial_free` (fluents left unconstrained). init=None
                resolves to "declared" when the institution has any of the three fields, else "empty"
                (resolve_init). "empty" and "free" ignore the three fields (legacy modes).
  variables     the attribute binds the aim's first argument; a name equal to a role is that role's agent; any other
                variable is typed by ActionDecl.arg_roles (by position), Rule.var_roles (by name), or else the
                rules_lower.var_role heuristic (unique role-name prefix), or ranges over all agents (warning);
                an action's arguments denote pairwise distinct agents. Free variables of a condition that are
                not in the aim are existentially quantified over the domain (they may coincide with an aim
                argument; no distinctness).
  arg_roles     a fluent with arg_roles only has variables for tuples of those roles' agents; any other tuple is
                constant false (birthing_parent(non_birthing_parent) cannot be satisfied).
  attribute     scoping: an action named by any rule's aim can only be performed by an agent whose role is the
                attribute of some rule on that action (the actor is the aim's first argument); plan cannot
                `transfer_reserved` when only non_birthing_parent rules mention it. An action no rule names keeps
                every typed instance.
  step_mode     "one" (default): at most one action fires per step (interleaving semantics; feed and transfer cannot
                land in the same step). "many": any set of enabled actions may fire together (pre-existing).
  deontics      may A when C: A enabled at t if C(t). must A when C: enabled, and compliant traces have C(t) => A(t).
                must_not A when C: compliant traces have C(t) => not A(t). An action with no may/must rule is always
                enabled (a must_not alone prunes an otherwise free action).
  aim_kind      (ADR 0009) an aim whose head is a declared fluent is a state obligation: must F when C lowers to
                C(t) => F(t) at every step 0..k (must_not: C(t) => not F(t)); no action fires, nothing counts toward
                the one-action-per-step limit, and a breach (C and not F) sets violated_<rule> like any other.
                `may` on a fluent is an error. The aim's variables are typed by the fluent's arg_roles, var_roles or
                the prefix heuristic; the attribute is the bearer and need not appear in the aim.
                compliance="strict" (default): every must/must_not is a hard constraint (checks are over compliant
                traces, as the plan says). compliance="sanctioned": a rule with or_else may be broken; a breach at t
                sets the sanction fluent violated_<rule>(t+1) which enables the or_else rule's action at t+1 whatever
                its condition. Disabilities (must_not with or_else null) are hard in both modes (dataset README).
  derived       (ADR 0013) FluentDecl.derived defines a fluent from rule enabledness instead of effects:
                D(args, t) <-> expr[params := args] at every step, where expr ranges over (enabled ACTION x ...)
                and other fluents (schemas_rules module doc has the grammar). (enabled a x y) at t is true iff
                (a x y) is an action instance (typed, attribute-scoped) and some may/must rule instance on it has
                its condition true at t and no must_not disability (or_else null) on it does; an action no
                may/must rule names is NOT enabled (constant false; a warning flags the reference, since the
                action can still fire freely in traces: the trace floor and the rule-granted power are different
                questions, ADR 0013 amendment 2026-11-03), UNLESS the action is declared `default_capacity: true`
                (ADR 0013 amendment 2026-11-05; default capacity vs power): a default-capacity action is enabled at t iff no
                disability on that instance has its condition true, whether or not any may/must names it (a
                may/must on it is redundant for enablement). Default capacity affects only (enabled ...) in derived
                fluents, never which actions may fire in traces. A derived fluent gets a Bool per (args, t)
                defined by an equation, no frame axiom, no init, and cannot appear in effects / initial /
                defaults / initial_free / a rule's aim (validation error); cycles through derived fluents or rule
                conditions are errors. Power fluents (can_sanction, has_standing) are meant to be derived.
  obliged       (ADR 0013 amendment "derived obligation fluents"; plans/priority-slice2.md revision 3, R3.2) inside a
                derived definition only, like `enabled`: (obliged AIM x ...) at t is true iff (AIM x ...) is an
                instance (an action instance, typed and attribute-scoped; or a fluent tuple inside arg_roles) and
                some rule instance with deontic `must` on that aim and those args has its condition true at t
                (free condition variables existential, as cond_at). AIM is a declared action (must-do) or a declared
                non-derived fluent (must-be). Sanctioned and unsanctioned musts count alike (or_else plays no part);
                `may` and `must_not` never oblige, and a disability on the same instance does not cancel it (a
                deontic conflict, reported by the conflict check). Independent of default_capacity and of the
                compliance mode (it reads the rule set and the state). A warning flags an aim no `must` names
                (constant false). `enabled` and `obliged` in a property formula or a rule condition are errors.
  `true`        accepted as a bare condition in the rules path (sexpr.py still forbids it inside formulas).
  effects       an effect argument that is neither an action parameter nor a role is a wildcard (applies to all agents).
Properties (properties.json) are state formulas with `t` free: fluent applications carry the step last,
`succ(t, t2)` means t2 = t + 1, quantifiers over `agent` / `step` expand over the finite domains.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import z3

from . import sexpr as sx
from .schemas_rules import ActionDecl, InstitutionJSON, Property, Rule, TraceStep

DEFAULT_K = 6
TRUE_WORDS = ("true",)
PSEUDO = ("enabled", "obliged")  # pseudo-predicates over the rules, admitted only inside a derived definition (ADR 0013)


class LowerError(ValueError):
    pass


_LITERAL = __import__("re").compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?$")


# ---------------------------------------------------------------- validation
def parse_condition(text: str):
    """Rule condition -> AST or None (for the bare `true` the plan's examples use)."""
    if text.strip() in TRUE_WORDS:
        return None
    return sx.parse(text)


def parse_aim(text: str) -> sx.App:
    a = sx.parse(text)
    if not isinstance(a, sx.App):
        raise sx.ParseError(f"aim must be an action application, got {text!r}")
    return a


def regulated_actions(inst: InstitutionJSON, kinds: dict[str, str] | None = None) -> set[str]:
    """Actions some may/must rule names; every other action is unregulated (always enabled, never (enabled ...))."""
    return {parse_aim(r.aim).pred for r in inst.rules
            if r.deontic in ("may", "must") and (kinds[r.id] if kinds else aim_kind(r, inst)) == "action"}


def aim_kind(r: Rule, inst: InstitutionJSON) -> str:
    """"action" or "state" (ADR 0009): declared or inferred from the aim's head. Raises LowerError when the head
    is neither a declared action nor a declared fluent, both, or contradicts an explicit aim_kind."""
    head = parse_aim(r.aim).pred
    is_act = any(a.name == head for a in inst.actions)
    is_fl = any(f.name == head for f in inst.fluents)
    if is_act and is_fl:
        raise LowerError(f"{r.id}: aim head {head!r} is both a declared action and a declared fluent")
    if not is_act and not is_fl:
        raise LowerError(f"{r.id}: aim names undeclared action {head!r} (and no fluent of that name either)")
    kind = "action" if is_act else "state"
    if r.aim_kind is not None and r.aim_kind != kind:
        raise LowerError(f"{r.id}: aim_kind is {r.aim_kind!r} but the aim head {head!r} is a declared {kind}")
    return kind


def parse_literal(text: str) -> tuple[str, tuple[str, ...]]:
    """Initial-state literal -> (fluent, args). Accepts "f(a, b)", "(f a b)" and bare "f"."""
    t = text.strip()
    if t.startswith("("):
        a = sx.parse(t)
        if isinstance(a, sx.Sym):
            return a.name, ()
        if isinstance(a, sx.App):
            return a.pred, tuple(x.name for x in a.args)
        raise sx.ParseError(f"initial literal must be a fluent application, got {text!r}")
    m = _LITERAL.match(t)
    if not m:
        raise sx.ParseError(f"initial literal {text!r}: expected fluent(agent, ...)")
    args = tuple(x.strip() for x in m.group(2).split(",") if x.strip()) if m.group(2) is not None else ()
    return m.group(1), args


INIT_MODES = ("empty", "free", "declared")
STEP_MODES = ("one", "many")


def resolve_init(inst: InstitutionJSON, init: str | None) -> str:
    """None -> "declared" when the institution declares defaults/initial/initial_free, else "empty"."""
    if init is None:
        return "declared" if inst.declares_init() else "empty"
    if init not in INIT_MODES:
        raise LowerError(f"init={init!r}: unknown mode (one of {INIT_MODES})")
    return init


def literal_roles(inst: InstitutionJSON) -> set[str]:
    """Roles used literally as action/rule arguments (plan, court, state): never a variable's type by prefix."""
    roles = {r.name for r in inst.roles}
    lit = set()
    for a in inst.actions:
        lit |= roles & set(a.args)
    for r in inst.rules:
        try:
            lit |= roles & {t.name for t in parse_aim(r.aim).args}
        except sx.ParseError:
            pass
    return lit


def _rule_kinds(inst: InstitutionJSON) -> dict[str, str]:
    return {r.id: aim_kind(r, inst) for r in inst.rules}


def var_role(name: str, inst: InstitutionJSON, lits: set[str] | None = None) -> str | None:
    """Heuristic typing of a rule/action variable: a literal role is itself; otherwise the unique non-literal role
    whose name starts with the variable (h -> husband, o -> officer, c -> child when court is literal); else None."""
    roles = [r.name for r in inst.roles]
    if name in roles:
        return name
    lits = literal_roles(inst) if lits is None else lits
    cands = [r for r in roles if r not in lits and r.startswith(name)]
    return cands[0] if len(cands) == 1 else None


def _free_vars(ast) -> set[str]:
    out: set[str] = set()

    def go(x, bound):
        if isinstance(x, sx.Sym):
            if x.name not in bound:
                out.add(x.name)
        elif isinstance(x, sx.App):
            for t in x.args:
                if t.name not in bound:
                    out.add(t.name)
        elif isinstance(x, sx.Not):
            go(x.arg, bound)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y, bound)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left, bound); go(x.right, bound)
        elif isinstance(x, sx.Eq):
            for t in (x.left, x.right):
                if t.name not in bound:
                    out.add(t.name)
        elif isinstance(x, sx.Quant):
            go(x.body, bound | {v for v, _ in x.vars})

    go(ast, frozenset())
    return out


def validate_institution(inst: InstitutionJSON) -> list[str]:
    """Readable errors; [] means the institution lowers."""
    errs: list[str] = []
    roles = {r.name for r in inst.roles}
    if len(roles) != len(inst.roles):
        errs.append("duplicate role names")
    fl = {f.name: f.arity for f in inst.fluents}
    if len(fl) != len(inst.fluents):
        errs.append("duplicate fluent names")
    derived = {f.name for f in inst.fluents if f.derived is not None}
    for f in inst.fluents:
        if not sx.IDENT.match(f.name) or f.name in sx.RESERVED or f.name in PSEUDO:
            errs.append(f"invalid fluent name {f.name!r}")
        if f.arg_roles is not None:
            if len(f.arg_roles) != f.arity:
                errs.append(f"fluent {f.name}: arg_roles has {len(f.arg_roles)} entries, arity is {f.arity}")
            for r in f.arg_roles:
                if r not in roles:
                    errs.append(f"fluent {f.name}: arg_roles names {r!r}, which is not a role")
    acts = {a.name: a for a in inst.actions}
    if len(acts) != len(inst.actions):
        errs.append("duplicate action names")
    for a in inst.actions:
        if len(set(a.args)) != len(a.args):
            errs.append(f"action {a.name}: duplicate parameter names {a.args}")
        if a.arg_roles is not None:
            if len(a.arg_roles) != len(a.args):
                errs.append(f"action {a.name}: arg_roles has {len(a.arg_roles)} entries, args has {len(a.args)}")
            for p, r in zip(a.args, a.arg_roles):
                if r is not None and r not in roles:
                    errs.append(f"action {a.name}: arg_roles types {p!r} as {r!r}, which is not a role")
                elif r is not None and p in roles and p != r:
                    errs.append(f"action {a.name}: literal role {p!r} typed as {r!r}")
        for e in a.effects:
            if e.fluent not in fl:
                errs.append(f"action {a.name}: effect on undeclared fluent {e.fluent!r}")
            elif e.fluent in derived:
                errs.append(f"action {a.name}: effect on derived fluent {e.fluent!r} (power is what the rules enable, "
                            f"never an asserted effect; ADR 0013)")
            elif fl[e.fluent] != len(e.args):
                errs.append(f"action {a.name}: effect {e.fluent} has arity {fl[e.fluent]}, got {len(e.args)}")
            # an effect argument that is neither a parameter nor a role is a wildcard: the effect applies to
            # every agent in that position (police-crisis leave(s) clears responding(o, s) for all o)
    ids = [r.id for r in inst.rules]
    if len(set(ids)) != len(ids):
        errs.append(f"duplicate rule ids {ids}")
    # initial state
    for name, _ in inst.defaults.items():
        if name not in fl:
            errs.append(f"defaults: undeclared fluent {name!r}")
        elif name in derived:
            errs.append(f"defaults: {name!r} is derived; it has no initial value")
    for name in inst.initial_free:
        if name not in fl:
            errs.append(f"initial_free: undeclared fluent {name!r}")
        elif name in derived:
            errs.append(f"initial_free: {name!r} is derived; it has no initial value")
    typed = {f.name: f.arg_roles for f in inst.fluents}
    for lit in inst.initial or []:
        try:
            name, args = parse_literal(lit)
        except sx.ParseError as e:
            errs.append(f"initial: {e}")
            continue
        if name not in fl:
            errs.append(f"initial {lit!r}: undeclared fluent {name!r}")
        elif name in derived:
            errs.append(f"initial {lit!r}: {name!r} is derived; it has no initial value")
        elif fl[name] != len(args):
            errs.append(f"initial {lit!r}: fluent {name!r} has arity {fl[name]}, got {len(args)} argument(s)")
        else:
            for i, (x, ro) in enumerate(zip(args, typed[name] or [None] * len(args))):
                if x not in roles:
                    errs.append(f"initial {lit!r}: {x!r} is not a role (agents are named after roles)")
                elif ro is not None and x != ro:
                    errs.append(f"initial {lit!r}: argument {i} must be of role {ro!r}, got {x!r}")
    for r in inst.rules:
        if r.attribute not in roles:
            errs.append(f"{r.id}: attribute {r.attribute!r} is not a role")
        for v, ro in r.var_roles.items():
            if ro not in roles:
                errs.append(f"{r.id}: var_roles types {v!r} as {ro!r}, which is not a role")
        if r.or_else is not None and r.or_else not in ids:
            errs.append(f"{r.id}: or_else {r.or_else!r} is not a rule id")
        try:
            aim = parse_aim(r.aim)
        except sx.ParseError as e:
            errs.append(f"{r.id}: aim parse error: {e}")
            continue
        try:
            kind = aim_kind(r, inst)
        except LowerError as e:
            errs.append(str(e))
            kind = None
        if kind is None:
            pass
        elif kind == "state":
            if r.deontic == "may":
                errs.append(f"{r.id}: `may` on a fluent ({aim.pred!r}) has no meaning; permissions are action-only (ADR 0009)")
            if aim.pred in derived:
                errs.append(f"{r.id}: aim {aim.pred!r} is a derived fluent; a state obligation needs a fluent effects can establish")
            if fl[aim.pred] != len(aim.args):
                errs.append(f"{r.id}: fluent {aim.pred} has arity {fl[aim.pred]}, aim gives {len(aim.args)}")
        else:
            a = acts[aim.pred]
            if len(a.args) != len(aim.args):
                errs.append(f"{r.id}: action {aim.pred} takes {len(a.args)} argument(s), aim gives {len(aim.args)}")
            first = aim.args[0].name if aim.args else None
            if first in roles and first != r.attribute:
                errs.append(f"{r.id}: aim's first argument {first!r} is a role but not the attribute {r.attribute!r}")
        try:
            cond = parse_condition(r.conditions)
        except sx.ParseError as e:
            errs.append(f"{r.id}: conditions parse error: {e}")
            continue
        if cond is not None:
            _check_state_formula(cond, fl, roles, errs, f"{r.id}: conditions", step_arg=False)
    errs.extend(validate_derived(inst))
    return errs


def _derived_asts(inst: InstitutionJSON) -> dict[str, object]:
    out = {}
    for f in inst.fluents:
        if f.derived is not None:
            out[f.name] = sx.parse(f.derived)
    return out


def _fluents_in(ast) -> set[str]:
    """Fluent names applied in a formula (the `enabled` and `obliged` pseudo-predicates excluded)."""
    out: set[str] = set()

    def go(x):
        if isinstance(x, sx.Sym):
            out.add(x.name)
        elif isinstance(x, sx.App):
            if x.pred not in PSEUDO:
                out.add(x.pred)
        elif isinstance(x, sx.Not):
            go(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left); go(x.right)
        elif isinstance(x, sx.Quant):
            go(x.body)

    go(ast)
    return out


def _enabled_actions(ast) -> set[str]:
    out: set[str] = set()

    def go(x):
        if isinstance(x, sx.App):
            if x.pred == "enabled" and x.args:
                out.add(x.args[0].name)
        elif isinstance(x, sx.Not):
            go(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left); go(x.right)
        elif isinstance(x, sx.Quant):
            go(x.body)

    go(ast)
    return out


def _obliged_aims(ast) -> set[str]:
    """Aims (actions or fluents) named by `(obliged AIM ...)` in a derived definition."""
    out: set[str] = set()

    def go(x):
        if isinstance(x, sx.App):
            if x.pred == "obliged" and x.args:
                out.add(x.args[0].name)
        elif isinstance(x, sx.Not):
            go(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left); go(x.right)
        elif isinstance(x, sx.Quant):
            go(x.body)

    go(ast)
    return out


def derived_dependencies(inst: InstitutionJSON) -> dict[str, set[str]]:
    """Derived fluent -> fluents its definition depends on, through its own expression, through the conditions of
    every may/must/must_not rule on each action it asks `enabled` of, and through the conditions of every `must`
    rule on each aim it asks `obliged` of (R3.2: a cycle through a must condition is an error)."""
    asts = _derived_asts(inst)
    deps: dict[str, set[str]] = {}
    for name, ast in asts.items():
        d = _fluents_in(ast)
        acts = _enabled_actions(ast)
        aims = _obliged_aims(ast)
        for r in inst.rules:
            try:
                head = parse_aim(r.aim).pred
                cond = parse_condition(r.conditions)
            except sx.ParseError:
                continue
            if cond is not None and (head in acts or (head in aims and r.deontic == "must")):
                d |= _fluents_in(cond)
        deps[name] = d
    return deps


def derived_order(inst: InstitutionJSON) -> list[str]:
    """Derived fluents in dependency order; raises LowerError on a cycle."""
    deps = derived_dependencies(inst)
    derived = set(deps)
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(n, path):
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            cyc = path[path.index(n):] + [n]
            raise LowerError(f"derived fluents are cyclic: {' -> '.join(cyc)}")
        state[n] = 1
        for m in sorted(deps[n] & derived):
            visit(m, path + [n])
        state[n] = 2
        order.append(n)

    for n in sorted(deps):
        visit(n, [])
    return order


def validate_derived(inst: InstitutionJSON) -> list[str]:
    """Derived-fluent declarations: params, grammar, references, cycles."""
    errs: list[str] = []
    roles = {r.name for r in inst.roles}
    fl = {f.name: f.arity for f in inst.fluents}
    acts = {a.name: a for a in inst.actions}
    for f in inst.fluents:
        if f.derived is None:
            if f.params is not None:
                errs.append(f"fluent {f.name}: params given but no `derived` expression")
            continue
        where = f"derived fluent {f.name}"
        params = f.params or []
        if len(params) != f.arity:
            errs.append(f"{where}: params has {len(params)} name(s), arity is {f.arity}")
            continue
        if len(set(params)) != len(params) or any(p in roles for p in params):
            errs.append(f"{where}: params must be distinct non-role names, got {params}")
            continue
        try:
            ast = sx.parse(f.derived)
        except sx.ParseError as e:
            errs.append(f"{where}: parse error: {e}")
            continue
        _check_derived_formula(ast, fl, acts, roles, set(params), errs, where, derived={
            x.name for x in inst.fluents if x.derived is not None})
    if not errs:
        try:
            derived_order(inst)
        except LowerError as e:
            errs.append(str(e))
    return errs


def _check_derived_formula(ast, fl: dict, acts: dict, roles: set, params: set, errs: list, where: str,
                           derived: set | None = None):
    derived = derived or set()

    def go(x, bound):
        if isinstance(x, sx.Sym):
            if x.name not in fl or fl[x.name] != 0:
                errs.append(f"{where}: {x.name!r} is not a 0-ary fluent")
        elif isinstance(x, sx.App):
            if x.pred == "obliged":  # R3.2: AIM is a declared action or a declared non-derived fluent
                if not x.args:
                    errs.append(f"{where}: (obliged AIM args...) needs an action or a fluent")
                    return
                aim = x.args[0].name
                if aim in acts:
                    n = len(acts[aim].args)
                elif aim in derived:
                    errs.append(f"{where}: (obliged {aim} ...): {aim!r} is a derived fluent; an obligation's aim is an "
                                "action or a fluent effects can establish (as for a rule's aim)")
                    return
                elif aim in fl:
                    n = fl[aim]
                else:
                    errs.append(f"{where}: (obliged {aim} ...): not a declared action or fluent")
                    return
                if n != len(x.args) - 1:
                    errs.append(f"{where}: (obliged {aim} ...): {aim!r} takes {n} argument(s), got {len(x.args) - 1}")
                terms = x.args[1:]
            elif x.pred == "enabled":
                if not x.args:
                    errs.append(f"{where}: (enabled ACTION args...) needs an action")
                    return
                a = acts.get(x.args[0].name)
                if a is None:
                    errs.append(f"{where}: (enabled {x.args[0].name} ...): not a declared action")
                    return
                if len(a.args) != len(x.args) - 1:
                    errs.append(f"{where}: (enabled {a.name} ...): action takes {len(a.args)} argument(s), got {len(x.args) - 1}")
                terms = x.args[1:]
            else:
                if x.pred not in fl:
                    errs.append(f"{where}: undeclared fluent {x.pred!r}")
                elif fl[x.pred] != len(x.args):
                    errs.append(f"{where}: fluent {x.pred!r} has arity {fl[x.pred]}, got {len(x.args)} argument(s)")
                terms = x.args
            for tm in terms:
                if tm.name not in bound and tm.name not in roles and tm.name not in params:
                    errs.append(f"{where}: {tm.name!r} is neither a param, a role nor a bound variable")
        elif isinstance(x, sx.Not):
            go(x.arg, bound)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y, bound)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left, bound); go(x.right, bound)
        elif isinstance(x, sx.Eq):
            for tm in (x.left, x.right):
                if tm.name not in bound and tm.name not in roles and tm.name not in params:
                    errs.append(f"{where}: {tm.name!r} is neither a param, a role nor a bound variable")
        elif isinstance(x, sx.Quant):
            for v, so in x.vars:
                if so != "agent":
                    errs.append(f"{where}: sort {so!r} is not agent (derived fluents are evaluated at one step)")
            go(x.body, bound | {v for v, _ in x.vars})

    go(ast, frozenset())


def _check_state_formula(ast, fl: dict, roles: set, errs: list, where: str, step_arg: bool):
    """Fluent names/arity; with step_arg the last argument of each application is a step term."""
    extra = 1 if step_arg else 0

    def go(x):
        if isinstance(x, sx.Sym):
            if x.name not in fl or fl[x.name] != 0:
                errs.append(f"{where}: {x.name!r} is not a 0-ary fluent")
        elif isinstance(x, sx.App):
            if x.pred in PSEUDO:  # ADR 0013 / R3.2: only inside a derived fluent's definition
                errs.append(f"{where}: ({x.pred} ...) is only available inside a derived fluent's definition; use the "
                            f"derived fluent that wraps it")
                return
            if x.pred == "succ" and step_arg:
                if len(x.args) != 2:
                    errs.append(f"{where}: (succ t t2) takes 2 arguments")
                return
            if x.pred not in fl:
                errs.append(f"{where}: undeclared fluent {x.pred!r}")
            elif fl[x.pred] + extra != len(x.args):
                errs.append(f"{where}: fluent {x.pred!r} has arity {fl[x.pred]}{' (+ step)' if step_arg else ''}, got {len(x.args)} argument(s)")
        elif isinstance(x, sx.Not):
            go(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for y in x.args:
                go(y)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            go(x.left); go(x.right)
        elif isinstance(x, sx.Eq):
            pass
        elif isinstance(x, sx.Quant):
            for v, s in x.vars:
                if s not in ("agent", "step"):
                    errs.append(f"{where}: sort {s!r} is not agent or step")
            go(x.body)

    go(ast)


def validate_property(p: Property, inst: InstitutionJSON) -> tuple[list[str], list[str]]:
    """(errors, warnings). Fluents the institution does not declare are a warning: they lower to constant false."""
    errs: list[str] = []
    warns: list[str] = []
    try:
        ast = sx.parse(p.formal)
    except sx.ParseError as e:
        return [f"property {p.name}: parse error: {e}"], []
    fl = {f.name: f.arity for f in inst.fluents}
    tmp: list[str] = []
    _check_state_formula(ast, fl, {r.name for r in inst.roles}, tmp, f"property {p.name}", step_arg=True)
    for m in tmp:
        if "undeclared fluent" in m:
            warns.append(m + " (lowered as constant false)")
        else:
            errs.append(m)
    free = _free_vars(ast) - {"t"} - {r.name for r in inst.roles}
    if free:
        errs.append(f"property {p.name}: free variables {sorted(free)} (only t may be free)")
    return errs, warns


# ------------------------------------------------------------------- lowering
@dataclass
class RuleInstance:
    rule: Rule
    action: str  # action name, or the fluent name for a state obligation (kind == "state")
    args: tuple  # agents
    cond: object  # z3-able AST or None; free condition vars already instantiated
    binding: dict
    kind: str = "action"  # "action" | "state" (ADR 0009)

    def aim_at(self, G: "Grounded", t: int):
        """The z3 Bool the deontic ranges over at step t: the action firing, or the fluent holding."""
        return G.fluent(self.action, self.args, t) if self.kind == "state" else G.action(self.action, self.args, t)


@dataclass
class Grounded:
    inst: InstitutionJSON
    k: int
    agents: list[str]
    init: str
    compliance: str
    step_mode: str = "one"
    fluent_vars: dict = field(default_factory=dict)  # (fluent, args, t) -> Bool
    action_vars: dict = field(default_factory=dict)  # (action, args, t) -> Bool
    violation_vars: dict = field(default_factory=dict)  # (rule id, t) -> Bool
    assertions: list = field(default_factory=list)  # (name, expr)
    action_instances: dict = field(default_factory=dict)  # action -> [args tuple]
    fluent_tuples: dict = field(default_factory=dict)  # fluent -> [args tuple] respecting arg_roles
    rule_instances: list = field(default_factory=list)  # RuleInstance
    exogenous: set = field(default_factory=set)
    warnings: list = field(default_factory=list)
    derived: dict = field(default_factory=dict)  # derived fluent name -> parsed definition
    derived_vars: dict = field(default_factory=dict)  # (fluent, args, t) -> Bool defined by an equation
    derived_defs: list = field(default_factory=list)  # (name, expr): the defining equations (also in assertions)
    cond_at: object = None  # set by ground(): (RuleInstance, t) -> z3 Bool
    regulated: set = field(default_factory=set)  # actions some may/must rule names (others fire freely but are never (enabled ...))

    def fluent(self, name: str, args: tuple, t: int):
        """The Bool for (fluent, args, t); constant false for a tuple outside the fluent's arg_roles.
        A derived fluent's Bool is created on first use and defined by its expression (ADR 0013)."""
        key = (name, tuple(args), t)
        v = self.fluent_vars.get(key)
        if v is None:
            if name in self.fluent_tuples and tuple(args) not in self.fluent_tuples[name]:
                return z3.BoolVal(False)
            if name in self.derived:
                return self._derived(name, tuple(args), t)
            return self.fluent_vars[key]  # KeyError: genuinely unknown
        return v

    def _derived(self, name: str, args: tuple, t: int):
        key = (name, args, t)
        v = self.derived_vars.get(key)
        if v is not None:
            return v
        v = z3.Bool(f"{name}({','.join(args)})@{t}")
        self.derived_vars[key] = v
        decl = next(f for f in self.inst.fluents if f.name == name)
        env = dict(zip(decl.params or [], args))
        defn = lower_state_formula(self.derived[name], self, t, env)
        self.derived_defs.append((f"derived:{name}@{t}", v == defn))
        self.assertions.append(self.derived_defs[-1])
        return v

    def obliged(self, aim: str, args: tuple, t: int):
        """(obliged aim args) at t (R3.2): (aim args) is an instance (an action instance, or a fluent tuple inside
        arg_roles) and some `must` rule instance on it has its condition true at t; action and state aims alike.
        `may` and `must_not` never oblige; or_else, default_capacity and the compliance mode play no part."""
        args = tuple(args)
        inst_ok = (args in self.action_instances[aim]) if aim in self.action_instances else (
            args in self.fluent_tuples.get(aim, []))
        if not inst_ok:
            return z3.BoolVal(False)
        on = [self.cond_at(ri, t) for ri in self.rule_instances
              if ri.action == aim and ri.args == args and ri.rule.deontic == "must"]
        return z3.Or(*on) if on else z3.BoolVal(False)

    def enabled(self, action: str, args: tuple, t: int):
        """(enabled action args) at t: some may/must rule instance's condition holds and no disability's does;
        constant false for a non-instance and for an action no may/must rule regulates (ADR 0013 amendment:
        a power is what the rules grant, and no rule grants an unregulated action). A `default_capacity` action
        (amendment 2026-11-05) is enabled unless a disability bars it, whatever may/must name it."""
        args = tuple(args)
        if args not in self.action_instances.get(action, []):
            return z3.BoolVal(False)
        default_capacity = next(a.default_capacity for a in self.inst.actions if a.name == action)
        ris = [ri for ri in self.rule_instances if ri.kind == "action" and ri.action == action and ri.args == args]
        on = [self.cond_at(ri, t) for ri in ris if ri.rule.deontic in ("may", "must")]
        off = [self.cond_at(ri, t) for ri in ris if ri.rule.deontic == "must_not" and ri.rule.or_else is None]
        en = z3.BoolVal(True) if default_capacity else (z3.Or(*on) if on else z3.BoolVal(False))
        return z3.And(en, z3.Not(z3.Or(*off))) if off else en

    def action(self, name: str, args: tuple, t: int):
        return self.action_vars[(name, tuple(args), t)]

    def system(self):
        """The whole unrolled system as one z3 expression."""
        return z3.And(*[e for _, e in self.assertions]) if self.assertions else z3.BoolVal(True)


def _typed_domains(names: list[str], types: dict, agents: list[str]):
    """All assignments of agents to names (pairwise distinct), respecting fixed/typed names."""
    doms = []
    for n in names:
        ty = types.get(n)
        doms.append([ty] if ty else list(agents))
    for tup in itertools.product(*doms):
        if len(set(tup)) == len(tup):
            yield dict(zip(names, tup))


def _action_types(a: ActionDecl, inst: InstitutionJSON, lits: set[str]) -> dict:
    """Parameter -> role: declared arg_roles first, else the prefix heuristic."""
    out = {p: var_role(p, inst, lits) for p in a.args}
    for p, r in zip(a.args, a.arg_roles or []):
        if r is not None:
            out[p] = r
    return out


def _fluent_tuples(f, agents: list[str]) -> list[tuple]:
    if f.arg_roles is None:
        return list(itertools.product(agents, repeat=f.arity))
    return [tuple(f.arg_roles)] if all(r in agents for r in f.arg_roles) else []


def _free_types(r: Rule, free: list[str], inst: InstitutionJSON, lits: set[str]) -> dict:
    """Free condition variable -> role: Rule.var_roles first, else the prefix heuristic (None = all agents)."""
    return {n: (r.var_roles[n] if n in r.var_roles and n not in lits else var_role(n, inst, lits)) for n in free}


def lower_state_formula(ast, G: Grounded, t: int, env: dict | None = None):
    """State formula (rule condition: no step arguments) at step t -> z3 Bool."""
    env = env or {}

    def term(x):
        return env.get(x.name, x.name)

    def go(x):
        if isinstance(x, sx.Sym):
            return G.fluent(x.name, (), t)
        if isinstance(x, sx.App):
            if x.pred == "enabled":
                return G.enabled(x.args[0].name, tuple(term(a) for a in x.args[1:]), t)
            if x.pred == "obliged":
                return G.obliged(x.args[0].name, tuple(term(a) for a in x.args[1:]), t)
            return G.fluent(x.pred, tuple(term(a) for a in x.args), t)
        if isinstance(x, sx.Not):
            return z3.Not(go(x.arg))
        if isinstance(x, sx.And):
            return z3.And(*[go(y) for y in x.args])
        if isinstance(x, sx.Or):
            return z3.Or(*[go(y) for y in x.args])
        if isinstance(x, sx.Implies):
            return z3.Implies(go(x.left), go(x.right))
        if isinstance(x, sx.Iff):
            return go(x.left) == go(x.right)
        if isinstance(x, sx.Eq):
            return z3.BoolVal(term(x.left) == term(x.right))
        if isinstance(x, sx.Quant):
            names = [v for v, _ in x.vars]
            parts = [lower_state_formula(x.body, G, t, env | b) for b in _typed_domains(names, {}, G.agents)]
            return (z3.And if x.kind == "forall" else z3.Or)(*parts) if parts else z3.BoolVal(x.kind == "forall")
        raise TypeError(x)

    return go(ast)


def lower_property(ast, G: Grounded, t: int, env: dict | None = None):
    """Property formula (t free, fluent applications carry the step last) at step t -> z3 Bool.
    Undeclared fluents are constant false (warning recorded by validate_property)."""
    env = {"t": t} | (env or {})
    declared = {f.name for f in G.inst.fluents}

    def term(x):
        return env.get(x.name, x.name)

    def go(x):
        if isinstance(x, sx.Sym):
            return G.fluent(x.name, (), t) if x.name in declared else z3.BoolVal(False)
        if isinstance(x, sx.App):
            if x.pred == "succ":
                a, b = term(x.args[0]), term(x.args[1])
                return z3.BoolVal(isinstance(a, int) and isinstance(b, int) and b == a + 1)
            if x.pred not in declared:
                return z3.BoolVal(False)
            *aa, st = [term(a) for a in x.args]
            if not isinstance(st, int):
                raise LowerError(f"fluent {x.pred}: last argument {st!r} is not a step")
            if not 0 <= st <= G.k:
                return z3.BoolVal(False)
            return G.fluent(x.pred, tuple(aa), st)
        if isinstance(x, sx.Not):
            return z3.Not(go(x.arg))
        if isinstance(x, sx.And):
            return z3.And(*[go(y) for y in x.args])
        if isinstance(x, sx.Or):
            return z3.Or(*[go(y) for y in x.args])
        if isinstance(x, sx.Implies):
            return z3.Implies(go(x.left), go(x.right))
        if isinstance(x, sx.Iff):
            return go(x.left) == go(x.right)
        if isinstance(x, sx.Eq):
            return z3.BoolVal(term(x.left) == term(x.right))
        if isinstance(x, sx.Quant):
            doms = [list(range(G.k + 1)) if s == "step" else list(G.agents) for _, s in x.vars]
            names = [v for v, _ in x.vars]
            parts = [lower_property(x.body, G, t, env | dict(zip(names, tup))) for tup in itertools.product(*doms)]
            return (z3.And if x.kind == "forall" else z3.Or)(*parts)
        raise TypeError(x)

    return go(ast)


def ground(inst: InstitutionJSON, k: int = DEFAULT_K, init: str | None = None, compliance: str = "strict",
           step_mode: str = "one") -> Grounded:
    """Build the unrolled system. Raises LowerError on validation failure. init=None resolves per resolve_init."""
    errs = validate_institution(inst)
    if errs:
        raise LowerError("\n".join(errs))
    init = resolve_init(inst, init)
    if compliance not in ("strict", "sanctioned"):
        raise LowerError(f"compliance={compliance!r}: unknown mode")
    if step_mode not in STEP_MODES:
        raise LowerError(f"step_mode={step_mode!r}: unknown mode (one of {STEP_MODES})")
    agents = [r.name for r in inst.roles]
    G = Grounded(inst, k, agents, init, compliance, step_mode)
    lits = literal_roles(inst)
    fl = {f.name: f.arity for f in inst.fluents}
    acts = {a.name: a for a in inst.actions}

    # variables
    G.derived = _derived_asts(inst)
    for f in inst.fluents:
        G.fluent_tuples[f.name] = _fluent_tuples(f, agents)
        if f.name in G.derived:
            continue  # defined by an equation on first use (ADR 0013)
        for tup in G.fluent_tuples[f.name]:
            for t in range(k + 1):
                G.fluent_vars[(f.name, tup, t)] = z3.Bool(f"{f.name}({','.join(tup)})@{t}")
    kinds = _rule_kinds(inst)
    actors: dict[str, set[str]] = {}  # action -> attributes of the rules that name it (attribute scoping)
    for r in inst.rules:
        if kinds[r.id] == "action":
            actors.setdefault(parse_aim(r.aim).pred, set()).add(r.attribute)
    for a in inst.actions:
        types = _action_types(a, inst, lits)
        G.action_instances[a.name] = [tuple(b[p] for p in a.args) for b in _typed_domains(a.args, types, agents)
                                      if not a.args or a.name not in actors or b[a.args[0]] in actors[a.name]]
        for tup in G.action_instances[a.name]:
            for t in range(k):
                G.action_vars[(a.name, tup, t)] = z3.Bool(f"{a.name}({','.join(tup)})@{t}")
    for r in inst.rules:
        for t in range(k + 1):
            G.violation_vars[(r.id, t)] = z3.Bool(f"violated_{r.id}@{t}")
    G.exogenous = set(fl) - {e.fluent for a in inst.actions for e in a.effects} - set(G.derived)

    # rule instances
    fls = {f.name: f for f in inst.fluents}
    for r in inst.rules:
        aim = parse_aim(r.aim)
        kind = kinds[r.id]
        cond = parse_condition(r.conditions)
        names = [x.name for x in aim.args]
        types = {n: var_role(n, inst, lits) for n in names}
        if kind == "state":  # positional typing from the fluent's arg_roles
            for n, ro in zip(names, fls[aim.pred].arg_roles or []):
                if ro is not None and n not in lits:
                    types[n] = ro
        else:
            act = acts[aim.pred]  # positional typing from the action's arg_roles
            for n, ro in zip(names, act.arg_roles or []):
                if ro is not None and n not in lits:
                    types[n] = ro
        for n in names:
            if n in r.var_roles and n not in lits:
                types[n] = r.var_roles[n]
        if kind == "action" and names and names[0] not in lits:
            types[names[0]] = r.attribute
        free = sorted((_free_vars(cond) if cond is not None else set()) - set(names))
        ftypes = _free_types(r, free, inst, lits)
        for b in _typed_domains(names, types, agents):
            tup = tuple(b[n] for n in names)
            if kind == "state":
                if tup not in G.fluent_tuples[aim.pred]:
                    continue
            elif tup not in G.action_instances.get(aim.pred, []):
                continue
            G.rule_instances.append(RuleInstance(r, aim.pred, tup, cond, b, kind))
        untyped_pos = names if kind == "state" else names[1:]
        if any(types[n] is None for n in untyped_pos) or any(v is None for v in ftypes.values()):
            G.warnings.append(f"{r.id}: untyped variable(s) {[n for n in untyped_pos if types[n] is None] + [n for n in free if ftypes[n] is None]} range over all agents")
    rules_by_id = {r.id: r for r in inst.rules}

    def cond_at(ri: RuleInstance, t: int):
        if ri.cond is None:
            return z3.BoolVal(True)
        free = sorted(_free_vars(ri.cond) - set(ri.binding))
        if not free:
            return lower_state_formula(ri.cond, G, t, ri.binding)
        ftypes = _free_types(ri.rule, free, inst, lits)
        # plain existential quantification over the domain: a free condition variable may name an agent that is
        # also an aim argument (clerk must log(c, s) when (flag q): q = s is a witness)
        parts = [lower_state_formula(ri.cond, G, t, ri.binding | fb) for fb in _typed_domains(free, ftypes, agents)]
        return z3.Or(*parts) if parts else z3.BoolVal(False)

    G.cond_at = cond_at
    # derived fluents: define every tuple at every step now, so the definitions are part of G.system() before
    # any property is lowered (derived_order has already rejected cycles)
    G.regulated = regulated_actions(inst, kinds)
    barred = {parse_aim(r.aim).pred for r in inst.rules if r.deontic == "must_not" and kinds[r.id] == "action"}
    for name in derived_order(inst):
        for a in sorted(_enabled_actions(G.derived[name])):
            if a not in G.regulated and not next(x.default_capacity for x in inst.actions if x.name == a):
                tail = "only a prohibition names it" if a in barred else "it can still fire freely in traces"
                G.warnings.append(f"derived fluent {name}: (enabled {a} ...) names an action no may/must rule regulates; "
                                  f"it is never enabled ({tail}; declare `default_capacity: true` on the action if it is a "
                                  f"default capacity, enabled unless a disability bars it)")
        musts = {parse_aim(r.aim).pred for r in inst.rules if r.deontic == "must"}
        for a in sorted(_obliged_aims(G.derived[name]) - musts):
            G.warnings.append(f"derived fluent {name}: (obliged {a} ...) names an aim no `must` rule names; it is never "
                              f"obliged (constant false)")
        for tup in G.fluent_tuples[name]:
            for t in range(k + 1):
                G.fluent(name, tup, t)

    # init: "empty" = endogenous false; "free" = nothing; "declared" = defaults, then initial, else false,
    # with initial_free fluents unconstrained
    initial_true = {parse_literal(lit) for lit in (inst.initial or [])} if init == "declared" else set()
    for f in inst.fluents:
        if f.name in G.derived:
            continue
        for tup in G.fluent_tuples[f.name]:
            val = None
            if init == "empty" and f.name not in G.exogenous:
                val = False
            elif init == "declared" and f.name not in inst.initial_free:
                val = inst.defaults.get(f.name, "false") == "true"
                if (f.name, tup) in initial_true:
                    val = True
            if val is not None:
                G.assertions.append((f"init:{f.name}", G.fluent(f.name, tup, 0) == z3.BoolVal(val)))
    for r in inst.rules:
        G.assertions.append((f"init:violated_{r.id}", z3.Not(G.violation_vars[(r.id, 0)])))

    regulated = G.regulated
    sanction_of: dict[str, list[str]] = {}  # sanction rule id -> rules it punishes
    for r in inst.rules:
        if r.or_else:
            sanction_of.setdefault(r.or_else, []).append(r.id)

    for t in range(k):
        # interleaving: at most one action per step
        if step_mode == "one":
            fired = [v for (_, _, tt), v in G.action_vars.items() if tt == t]
            if len(fired) > 1:
                G.assertions.append((f"one_action@{t}", z3.AtMost(*fired, 1)))
        # enabling
        for a in inst.actions:
            for tup in G.action_instances[a.name]:
                if a.name not in regulated:
                    continue  # unregulated action: always enabled
                en = [cond_at(ri, t) for ri in G.rule_instances
                      if ri.kind == "action" and ri.action == a.name and ri.args == tup and ri.rule.deontic in ("may", "must")]
                if compliance == "sanctioned":
                    for ri in G.rule_instances:
                        if ri.kind == "action" and ri.action == a.name and ri.args == tup and ri.rule.id in sanction_of:
                            en.extend(G.violation_vars[(v, t)] for v in sanction_of[ri.rule.id])
                G.assertions.append((f"enable:{a.name}@{t}", z3.Implies(G.action(a.name, tup, t), z3.Or(*en) if en else z3.BoolVal(False))))
        # obligations / prohibitions
        for ri in G.rule_instances:
            r = ri.rule
            if r.deontic == "may":
                continue
            c = cond_at(ri, t)
            act = ri.aim_at(G, t)
            breach = z3.And(c, z3.Not(act)) if r.deontic == "must" else z3.And(c, act)
            soft = compliance == "sanctioned" and r.or_else is not None
            if not soft:
                G.assertions.append((f"{r.id}@{t}", z3.Not(breach)))
        for r in inst.rules:
            insts = [ri for ri in G.rule_instances if ri.rule.id == r.id]
            soft = compliance == "sanctioned" and r.or_else is not None and r.deontic != "may"
            if soft:
                breaches = []
                for ri in insts:
                    c = cond_at(ri, t)
                    act = ri.aim_at(G, t)
                    breaches.append(z3.And(c, z3.Not(act)) if r.deontic == "must" else z3.And(c, act))
                G.assertions.append((f"sanction:{r.id}@{t}", G.violation_vars[(r.id, t + 1)] == (z3.Or(*breaches) if breaches else z3.BoolVal(False))))
            else:
                G.assertions.append((f"sanction:{r.id}@{t}", z3.Not(G.violation_vars[(r.id, t + 1)])))
        # frame axioms (derived fluents have none: they are defined at every step)
        for f in inst.fluents:
            if f.name in G.derived:
                continue
            for tup in G.fluent_tuples[f.name]:
                sets_true, sets_false = [], []
                for a in inst.actions:
                    for e in a.effects:
                        if e.fluent != f.name:
                            continue
                        for atup in G.action_instances[a.name]:
                            b = dict(zip(a.args, atup))
                            if all(b.get(x, x) == y or (x not in b and x not in agents) for x, y in zip(e.args, tup)):
                                (sets_true if e.value else sets_false).append(G.action(a.name, atup, t))
                nxt = G.fluent(f.name, tup, t + 1)
                cur = G.fluent(f.name, tup, t)
                rhs = z3.Or(z3.Or(*sets_true) if sets_true else z3.BoolVal(False),
                            z3.And(cur, z3.Not(z3.Or(*sets_false)) if sets_false else cur))
                G.assertions.append((f"frame:{f.name}@{t}", nxt == rhs))
    # state obligations (ADR 0009) also bind at the last step k, where no action variable exists
    for ri in G.rule_instances:
        r = ri.rule
        if ri.kind != "state" or r.deontic == "may":
            continue
        if compliance == "sanctioned" and r.or_else is not None:
            continue  # soft: a breach at k has no step k+1 to record the sanction in
        c = cond_at(ri, k)
        f = ri.aim_at(G, k)
        breach = z3.And(c, z3.Not(f)) if r.deontic == "must" else z3.And(c, f)
        G.assertions.append((f"{r.id}@{k}", z3.Not(breach)))
    return G


# --------------------------------------------------------------------- traces
def trace_of(m: z3.ModelRef, G: Grounded, prop_at=None) -> list[TraceStep]:
    """Model -> readable trace. prop_at(t) -> z3 expr lets the step record whether the property holds."""
    out = []
    for t in range(G.k + 1):
        fl = [f"{n}({', '.join(a)})" if a else n for (n, a, tt), v in [*G.fluent_vars.items(), *G.derived_vars.items()]
              if tt == t and z3.is_true(m.eval(v, model_completion=True))]
        ac = [f"{n}({', '.join(a)})" for (n, a, tt), v in G.action_vars.items()
              if tt == t and z3.is_true(m.eval(v, model_completion=True))]
        vi = [f"violated_{r}" for (r, tt), v in G.violation_vars.items() if tt == t and z3.is_true(m.eval(v, model_completion=True))]
        ph = None
        if prop_at is not None:
            ph = z3.is_true(m.eval(prop_at(t), model_completion=True))
        out.append(TraceStep(step=t, actions=sorted(ac), fluents=sorted(fl + vi), property_holds=ph))
    return out
