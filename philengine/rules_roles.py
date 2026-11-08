"""Role cardinality (plans/cardinality.md): the ONE place that turns roles into agents.

`RoleDecl.count` agents per role. count 1 keeps the bare role name (every existing entry grounds identically);
count N > 1 yields `role_1..role_N`. Both the reference semantics (rules_reference) and the z3 lowering (rules_lower)
call `instances` / `agent_names` / `instance_role`, so they cannot disagree on the domain.

Roles with count > 1 cannot be used as literals (an action/aim/effect argument naming the role): which instance would
be meant? Name an instance or use a variable typed by the role.

`initial` literals may name an instance (`married(husband, wife_2)`). A role name with count > 1 in an `initial`
literal is, by flag, either an error or every instance: INITIAL_ROLE_EVERY_INSTANCE (default False = error; the
author decides, plans/cardinality.md "Open for the author"). Set it to True to expand to the product over instances.
"""
from __future__ import annotations

import itertools
import os

from . import sexpr as sx

INITIAL_ROLE_EVERY_INSTANCE = False  # flag: False = a role name with count > 1 in `initial` is an error
DEFAULT_MAX_ROLE_COUNT = 3


class RoleCardinalityError(ValueError):
    pass


def max_role_count() -> int:
    raw = os.environ.get("PHIL_MAX_ROLE_COUNT")
    if raw is None:
        return DEFAULT_MAX_ROLE_COUNT
    try:
        return int(raw)
    except ValueError:
        raise RoleCardinalityError(f"PHIL_MAX_ROLE_COUNT={raw!r} is not an integer")


def instances(inst, role: str) -> list[str]:
    """Agent names of a role (an unknown name stands for itself, so callers need no special case)."""
    for r in inst.roles:
        if r.name == role:
            return r.instance_names
    return [role]


def agent_names(inst) -> list[str]:
    return [a for r in inst.roles for a in r.instance_names]


def instance_role(inst) -> dict[str, str]:
    """agent name -> role name."""
    return {a: r.name for r in inst.roles for a in r.instance_names}


def multi_roles(inst) -> set[str]:
    return {r.name for r in inst.roles if r.count > 1}


def check_role_counts(inst) -> list[str]:
    """Ceiling, instance-name collisions, literal use of a multi-instance role. [] = fine."""
    errs: list[str] = []
    cap = max_role_count()
    for r in inst.roles:
        if r.count > cap:
            errs.append(f"role {r.name!r}: count {r.count} exceeds the ceiling {cap} (raise it with PHIL_MAX_ROLE_COUNT)")
    names = agent_names(inst)
    for n in sorted({n for n in names if names.count(n) > 1}):
        errs.append(f"agent name {n!r} is produced more than once (role or instance name collision)")
    multi = multi_roles(inst)
    if multi:
        uses: set[str] = set()
        for a in inst.actions:
            uses |= multi & set(a.args)
            for e in a.effects:
                uses |= multi & set(e.args)
        for r in inst.rules:
            try:
                aim = sx.parse(r.aim)
            except sx.ParseError:
                continue
            if isinstance(aim, sx.App):
                uses |= multi & {t.name for t in aim.args}
        for role in sorted(uses):
            errs.append(f"role {role!r} has count {next(r.count for r in inst.roles if r.name == role)} and is used as "
                        f"a literal (action/aim/effect argument): name an instance or use a variable")
    return errs


def expand_initial(inst, name: str, args: tuple) -> list[tuple[str, tuple]]:
    """One `initial` literal -> the atoms it asserts. Instance names and count-1 role names stand for themselves;
    a role name with count > 1 is every instance when INITIAL_ROLE_EVERY_INSTANCE, else RoleCardinalityError."""
    doms = []
    by_role = {r.name: r for r in inst.roles}
    for x in args:
        r = by_role.get(x)
        if r is None or r.count == 1:
            doms.append([x])
        elif INITIAL_ROLE_EVERY_INSTANCE:
            doms.append(r.instance_names)
        else:
            raise RoleCardinalityError(
                f"initial {name}({', '.join(args)}): role {x!r} has count {r.count}; name an instance "
                f"({', '.join(r.instance_names)}) (or set rules_roles.INITIAL_ROLE_EVERY_INSTANCE)")
    return [(name, t) for t in itertools.product(*doms)]
