"""Composition support (CL plans/composition.md, "Two problems" item 2): freeze the prefix heuristic.

`Reference` binds a rule variable by precedence: literal role name > `Rule.var_roles` > the action's / fluent's
`arg_roles` > the prefix heuristic (`_var_role`: the unique declared role whose name starts with the variable;
None = all agents). Adding roles (composition) can make a prefix ambiguous and silently untype a variable.
`freeze_bindings` records the answer the heuristic gives TODAY, in the entry's own role list, into `var_roles`,
using `Reference`'s own resolution code (`_Typing`, no grounding built). Typed variables: every aim variable
(action aims: positions 1.. since position 0 is the attribute; state aims: all positions) and every condition
variable that is not in the aim (Reference types those too: existential domain). Names that are roles are
literals, not variables, and are skipped.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import sexpr as sx
from .rules_reference import _Typing
from .schemas_rules import InstitutionJSON

ACTIONS = ("written", "already_explicit", "untyped", "conflict")


@dataclass(frozen=True)
class FreezeRow:
    entry: str
    rule: str
    variable: str
    role: str | None  # what the heuristic / arg_roles resolve to with var_roles ignored
    action: str  # written | already_explicit | untyped | conflict
    existing: str | None = None  # the explicit var_roles entry, if any

    def to_dict(self) -> dict:
        return asdict(self)


def _typer(inst: InstitutionJSON) -> _Typing:
    t = _Typing()
    t._init_typing(inst)
    t._init_lits(inst)
    return t


def freeze_bindings(inst: InstitutionJSON) -> tuple[InstitutionJSON, list[FreezeRow]]:
    t = _typer(inst)
    rows: list[FreezeRow] = []
    new_rules = []
    for r in inst.rules:
        bare = r.model_copy(update={"var_roles": {}})  # what Reference gives with no explicit entries
        aim = t._aim(r.aim)
        is_action = not (aim.pred in t.fluents and aim.pred not in t.actions)
        resolved: dict[str, str | None] = {}
        for i, (n, ty) in enumerate(t.aim_types(bare).items()):
            if (is_action and i == 0) or n in t.roles:
                continue  # attribute slot / literal role name
            resolved.setdefault(n, ty)
        cond = None if r.conditions.strip() == "true" else sx.parse(r.conditions)
        for v, ty in t.free_var_types(bare, cond).items():
            if v not in t.roles:
                resolved.setdefault(v, ty)
        vr = dict(r.var_roles)
        for v, ty in resolved.items():
            ex = r.var_roles.get(v)
            if ex is not None:
                act = "conflict" if ty is not None and ty != ex else "already_explicit"
            elif ty is None:
                act = "untyped"
            else:
                act = "written"
                vr[v] = ty
            rows.append(FreezeRow(inst.id, r.id, v, ty, act, ex))
        new_rules.append(r.model_copy(update={"var_roles": vr}))
    return inst.model_copy(update={"rules": new_rules}), rows
