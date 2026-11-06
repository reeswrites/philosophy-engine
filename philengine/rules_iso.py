"""Stage: iso for the institutions family (plan: plans/institutions-phase0.md, Stage 6 and gate (b), (c), (f)).

Two institutions are isomorphic when there is a bijection over (roles ∪ fluents ∪ actions) under which their
rule sets are equal: same deontic, same aim shape (action + argument pattern, variables abstracted to their
position of first occurrence), same condition structure (And/Or children compared up to permutation), and the
same or_else linkage (matched rules' sanction rules are matched to each other). Strand tags enter the skeleton
only with `with_strands=True`; the plan warns they may make care + control isomorphic by construction, so the
CLI reports both.

Method (recorded in `IsoReport.method`): backtracking over rule pairs with a name-erased per-rule skeleton
(`rule_skeleton`) as a pruning hash, plus a unifier that extends a partial injective name map while it walks the
two rules' ASTs. Z3 is not used: the rule sets are small (<= ~10 rules, <= ~5 roles) and the question is purely
syntactic, so the bijection search is exact without it. The search also returns the largest matched sub-signature
when no full isomorphism exists (maximum common sub-rule-set), which is what the extension section of the plan
asks every human/non-human report to print.

Outputs for a pair (`IsoReport`):
  iso                     every rule on both sides matched
  pure_rename             iso and the bijection moves only role names (fluents and actions map to themselves)
  matched_sub_signature   [(rule id in A, rule id in B), ...]
  unmatched_a/_b          rule ids with no image
  rule_distance           max(|A|, |B|) - matched: rule edits (add, remove or replace one rule) to turn one
                          into the other, so a minimal pair that changes one rule is at distance 1
  add_remove_distance     |A| + |B| - 2 * matched: the same with replacement counted as remove + add
  mapping                 {"role": {a: b}, "fluent": {a: b}, "action": {a: b}} on the names used by matched rules
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from . import sexpr as sx
from .rules_lower import parse_aim, parse_condition, var_role
from .schemas_rules import InstitutionJSON, Rule

METHOD = "backtracking over rule pairs, skeleton-hash pruning, AST unifier; z3 not used"
KINDS = ("role", "fluent", "action")
COND_LEVELS = ("exact", "guard")  # exact: conditions equal under the bijection; guard: only conditional-vs-unconditional
LEVELS = ("exact", "guard", "exact+strands", "guard+strands")  # dataset spelling of (cond_level, with_strands)


def parse_level(level: str) -> tuple[str, bool]:
    """"guard+strands" -> ("guard", True). Raises ValueError on an unknown level."""
    if level not in LEVELS:
        raise ValueError(f"unknown iso level {level!r}; have {LEVELS}")
    parts = level.split("+")
    return parts[0], "strands" in parts[1:]


def level_name(cond_level: str, with_strands: bool) -> str:
    return cond_level + ("+strands" if with_strands else "")
GUARDED = ("guarded",)  # sentinel condition at the guard level


def abstract_condition(cond, level: str):
    if level == "exact":
        return cond
    if level == "guard":
        return None if cond is None else GUARDED
    raise ValueError(f"unknown condition level {level!r}; have {COND_LEVELS}")


# ------------------------------------------------------------------ parsed rules
@dataclass
class PRule:
    rule: Rule
    aim: sx.App
    cond: object  # AST or None for `true`
    skel: tuple   # name-erased pruning key


@dataclass
class PInst:
    inst: InstitutionJSON
    roles: set[str]
    rules: list[PRule]
    by_id: dict[str, PRule]

    @property
    def id(self) -> str:
        return self.inst.id


def _erase(ast, roles: set[str], varmap: dict) -> object:
    """Name-erased, order-normalised condition structure (fluent names -> arity, vars -> aim position or '_')."""
    if ast is None:
        return "true"
    if ast is GUARDED:
        return "guarded"
    if isinstance(ast, sx.Sym):
        if ast.name in roles:
            return "role"
        return varmap.get(ast.name, "_")
    if isinstance(ast, sx.App):
        return ("F%d" % len(ast.args), tuple(_erase(a, roles, varmap) for a in ast.args))
    if isinstance(ast, sx.Not):
        return ("not", _erase(ast.arg, roles, varmap))
    if isinstance(ast, (sx.And, sx.Or)):
        kids = sorted((_erase(a, roles, varmap) for a in ast.args), key=repr)
        return (type(ast).__name__.lower(), tuple(kids))
    if isinstance(ast, (sx.Implies, sx.Iff, sx.Eq)):
        return (type(ast).__name__.lower(), _erase(ast.left, roles, varmap), _erase(ast.right, roles, varmap))
    if isinstance(ast, sx.Quant):
        inner = dict(varmap)
        for i, (v, _s) in enumerate(ast.vars):
            inner[v] = "q%d" % i
        return (ast.kind, len(ast.vars), _erase(ast.body, roles, inner))
    return repr(ast)


def rule_skeleton(r: Rule, roles: set[str], with_strands: bool = False, cond_level: str = "exact") -> tuple:
    aim = parse_aim(r.aim)
    cond = abstract_condition(parse_condition(r.conditions), cond_level)
    varmap: dict = {}
    pattern = []
    for a in aim.args:
        if a.name in roles:
            pattern.append("role")
        else:
            varmap.setdefault(a.name, "v%d" % len(varmap))
            pattern.append(varmap[a.name])
    key = (r.deontic, tuple(pattern), _erase(cond, roles, varmap), r.or_else is not None)
    if with_strands:
        key = key + (r.strand if r.strand is not None else "<untagged>",)  # null strand (R2.5): its own tag
    return key


def prepare(inst: InstitutionJSON, with_strands: bool = False, cond_level: str = "exact") -> PInst:
    roles = {x.name for x in inst.roles}
    rules = []
    for r in inst.rules:
        cond = abstract_condition(parse_condition(r.conditions), cond_level)
        rules.append(PRule(r, parse_aim(r.aim), cond, rule_skeleton(r, roles, with_strands, cond_level)))
    return PInst(inst, roles, rules, {p.rule.id: p for p in rules})


# ------------------------------------------------------------------ unifier
def _bind(m: dict, kind: str, a: str, b: str) -> dict | None:
    """Extend the injective map m[kind] with a -> b; None on clash."""
    fwd = m[kind]
    if a in fwd:
        return m if fwd[a] == b else None
    if b in m["inv_" + kind]:
        return None
    m2 = {k: dict(v) for k, v in m.items()}
    m2[kind][a] = b
    m2["inv_" + kind][b] = a
    return m2


def _unify_term(x: sx.Sym, y: sx.Sym, A: PInst, B: PInst, m: dict):
    xr, yr = x.name in A.roles, y.name in B.roles
    if xr != yr:
        return None
    return _bind(m, "role" if xr else "var", x.name, y.name)


def _unify(x, y, A: PInst, B: PInst, m: dict):
    """Yield every extension of m under which condition x (from A) equals y (from B)."""
    if x is None or y is None or x is GUARDED or y is GUARDED:
        if x is y:
            yield m
        return
    if type(x) is not type(y):
        return
    if isinstance(x, sx.Sym):
        m2 = _unify_term(x, y, A, B, m)
        if m2 is not None:
            yield m2
        return
    if isinstance(x, sx.App):
        if len(x.args) != len(y.args):
            return
        m2 = _bind(m, "fluent", x.pred, y.pred)
        if m2 is None:
            return
        yield from _unify_seq(list(x.args), list(y.args), A, B, m2)
        return
    if isinstance(x, sx.Not):
        yield from _unify(x.arg, y.arg, A, B, m)
        return
    if isinstance(x, (sx.And, sx.Or)):
        if len(x.args) != len(y.args):
            return
        seen = set()
        for perm in itertools.permutations(range(len(y.args))):
            ys = [y.args[i] for i in perm]
            for m2 in _unify_seq(list(x.args), ys, A, B, m):
                key = repr(sorted((k, sorted(v.items())) for k, v in m2.items()))
                if key not in seen:
                    seen.add(key)
                    yield m2
        return
    if isinstance(x, (sx.Implies, sx.Iff, sx.Eq)):
        yield from _unify_seq([x.left, x.right], [y.left, y.right], A, B, m)
        return
    if isinstance(x, sx.Quant):
        if x.kind != y.kind or len(x.vars) != len(y.vars):
            return
        m2 = m
        for (vx, _), (vy, _) in zip(x.vars, y.vars):
            m2 = _bind(m2, "var", vx, vy)
            if m2 is None:
                return
        yield from _unify(x.body, y.body, A, B, m2)
        return


def _unify_seq(xs, ys, A, B, m):
    if not xs:
        yield m
        return
    for m2 in _unify(xs[0], ys[0], A, B, m):
        yield from _unify_seq(xs[1:], ys[1:], A, B, m2)


def _unify_rules(a: PRule, b: PRule, A: PInst, B: PInst, m: dict):
    """Yield every extension of m (names only; the per-rule var map is reset) under which a == b."""
    ra, rb = a.rule, b.rule
    if ra.deontic != rb.deontic or (ra.or_else is None) != (rb.or_else is None):
        return
    if len(a.aim.args) != len(b.aim.args):
        return
    m0 = dict(m); m0["var"] = {}; m0["inv_var"] = {}
    m0 = _bind(m0, "role", ra.attribute, rb.attribute)
    if m0 is None:
        return
    m0 = _bind(m0, "action", a.aim.pred, b.aim.pred)
    if m0 is None:
        return
    for m1 in _unify_seq(list(a.aim.args), list(b.aim.args), A, B, m0):
        for m2 in _unify(a.cond, b.cond, A, B, m1):
            out = {k: v for k, v in m2.items() if not k.endswith("var")}
            yield out


def _empty_map() -> dict:
    m = {}
    for k in KINDS:
        m[k] = {}; m["inv_" + k] = {}
    return m


# ------------------------------------------------------------------ search
@dataclass
class IsoReport:
    a: str
    b: str
    iso: bool
    pure_rename: bool
    matched_sub_signature: list[tuple[str, str]]
    unmatched_a: list[str]
    unmatched_b: list[str]
    rule_distance: int
    mapping: dict
    with_strands: bool
    add_remove_distance: int = 0
    cond_level: str = "exact"
    method: str = METHOD
    n_a: int = 0
    n_b: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "a": self.a, "b": self.b, "iso": self.iso, "pure_rename": self.pure_rename,
            "matched_sub_signature": [list(p) for p in self.matched_sub_signature],
            "unmatched": {self.a: self.unmatched_a, self.b: self.unmatched_b},
            "rule_distance": self.rule_distance, "add_remove_distance": self.add_remove_distance,
            "mapping": self.mapping,
            "with_strands": self.with_strands, "cond_level": self.cond_level, "method": self.method,
            "notes": self.notes,
        }


def _linkage_ok(pairs: dict, A: PInst, B: PInst) -> bool:
    """Matched rules whose sanction rules are both matched must have them matched to each other."""
    inv = {b: a for a, b in pairs.items()}
    for ia, ib in pairs.items():
        oa, ob = A.by_id[ia].rule.or_else, B.by_id[ib].rule.or_else
        if oa is None or ob is None:
            continue
        if oa in pairs and pairs[oa] != ob:
            return False
        if ob in inv and inv[ob] != oa:
            return False
    return True


def match(a_inst: InstitutionJSON, b_inst: InstitutionJSON, with_strands: bool = False,
          cond_level: str = "exact") -> IsoReport:
    A, B = prepare(a_inst, with_strands, cond_level), prepare(b_inst, with_strands, cond_level)
    best = {"n": -1, "pairs": {}, "map": None}
    order = sorted(A.rules, key=lambda p: (sum(1 for q in B.rules if q.skel == p.skel), p.rule.id))
    cap = min(len(A.rules), len(B.rules))

    def rec(i: int, pairs: dict, used_b: set, m: dict):
        remaining = len(order) - i
        if len(pairs) + remaining <= best["n"]:
            return
        if i == len(order):
            if _linkage_ok(pairs, A, B):
                best["n"] = len(pairs); best["pairs"] = dict(pairs); best["map"] = m
            return
        p = order[i]
        for q in B.rules:
            if q.rule.id in used_b or q.skel != p.skel:
                continue
            for m2 in _unify_rules(p, q, A, B, m):
                pairs[p.rule.id] = q.rule.id; used_b.add(q.rule.id)
                rec(i + 1, pairs, used_b, m2)
                del pairs[p.rule.id]; used_b.discard(q.rule.id)
                if best["n"] == cap:
                    return
        rec(i + 1, pairs, used_b, m)

    rec(0, {}, set(), _empty_map())
    pairs = best["pairs"]
    m = best["map"] or _empty_map()
    mapping = {k: dict(sorted(m[k].items())) for k in KINDS}
    iso = len(pairs) == len(A.rules) == len(B.rules)
    pure = iso and all(k == v for kind in ("fluent", "action") for k, v in mapping[kind].items())
    ua = [p.rule.id for p in A.rules if p.rule.id not in pairs]
    ub = [q.rule.id for q in B.rules if q.rule.id not in set(pairs.values())]
    rep = IsoReport(
        a=a_inst.id, b=b_inst.id, iso=iso, pure_rename=pure,
        matched_sub_signature=[(p.rule.id, pairs[p.rule.id]) for p in A.rules if p.rule.id in pairs],
        unmatched_a=ua, unmatched_b=ub, rule_distance=max(len(A.rules), len(B.rules)) - len(pairs),
        mapping=mapping, add_remove_distance=len(A.rules) + len(B.rules) - 2 * len(pairs), with_strands=with_strands, cond_level=cond_level, n_a=len(A.rules), n_b=len(B.rules),
    )
    if cond_level != "exact":
        rep.notes.append(f"condition level {cond_level}: conditions compared only as conditional/unconditional")
    if iso and not pure:
        rep.notes.append("structural isomorphism: fluent/action names differ")
    return rep


def match_all(insts: list[InstitutionJSON], with_strands: bool = False,
              cond_level: str = "exact") -> dict[tuple[str, str], IsoReport]:
    out = {}
    for a, b in itertools.combinations(insts, 2):
        r = match(a, b, with_strands, cond_level)
        out[(a.id, b.id)] = r
        out[(b.id, a.id)] = r
    return out


@dataclass
class CareControl:
    """The care + control form found inside a matched sub-signature (gate (b)). Three matched rule pairs, each
    (id in A, id in B):
      care      a `must` superadditive rule (duty) bound to attribute X whose target is subject variable S
      control   a `may` rival rule bound to the same X whose target is the same S (the power over the subject)
      exit_bar  a `must_not` rule bound to S's role: the subject's own action is barred (what makes S a dependent,
                not a counterparty; a lease has no such rule, the tenant may leave)
    `matched` / `n_a` / `n_b` give the size of the whole matched sub-signature relative to the rule sets."""
    care: tuple[str, str]
    control: tuple[str, str]
    exit_bar: tuple[str, str]
    subject_role: tuple[str, str]
    matched: int
    n_a: int
    n_b: int

    def pairs(self) -> list[tuple[str, str]]:
        return [self.care, self.control, self.exit_bar]

    @property
    def coverage(self) -> float:
        return self.matched / max(self.n_a, self.n_b, 1)

    def __iter__(self):  # backwards compatible: list(cc) gives the pairs
        return iter(self.pairs())


def rule_target(r: Rule, inst: InstitutionJSON) -> tuple[str | None, str | None]:
    """(variable, role) of a rule's target: the aim's second argument (the first is the actor / bearer), typed
    by the action's or fluent's arg_roles, Rule.var_roles, or the prefix heuristic."""
    aim = parse_aim(r.aim)
    if len(aim.args) < 2:
        return None, None
    v = aim.args[1].name
    roles = {x.name for x in inst.roles}
    if v in roles:
        return v, v
    decl = next((a for a in inst.actions if a.name == aim.pred), None) or next((f for f in inst.fluents if f.name == aim.pred), None)
    role = None
    if decl is not None and decl.arg_roles and len(decl.arg_roles) > 1:
        role = decl.arg_roles[1]
    if v in r.var_roles:
        role = r.var_roles[v]
    if role is None:
        role = var_role(v, inst)
    return v, role


def _same_target(u: tuple, v: tuple) -> bool:
    return u[0] is not None and u[0] == v[0] and (u[1] is None or v[1] is None or u[1] == v[1])


def care_control_subsignature(rep: IsoReport, a_inst: InstitutionJSON, b_inst: InstitutionJSON) -> CareControl | None:
    """The plan's care + control form inside a matched sub-signature: care (must, superadditive) and control
    (may, rival) on one attribute and one target subject on each side, plus a must_not on the subject's own
    action (exit bar). A matched superadditive + a matched rival may on one attribute is NOT enough (review
    finding 4: a lease matched that). Returns the CareControl, or None."""
    ra = {r.id: r for r in a_inst.rules}
    rb = {r.id: r for r in b_inst.rules}
    ms = rep.matched_sub_signature
    care = [(x, y) for x, y in ms if ra[x].strand == "superadditive" == rb[y].strand and ra[x].deontic == "must" == rb[y].deontic]
    ctrl = [(x, y) for x, y in ms if ra[x].strand == "rival" == rb[y].strand and ra[x].deontic == "may" == rb[y].deontic]
    bars = [(x, y) for x, y in ms if ra[x].deontic == "must_not" == rb[y].deontic]
    for c in care:
        ta, tb = rule_target(ra[c[0]], a_inst), rule_target(rb[c[1]], b_inst)
        if ta[0] is None or tb[0] is None:
            continue
        for k in ctrl:
            if ra[c[0]].attribute != ra[k[0]].attribute or rb[c[1]].attribute != rb[k[1]].attribute:
                continue
            if not (_same_target(rule_target(ra[k[0]], a_inst), ta) and _same_target(rule_target(rb[k[1]], b_inst), tb)):
                continue  # the rival may must act on the same subject (variable, and role when both are typed)
            for e in bars:
                if ta[1] is not None and tb[1] is not None and ra[e[0]].attribute == ta[1] and rb[e[1]].attribute == tb[1]:
                    return CareControl(c, k, e, (ta[1], tb[1]), len(ms), rep.n_a, rep.n_b)
    return None


def format_care_control(cc: CareControl | None, a_inst: InstitutionJSON, b_inst: InstitutionJSON) -> str:
    if cc is None:
        return "care+control: -"
    ra = {r.id: r for r in a_inst.rules}
    rb = {r.id: r for r in b_inst.rules}
    parts = [f"{n} {x}:{ra[x].aim} ~ {y}:{rb[y].aim}" for n, (x, y) in zip(("care", "control", "exit_bar"), cc.pairs())]
    return (f"care+control: {'; '.join(parts)}; subject {cc.subject_role[0]}~{cc.subject_role[1]}; "
            f"sub-signature {cc.matched}/{cc.n_a}|{cc.n_b} rules ({cc.coverage:.0%})")


def format_pair(rep: IsoReport) -> str:
    lines = [f"{rep.a} ~ {rep.b}: iso={rep.iso} pure_rename={rep.pure_rename} distance={rep.rule_distance} "
             f"matched={len(rep.matched_sub_signature)}/{rep.n_a}|{rep.n_b} strands={'on' if rep.with_strands else 'off'} "
             f"cond={rep.cond_level}"]
    lines.append("  matched: " + (", ".join(f"{x}->{y}" for x, y in rep.matched_sub_signature) or "-"))
    lines.append(f"  unmatched {rep.a}: {', '.join(rep.unmatched_a) or '-'}; {rep.b}: {', '.join(rep.unmatched_b) or '-'}")
    for kind in KINDS:
        moved = {k: v for k, v in rep.mapping[kind].items() if k != v}
        if moved:
            lines.append(f"  {kind} map: " + ", ".join(f"{k}->{v}" for k, v in moved.items()))
    for n in rep.notes:
        lines.append("  note: " + n)
    return "\n".join(lines)


def format_matrix(insts: list[InstitutionJSON], reps: dict, cell=None) -> str:
    """Matrix of rule edit distances (diagonal 0; `=` marks iso, `~` pure rename)."""
    ids = [i.id for i in insts]
    short = {i: i[:14] for i in ids}
    w = max(len(s) for s in short.values())
    hdr = " " * (w + 2) + " ".join(f"{short[j]:>{w}}" for j in ids)
    rows = [hdr]
    for i in ids:
        cells = []
        for j in ids:
            if i == j:
                cells.append(f"{'0':>{w}}")
                continue
            r = reps[(i, j)]
            tag = "~" if r.pure_rename else "=" if r.iso else ""
            cells.append(f"{tag + str(r.rule_distance) + '(' + str(len(r.matched_sub_signature)) + ')':>{w}}")
        rows.append(f"{short[i]:<{w}}  " + " ".join(cells))
    rows.append("cell = rule_distance(matched rules); '=' iso, '~' iso by pure rename")
    return "\n".join(rows)
