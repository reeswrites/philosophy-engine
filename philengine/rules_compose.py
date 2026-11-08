"""Composition support (CL plans/composition.md, "Two problems" item 2): freeze the prefix heuristic.

`Reference` binds a rule variable by precedence: literal role name > `Rule.var_roles` > the action's / fluent's
`arg_roles` > the prefix heuristic (`_var_role`: the unique declared role whose name starts with the variable;
None = all agents). Adding roles (composition) can make a prefix ambiguous and silently untype a variable.
`freeze_bindings` records the answer the heuristic gives TODAY, in the entry's own role list, into `var_roles`,
using `Reference`'s own resolution code (`_Typing`, no grounding built). Typed variables: every aim variable
(action aims: position 0 resolves to the rule's attribute, written as an explicit entry; positions 1.. by the heuristic; state aims: all positions) and every condition
variable that is not in the aim (Reference types those too: existential domain). Names that are roles are
literals, not variables, and are skipped.

`freeze_action_roles` does the same for action parameters: each parameter's type by the prefix heuristic over the
entry's OWN roles is written into `ActionDecl.arg_roles` (explicit entries win; an untypable parameter stays None),
so a role added by composition cannot re-type it (coverture's `h` must stay `husband` beside a `hospital`).
`freeze_bindings` runs it first, so its rows (kind="action", `rule` = the action name) come back with the rule rows.
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
    existing: str | None = None  # the explicit var_roles / arg_roles entry, if any
    kind: str = "rule"  # "rule": `rule` is a rule id, `variable` a rule variable; "action": an action name and parameter

    def to_dict(self) -> dict:
        return asdict(self)


def _typer(inst: InstitutionJSON) -> _Typing:
    t = _Typing()
    t._init_typing(inst)
    t._init_lits(inst)
    return t


def freeze_action_roles(inst: InstitutionJSON) -> tuple[InstitutionJSON, list[FreezeRow]]:
    """Write each action parameter's type (prefix heuristic over the entry's own roles, `_Typing._var_role`) into
    `arg_roles`; an explicit entry is kept (already_explicit, or conflict when the heuristic disagrees), an untypable
    parameter stays None (untyped). An action with no typable parameter is returned unchanged (arg_roles None)."""
    t = _typer(inst)
    rows: list[FreezeRow] = []
    acts = []
    for a in inst.actions:
        given = list(a.arg_roles) if a.arg_roles is not None else [None] * len(a.args)
        typed: list[str | None] = []
        for p, ex in zip(a.args, given):
            ty = t._var_role(p)
            if ex is not None:
                act = "conflict" if ty is not None and ty != ex else "already_explicit"
                typed.append(ex)
            elif ty is None:
                act = "untyped"
                typed.append(None)
            else:
                act = "written"
                typed.append(ty)
            rows.append(FreezeRow(inst.id, a.name, p, ty, act, ex, kind="action"))
        acts.append(a.model_copy(update={"arg_roles": typed}) if any(x is not None for x in typed) else a)
    return inst.model_copy(update={"actions": acts}), rows


def freeze_bindings(inst: InstitutionJSON) -> tuple[InstitutionJSON, list[FreezeRow]]:
    """Freeze action parameter roles, then rule variable roles. Rows: action rows first, then rule rows."""
    inst, rows = freeze_action_roles(inst)
    t = _typer(inst)
    new_rules = []
    for r in inst.rules:
        bare = r.model_copy(update={"var_roles": {}})  # what Reference gives with no explicit entries
        aim = t._aim(r.aim)
        is_action = not (aim.pred in t.fluents and aim.pred not in t.actions)
        resolved: dict[str, str | None] = {}
        for i, (n, ty) in enumerate(t.aim_types(bare).items()):
            if n in t.roles:
                continue  # literal role name
            # action aim position 0: aim_types (bare rule) already returns rule.attribute; record it too (P3b)
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


# ---------------------------------------------------------------------------------------------------------------
# compose (ADR 0018, plans/composition.md unification table)

import re

from pydantic import ValidationError

from .schemas_rules import ActionDecl, FluentDecl, RoleDecl


class ComposeError(Exception):
    """A composition conflict; the message names the member and the field."""


_IDENT_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_])")


def _rn(text: str, amap: dict[str, str]) -> str:
    """Rename role-name atoms in an S-expression / literal string, simultaneously. Heads (an identifier right after
    `(` or right before `(`) are fluent/action/keyword names and are left alone."""
    if not amap:
        return text

    def sub(m: re.Match) -> str:
        w = m.group(0)
        if w not in amap:
            return w
        before = text[:m.start()].rstrip()
        if before.endswith("(") and not re.search(r"[A-Za-z0-9_]\($", before):  # S-expr head, not call-style `f(arg`
            return w
        if text[m.end():].lstrip().startswith("("):
            return w
        return amap[w]
    return _IDENT_RE.sub(sub, text)


def _alias_member(m: InstitutionJSON, amap: dict[str, str], eff: str) -> InstitutionJSON:
    roles = {r.name for r in m.roles}
    for old, new in amap.items():
        if old not in roles:
            raise ComposeError(f"member {eff!r}: alias {old!r}->{new!r}: {old!r} is not a role (roles: {sorted(roles)})")
    renamed = [amap.get(r.name, r.name) for r in m.roles]
    if len(set(renamed)) != len(renamed):
        raise ComposeError(f"member {eff!r}: aliases {amap} make two roles share a name in field roles")
    if not amap:
        return m
    ren = lambda x: amap.get(x, x) if x is not None else None  # noqa: E731
    d = m.model_dump()
    d["roles"] = [{**r, "name": ren(r["name"])} for r in d["roles"]]
    for f in d["fluents"]:
        if f["arg_roles"] is not None:
            f["arg_roles"] = [ren(x) for x in f["arg_roles"]]
        if f["derived"] is not None:
            f["derived"] = _rn(f["derived"], amap)
    for a in d["actions"]:
        a["args"] = [ren(x) for x in a["args"]]
        if a["arg_roles"] is not None:
            a["arg_roles"] = [ren(x) for x in a["arg_roles"]]
        for e in a["effects"]:
            e["args"] = [ren(x) for x in e["args"]]
    for r in d["rules"]:
        r["attribute"] = ren(r["attribute"])
        r["aim"] = _rn(r["aim"], amap)
        r["conditions"] = _rn(r["conditions"], amap)
        r["var_roles"] = {k: ren(v) for k, v in r["var_roles"].items()}
    if d["initial"] is not None:
        d["initial"] = [_rn(x, amap) for x in d["initial"]]
    return InstitutionJSON.model_validate(d)


def compose(members: list[InstitutionJSON], aliases: dict[str, dict[str, str]], id: str, *,
            initial: list[str] | None = None, expected_properties: dict | None = None,
            notes: str = "") -> InstitutionJSON:
    """Union `members` into one entry (ADR 0018). Per member: bindings are frozen in the member's own role list
    (before aliasing, so the prefix heuristic still sees the original names), then `aliases[member]` renames roles
    everywhere (var_roles values included), then the union runs per the unification table; every conflict is a
    ComposeError naming the member and the field. The result is validated like a loaded entry.

    The same entry may appear more than once (e.g. two alias maps). The first occurrence is `<id>`; the nth
    occurrence (n >= 2) is `<id>_<n>`, and that effective id keys `aliases` and builds the rule-id prefix, so
    repeats get distinct prefixes and distinct alias maps. `members` on the result keeps the plain ids."""
    from .rules_lower import validate_institution

    seen: dict[str, int] = {}
    effs = []
    for m in members:
        seen[m.id] = seen.get(m.id, 0) + 1
        effs.append(m.id if seen[m.id] == 1 else f"{m.id}_{seen[m.id]}")
    unknown = set(aliases) - set(effs)
    if unknown:
        raise ComposeError(f"aliases name unknown member(s) {sorted(unknown)}; members are {effs}")

    roles: dict[str, RoleDecl] = {}
    fluents: dict[str, FluentDecl] = {}
    actions: dict[str, ActionDecl] = {}
    rules, defaults, init_lits, init_free = [], {}, [], []
    for m0, eff in zip(members, effs):
        frozen, frows = freeze_bindings(m0)
        for fr in frows:
            if fr.kind == "action" and fr.action == "conflict":
                raise ComposeError(f"member {eff!r}: action {fr.rule!r} parameter {fr.variable!r} arg_roles says "
                                   f"{fr.existing!r} but the member's own roles type it {fr.role!r}")
        m = _alias_member(frozen, aliases.get(eff, {}), eff)
        pre = eff.replace("-", "_") + "__"
        for r in m.roles:
            roles.setdefault(r.name, r)
        for f in m.fluents:
            g = fluents.get(f.name)
            if g is None:
                fluents[f.name] = f
                continue
            if g.arity != f.arity:
                raise ComposeError(f"member {eff!r}: fluent {f.name!r} field arity is {f.arity}, earlier member has {g.arity}")
            if (g.derived is not None or f.derived is not None) and (g.derived != f.derived or g.params != f.params):
                raise ComposeError(f"member {eff!r}: fluent {f.name!r} field derived differs: {f.derived!r} vs {g.derived!r}")
            if g.arg_roles is not None and f.arg_roles is not None and g.arg_roles != f.arg_roles:
                raise ComposeError(f"member {eff!r}: fluent {f.name!r} field arg_roles {f.arg_roles} disagrees with {g.arg_roles}")
            if g.arg_roles is None and f.arg_roles is not None:
                fluents[f.name] = g.model_copy(update={"arg_roles": f.arg_roles})
        for a in m.actions:
            b = actions.get(a.name)
            if b is None:
                actions[a.name] = a
            elif b.model_dump(exclude={"arg_roles"}) != a.model_dump(exclude={"arg_roles"}):
                raise ComposeError(f"member {eff!r}: action {a.name!r} differs from an earlier member's (args, effects, gloss or default_capacity)")
            elif b.arg_roles != a.arg_roles:
                # frozen parameter types from two occurrences (e.g. the same member under two alias maps): keep a
                # position where they agree or one side is untyped, else fall back to untyped (the pre-freeze answer).
                # Rule variables are already pinned by var_roles, so this only loosens the fallback, never a rule.
                ba, aa = b.arg_roles or [None] * len(b.args), a.arg_roles or [None] * len(a.args)
                merged = [x if x == y or y is None else (y if x is None else None) for x, y in zip(ba, aa)]
                actions[a.name] = b.model_copy(update={"arg_roles": merged if any(x is not None for x in merged) else None})
        for r in m.rules:
            rules.append(r.model_copy(update={"id": pre + r.id, "or_else": pre + r.or_else if r.or_else else None}))
        for k, v in m.defaults.items():
            if defaults.setdefault(k, v) != v:
                raise ComposeError(f"member {eff!r}: field defaults: fluent {k!r} is {v!r}, earlier member has {defaults[k]!r}")
        init_lits += [x for x in (m.initial or []) if x not in init_lits]
        init_free += [x for x in m.initial_free if x not in init_free]
    init_lits += [x for x in (initial or []) if x not in init_lits]
    declared = any(m.initial is not None for m in members) or initial is not None
    try:
        comp = InstitutionJSON.model_validate({
            "id": id, "name": id, "roles": [r.model_dump() for r in roles.values()],
            "fluents": [f.model_dump() for f in fluents.values()], "actions": [a.model_dump() for a in actions.values()],
            "rules": [r.model_dump() for r in rules],
            "source_text": "composite of: " + ", ".join(effs),
            "expected_properties": dict(expected_properties or {}), "notes": notes,
            "defaults": defaults, "initial": init_lits if declared else None, "initial_free": init_free,
            "members": [m.id for m in members]})
    except ValidationError as e:
        raise ComposeError(f"composite {id!r}: invalid after union: {e}") from e
    errs = validate_institution(comp)
    if errs:
        raise ComposeError(f"composite {id!r}: " + "; ".join(errs))
    return comp
