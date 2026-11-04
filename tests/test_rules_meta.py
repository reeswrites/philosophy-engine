"""Independent verification of rules_lower / rules_checks against philengine.rules_reference (brute force).

  differential   tiny institutions: reference verdict == engine verdict for every property x check x step_mode x k
  metamorphic    rename / add must_not / raise k / drop a may: verdict relations that must hold
  round trip     every counterexample trace the engine returns on the real dataset replays as a compliant trace

Tests on the real dataset are marked `slow` (not registered in conftest; run with `-m "not slow"` to skip).
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from philengine import rules_checks as rc
from philengine.rules_reference import Reference
from philengine.schemas_rules import InstitutionJSON, Property, load_institutions, load_properties

from .helpers import NO_DATASET, dataset_paths

slow = pytest.mark.slow
CHECKS = ("reachable", "invariant", "persists")


def P(name, formal):
    return Property(name=name, formal=formal)


# ---------------------------------------------------------------- tiny institutions
def inst_hire():
    """must with a standing obligation (pay while employed); untyped fluent `bonus` over every agent."""
    return InstitutionJSON.model_validate({
        "id": "t-hire",
        "roles": [{"name": "boss"}, {"name": "worker"}],
        "fluents": [{"name": "employed", "arity": 1, "arg_roles": ["worker"]},
                    {"name": "paid", "arity": 1, "arg_roles": ["worker"]},
                    {"name": "bonus", "arity": 1}],
        "actions": [
            {"name": "hire", "args": ["b", "w"], "arg_roles": ["boss", "worker"],
             "effects": [{"fluent": "employed", "args": ["w"], "value": True}]},
            {"name": "pay", "args": ["b", "w"], "arg_roles": ["boss", "worker"],
             "effects": [{"fluent": "paid", "args": ["w"], "value": True}]},
            {"name": "reward", "args": ["b", "x"], "arg_roles": ["boss", None],
             "effects": [{"fluent": "bonus", "args": ["x"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "boss", "deontic": "may", "aim": "(hire b w)", "conditions": "true", "strand": "rival"},
            {"id": "R2", "attribute": "boss", "deontic": "must", "aim": "(pay b w)", "conditions": "(employed w)",
             "or_else": "R3", "strand": "tying"},
            {"id": "R3", "attribute": "boss", "deontic": "may", "aim": "(reward b x)", "conditions": "(paid x)",
             "strand": "superadditive"},
        ],
    }), {
        "worker_paid": P("worker_paid", "(exists ((w agent)) (paid w t))"),
        "paid_if_employed": P("paid_if_employed", "(forall ((w agent)) (=> (employed w t) (paid w t)))"),
        "boss_bonus": P("boss_bonus", "(bonus boss t)"),
        "employed": P("employed", "(employed worker t)"),
    }


def inst_disability():
    """must_not with or_else null (disability): the animal may leave in general but never while owned."""
    return InstitutionJSON.model_validate({
        "id": "t-disability",
        "roles": [{"name": "owner"}, {"name": "animal"}],
        "fluents": [{"name": "owned", "arity": 2, "arg_roles": ["owner", "animal"]},
                    {"name": "free", "arity": 1, "arg_roles": ["animal"]}],
        "actions": [
            {"name": "acquire", "args": ["o", "a"], "arg_roles": ["owner", "animal"],
             "effects": [{"fluent": "owned", "args": ["o", "a"], "value": True},
                         {"fluent": "free", "args": ["a"], "value": False}]},
            {"name": "leave", "args": ["a"], "arg_roles": ["animal"],
             "effects": [{"fluent": "free", "args": ["a"], "value": True}]},
            {"name": "release", "args": ["o", "a"], "arg_roles": ["owner", "animal"],
             "effects": [{"fluent": "owned", "args": ["o", "a"], "value": False}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "owner", "deontic": "may", "aim": "(acquire o a)", "conditions": "(not (owned o a))", "strand": "rival"},
            {"id": "R2", "attribute": "animal", "deontic": "may", "aim": "(leave a)", "conditions": "true", "strand": "rival"},
            {"id": "R3", "attribute": "animal", "deontic": "must_not", "aim": "(leave a)", "conditions": "(owned owner a)",
             "or_else": None, "strand": "tying", "implicit": True},
            {"id": "R4", "attribute": "owner", "deontic": "may", "aim": "(release o a)", "conditions": "(owned o a)", "strand": "rival"},
        ],
    }), {
        "animal_free": P("animal_free", "(free animal t)"),
        "owned": P("owned", "(owned owner animal t)"),
        "owned_not_free": P("owned_not_free", "(=> (owned owner animal t) (not (free animal t)))"),
        "free_and_owned": P("free_and_owned", "(and (owned owner animal t) (free animal t))"),
    }


def inst_or_else():
    """must / must_not with or_else (sanction rule ids); a must whose condition has a free variable."""
    return InstitutionJSON.model_validate({
        "id": "t-or-else",
        "roles": [{"name": "officer"}, {"name": "subject"}, {"name": "clerk"}],
        "fluents": [{"name": "detained", "arity": 1, "arg_roles": ["subject"]},
                    {"name": "warned", "arity": 1, "arg_roles": ["subject"]},
                    {"name": "flag", "arity": 1},
                    {"name": "logged", "arity": 1, "arg_roles": ["subject"]}],
        "actions": [
            {"name": "detain", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "detained", "args": ["s"], "value": True}]},
            {"name": "warn", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "warned", "args": ["s"], "value": True}]},
            {"name": "resist", "args": ["s"], "arg_roles": ["subject"],
             "effects": [{"fluent": "flag", "args": ["s"], "value": True}]},
            {"name": "sanction", "args": ["o", "s"], "arg_roles": ["officer", "subject"],
             "effects": [{"fluent": "warned", "args": ["s"], "value": False}]},
            {"name": "log", "args": ["c", "s"], "arg_roles": ["clerk", "subject"],
             "effects": [{"fluent": "logged", "args": ["s"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "officer", "deontic": "may", "aim": "(detain o s)", "conditions": "true", "strand": "rival"},
            {"id": "R2", "attribute": "subject", "deontic": "may", "aim": "(resist s)", "conditions": "true", "strand": "rival"},
            {"id": "R3", "attribute": "subject", "deontic": "must_not", "aim": "(resist s)", "conditions": "(detained s)",
             "or_else": "R4", "strand": "tying"},
            {"id": "R4", "attribute": "officer", "deontic": "may", "aim": "(sanction o s)", "conditions": "(flag s)", "strand": "tying"},
            {"id": "R5", "attribute": "officer", "deontic": "must", "aim": "(warn o s)",
             "conditions": "(and (detained s) (not (warned s)))", "or_else": "R4", "strand": "tying"},
            {"id": "R6", "attribute": "clerk", "deontic": "must", "aim": "(log c s)",
             "conditions": "(and (flag q) (not (logged s)))", "var_roles": {"q": "subject"}, "or_else": None, "strand": "tying"},
        ],
    }), {
        "detained": P("detained", "(detained subject t)"),
        "warned_if_detained": P("warned_if_detained", "(=> (detained subject t) (warned subject t))"),
        "flag_any": P("flag_any", "(exists ((x agent)) (flag x t))"),
        "logged": P("logged", "(logged subject t)"),
        "warned": P("warned", "(warned subject t)"),
        "flag_then_logged": P("flag_then_logged",
                              "(=> (flag subject t) (exists ((t2 step)) (and (succ t t2) (logged subject t2))))"),
    }


def inst_initial():
    """initial + defaults (init mode `declared`); an action no rule names (fires freely, never (enabled ...))."""
    return InstitutionJSON.model_validate({
        "id": "t-initial",
        "roles": [{"name": "parent"}, {"name": "child"}],
        "fluents": [{"name": "is_subject", "arity": 1, "arg_roles": ["child"]},
                    {"name": "can_exit", "arity": 1, "arg_roles": ["child"]},
                    {"name": "cared", "arity": 2, "arg_roles": ["parent", "child"]},
                    {"name": "adult", "arity": 1, "arg_roles": ["child"]}],
        "actions": [
            {"name": "confine", "args": ["p", "c"], "arg_roles": ["parent", "child"],
             "effects": [{"fluent": "can_exit", "args": ["c"], "value": False}]},
            {"name": "care", "args": ["p", "c"], "arg_roles": ["parent", "child"],
             "effects": [{"fluent": "cared", "args": ["p", "c"], "value": True}]},
            {"name": "grow_up", "args": ["c"], "arg_roles": ["child"],
             "effects": [{"fluent": "adult", "args": ["c"], "value": True},
                         {"fluent": "is_subject", "args": ["c"], "value": False},
                         {"fluent": "can_exit", "args": ["c"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "parent", "deontic": "may", "aim": "(confine p c)", "conditions": "(is_subject c)", "strand": "tying"},
            {"id": "R2", "attribute": "parent", "deontic": "must", "aim": "(care p c)",
             "conditions": "(and (is_subject c) (not (cared p c)))", "or_else": None, "strand": "superadditive"},
        ],
        "defaults": {"can_exit": "true"},
        "initial": ["(is_subject child)"],
    }), {
        "cannot_exit": P("cannot_exit", "(exists ((s agent)) (and (is_subject s t) (not (can_exit s t))))"),
        "can_exit": P("can_exit", "(can_exit child t)"),
        "adult": P("adult", "(adult child t)"),
        "subject_cared": P("subject_cared", "(=> (is_subject child t) (cared parent child t))"),
        "subject": P("subject", "(is_subject child t)"),
    }


def inst_two_mays():
    """two may rules on one action (one per attribute), an exogenous free fluent (init `empty`)."""
    return InstitutionJSON.model_validate({
        "id": "t-two-mays",
        "roles": [{"name": "guard"}, {"name": "nurse"}, {"name": "patient"}],
        "fluents": [{"name": "calm", "arity": 1, "arg_roles": ["patient"]},
                    {"name": "treated", "arity": 1, "arg_roles": ["patient"]},
                    {"name": "held", "arity": 1, "arg_roles": ["patient"]}],
        "actions": [
            {"name": "treat", "args": ["x", "p"], "arg_roles": [None, "patient"],
             "effects": [{"fluent": "treated", "args": ["p"], "value": True}]},
            {"name": "hold", "args": ["x", "p"], "arg_roles": [None, "patient"],
             "effects": [{"fluent": "held", "args": ["p"], "value": True}]},
            {"name": "settle", "args": ["p"], "arg_roles": ["patient"],
             "effects": [{"fluent": "calm", "args": ["p"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "nurse", "deontic": "may", "aim": "(treat x p)", "conditions": "(calm p)", "strand": "superadditive"},
            {"id": "R2", "attribute": "guard", "deontic": "may", "aim": "(treat x p)", "conditions": "(held p)", "strand": "tying"},
            {"id": "R3", "attribute": "guard", "deontic": "may", "aim": "(hold x p)", "conditions": "(not (calm p))", "strand": "rival"},
            {"id": "R4", "attribute": "nurse", "deontic": "must_not", "aim": "(hold x p)", "conditions": "true", "or_else": None, "strand": "tying"},
            {"id": "R5", "attribute": "nurse", "deontic": "may", "aim": "(treat x p)", "conditions": "(held p)", "strand": "superadditive"},
        ],
    }), {
        "treated": P("treated", "(treated patient t)"),
        "held": P("held", "(held patient t)"),
        "treated_implies_calm": P("treated_implies_calm", "(=> (treated patient t) (calm patient t))"),
        "calm": P("calm", "(calm patient t)"),
        "held_and_calm": P("held_and_calm", "(and (held patient t) (calm patient t))"),
    }


def inst_or_else_bound():
    """inst_or_else with R6's condition written over the aim's own variable (no free condition variable):
    the free-variable reading is the only thing the two differ on."""
    inst, props = inst_or_else()
    d = inst.model_dump()
    d["id"] = "t-or-else-bound"
    r6 = next(r for r in d["rules"] if r["id"] == "R6")
    r6["conditions"] = "(and (flag s) (not (logged s)))"
    r6["var_roles"] = {}
    return InstitutionJSON.model_validate(d), props


def inst_state_rule():
    """A state obligation (aim head is a fluent, rules_lower docstring 'ADR 0009'): must cared(h, w) when married."""
    return InstitutionJSON.model_validate({
        "id": "t-state-rule",
        "roles": [{"name": "husband"}, {"name": "wife"}],
        "fluents": [{"name": "married", "arity": 2, "arg_roles": ["husband", "wife"]},
                    {"name": "cared", "arity": 2, "arg_roles": ["husband", "wife"]},
                    {"name": "rich", "arity": 1}],
        "actions": [
            {"name": "marry", "args": ["h", "w"], "arg_roles": ["husband", "wife"],
             "effects": [{"fluent": "married", "args": ["h", "w"], "value": True},
                         {"fluent": "cared", "args": ["h", "w"], "value": True}]},
            {"name": "neglect", "args": ["h", "w"], "arg_roles": ["husband", "wife"],
             "effects": [{"fluent": "cared", "args": ["h", "w"], "value": False}]},
            {"name": "divorce", "args": ["h", "w"], "arg_roles": ["husband", "wife"],
             "effects": [{"fluent": "married", "args": ["h", "w"], "value": False}]},
            {"name": "earn", "args": ["x"],
             "effects": [{"fluent": "rich", "args": ["x"], "value": True}]},
        ],
        "rules": [
            {"id": "R1", "attribute": "husband", "deontic": "may", "aim": "(marry h w)", "conditions": "(not (married h w))", "strand": "rival"},
            {"id": "R2", "attribute": "husband", "deontic": "must", "aim": "(cared h w)", "conditions": "(married h w)",
             "or_else": None, "strand": "superadditive"},
            {"id": "R3", "attribute": "husband", "deontic": "may", "aim": "(neglect h w)", "conditions": "true", "strand": "rival"},
            {"id": "R4", "attribute": "husband", "deontic": "may", "aim": "(divorce h w)", "conditions": "(married h w)", "strand": "rival"},
            {"id": "R5", "attribute": "wife", "deontic": "must_not", "aim": "(rich w)", "conditions": "(married husband w)",
             "or_else": None, "strand": "tying", "implicit": True},
        ],
    }), {
        "cared": P("cared", "(cared husband wife t)"),
        "married_cared": P("married_cared", "(=> (married husband wife t) (cared husband wife t))"),
        "married": P("married", "(married husband wife t)"),
        "wife_rich": P("wife_rich", "(rich wife t)"),
        "rich_and_married": P("rich_and_married", "(and (rich wife t) (married husband wife t))"),
        "anyone_rich": P("anyone_rich", "(exists ((x agent)) (rich x t))"),
    }


def inst_derived():
    """Derived power fluents (ADR 0013): can_sanction / can_exit computed from what the rules enable, with a
    disability barring exit in custody and an exogenous (initial_free) danger fluent."""
    from .test_rules_lower import derived_police
    return derived_police(), {
        "care_sanction": P("care_sanction", "(forall ((x agent) (y agent)) (=> (and (provides_care x y t) (is_subject y t)) (can_sanction x y t)))"),
        "can_sanction": P("can_sanction", "(can_sanction officer subject t)"),
        "cannot_exit": P("cannot_exit", "(exists ((s agent)) (and (is_subject s t) (not (can_exit s t))))"),
        "can_exit": P("can_exit", "(can_exit subject t)"),
        "custody_no_exit": P("custody_no_exit", "(=> (in_custody subject t) (not (can_exit subject t)))"),
        "custody": P("custody", "(in_custody subject t)"),
    }


TINY = [inst_hire, inst_disability, inst_or_else, inst_or_else_bound, inst_initial, inst_two_mays, inst_state_rule, inst_derived]


def test_reference_derived_fluents_pinned():
    """Hand-pinned verdicts for the derived fixture so the reference's `enabled` reading is not just whatever the
    engine says: power exists exactly when some rule enables detain or use_force; custody bars exit."""
    inst, props = inst_derived()
    ref = Reference(inst, k=3)
    assert ref.verdict(props["can_sanction"], "reachable") == "reachable"
    assert ref.verdict(props["care_sanction"], "invariant") == "violated"  # responding without danger: care, no power
    assert ref.verdict(props["custody_no_exit"], "invariant") == "holds_to_k"
    assert ref.verdict(props["can_exit"], "reachable") == "reachable"
    assert ref.verdict(props["cannot_exit"], "reachable") == "reachable"
    # derived fluents are never in a state and never appear in effects
    assert all(n not in ("can_sanction", "can_exit") for tr in ref.traces() for st in tr for n, _ in st)
    # an action no may/must rule names is never (enabled ...), though it may still fire (ADR 0013 amendment)
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] not in ("R3", "R4")]
    ref2 = Reference(InstitutionJSON.model_validate(d), k=3)
    assert ref2.verdict(props["can_sanction"], "reachable") == "open"
    act = ("use_force", ("officer", "subject"))
    states = {st for tr in ref2.traces() for st in tr}
    assert states and all(ref2.enabled(act, st) and not ref2.power(st, *act) for st in states)


def engine_verdicts(inst, props, k, step_mode="one", which=None):
    which = which or {n: list(CHECKS) for n in props}
    rep = rc.run_all(inst, props, k=k, which=which, step_mode=step_mode)
    assert not any("lowering failed" in w for w in rep.warnings), rep.warnings
    return rep, {(r.property, r.check): r.verdict for r in rep.results}


def reference_verdicts(inst, props, k, step_mode="one"):
    ref = Reference(inst, k=k, step_mode=step_mode)
    return ref, {(n, c): ref.verdict(p, c) for n, p in props.items() for c in CHECKS}


# ---------------------------------------------------------------- a. differential
@pytest.mark.parametrize("make", TINY, ids=[f.__name__ for f in TINY])
@pytest.mark.parametrize("step_mode", ["one", "many"])
@pytest.mark.parametrize("k", [2, 3, 4])
def test_differential_reference_vs_engine(make, step_mode, k):
    inst, props = make()
    rep, eng = engine_verdicts(inst, props, k, step_mode)
    ref, exp = reference_verdicts(inst, props, k, step_mode)
    diffs = {key: (exp[key], eng[key]) for key in exp if exp[key] != eng.get(key)}
    assert not diffs, f"(reference, engine) disagree: {diffs}; warnings={rep.warnings}"
    # the engine's own counterexample traces must replay under the reference
    for r in rep.results:
        if r.trace is not None:
            problems = ref.replay(r.trace, props[r.property], r.check)
            assert not problems, f"{inst.id} {r.property}/{r.check}: {problems}"


def test_reference_sanity_expected_values():
    """A few verdicts pinned by hand so a wrong reference cannot silently agree with a wrong engine."""
    inst, props = inst_disability()
    ref = Reference(inst, k=3)
    assert ref.verdict(props["free_and_owned"], "reachable") == "open"  # acquire clears free; leaving while owned is a disability
    assert ref.verdict(props["animal_free"], "reachable") == "reachable"
    assert ref.verdict(props["owned_not_free"], "invariant") == "holds_to_k"
    inst, props = inst_initial()
    ref = Reference(inst, k=3)
    assert ref.verdict(props["can_exit"], "reachable") == "reachable"  # default true at t=0
    assert ref.verdict(props["subject_cared"], "invariant") == "violated"  # not cared at t=0
    assert ref.verdict(props["subject"], "persists") == "fails"  # grow_up
    inst, props = inst_hire()
    ref = Reference(inst, k=3)
    assert ref.verdict(props["boss_bonus"], "reachable") == "open"  # reward needs paid(boss), boss is never paid


# ---------------------------------------------------------------- b. metamorphic
def rename(inst: InstitutionJSON, props: dict, mapping: dict[str, str]):
    """Consistent identifier rename across institution and properties (whole-token replacement)."""
    pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in mapping) + r")\b")

    def sub(text):
        return pat.sub(lambda m: mapping[m.group(1)], text)
    inst2 = InstitutionJSON.model_validate(json.loads(sub(json.dumps(inst.model_dump()))))
    props2 = {sub(n): Property.model_validate(json.loads(sub(json.dumps(p.model_dump())))) for n, p in props.items()}
    return inst2, props2


def _rename_map(inst: InstitutionJSON, suffix: bool):
    names = [r.name for r in inst.roles] + [f.name for f in inst.fluents] + [a.name for a in inst.actions]
    if suffix:  # keeps prefix-heuristic typing of variables intact (needed for the untyped dataset)
        return {n: n + "_q" for n in names}
    return {n: f"zz{i}_{n[::-1]}" for i, n in enumerate(names)}


@pytest.mark.parametrize("make", TINY, ids=[f.__name__ for f in TINY])
def test_rename_preserves_verdicts_tiny(make):
    inst, props = make()
    _, before = engine_verdicts(inst, props, 3)
    inst2, props2 = rename(inst, props, _rename_map(inst, suffix=False))
    m = _rename_map(inst, suffix=False)
    _, after = engine_verdicts(inst2, props2, 3)
    renamed_before = {(re.sub(r"\b(" + "|".join(map(re.escape, m)) + r")\b", lambda x: m[x.group(1)], n), c): v
                      for (n, c), v in before.items()}
    assert renamed_before == after


def _dataset():
    paths = dataset_paths()
    if paths is None:  # no dataset: the parametrized dataset tests collect empty and skip; the others skip below
        return [], {}
    ipath, ppath = paths
    return load_institutions(ipath), load_properties(ppath)


def _dataset_which(inst):
    return {n: [rc.check_for_expected(e) or "reachable"] for n, e in inst.expected_properties.items()}


@slow
@pytest.mark.parametrize("iid", [i.id for i in _dataset()[0]])
def test_rename_preserves_verdicts_dataset(iid):
    insts, props = _dataset()
    inst = next(i for i in insts if i.id == iid)
    which = _dataset_which(inst)
    _, before = engine_verdicts(inst, props, 4, which=which)
    m = _rename_map(inst, suffix=True)
    inst2, props2 = rename(inst, props, m)
    _, after = engine_verdicts(inst2, props2, 4, which={n + "_q" if n in m else n: c for n, c in which.items()})
    assert {(n, c): v for (n, c), v in before.items()} == {(n, c): v for (n, c), v in after.items()}


def _add_must_not(inst: InstitutionJSON) -> list[InstitutionJSON]:
    """One variant per may rule: a disability (must_not, or_else null, condition true) on that rule's aim."""
    out = []
    for r in inst.rules:
        if r.deontic != "may":
            continue
        d = inst.model_dump()
        d["rules"].append({"id": f"{r.id}_forbid", "attribute": r.attribute, "deontic": "must_not", "aim": r.aim,
                           "conditions": "true", "or_else": None, "strand": "tying", "var_roles": r.var_roles})
        out.append(InstitutionJSON.model_validate(d))
    return out


@pytest.mark.parametrize("make", [f for f in TINY if f is not inst_derived], ids=[f.__name__ for f in TINY if f is not inst_derived])
def test_adding_must_not_never_opens_reachability_tiny(make):
    """Not a law once fluents are derived from enabledness: a new disability turns (enabled ...) false, so a
    property over `not can_exit` can become reachable. inst_derived is excluded; test_disability_closes_derived_power
    pins the derived case."""
    inst, props = make()
    _, before = engine_verdicts(inst, props, 3)
    for v in _add_must_not(inst):
        _, after = engine_verdicts(v, props, 3)
        for (n, c), vb in before.items():
            if c == "reachable" and vb == "open":
                assert after[(n, c)] != "reachable", (v.rules[-1].id, n)
            if c == "invariant" and vb == "holds_to_k":
                assert after[(n, c)] != "violated", (v.rules[-1].id, n)
            if c == "persists" and vb == "persists":
                assert after[(n, c)] != "fails", (v.rules[-1].id, n)


def test_disability_closes_derived_power():
    """With derived power fluents, adding a disability on the enabling action removes the power: the metamorphic
    relation runs the other way for a property that asserts the power."""
    inst, props = inst_derived()
    _, before = engine_verdicts(inst, props, 3)
    assert before[("can_sanction", "reachable")] == "reachable"
    d = inst.model_dump()
    for rid in ("R3", "R4"):
        r = next(x for x in d["rules"] if x["id"] == rid)
        d["rules"].append({"id": f"{rid}_forbid", "attribute": r["attribute"], "deontic": "must_not", "aim": r["aim"],
                           "conditions": "true", "or_else": None, "strand": "tying"})
    _, after = engine_verdicts(InstitutionJSON.model_validate(d), props, 3)
    assert after[("can_sanction", "reachable")] == "open"
    assert after[("care_sanction", "invariant")] == "violated"


@slow
@pytest.mark.parametrize("iid", [i.id for i in _dataset()[0]])
def test_adding_must_not_never_opens_reachability_dataset(iid):
    insts, props = _dataset()
    inst = next(i for i in insts if i.id == iid)
    if inst.derived_fluents():
        pytest.skip("not a law for institutions with derived power fluents (a disability removes a power)")
    which = _dataset_which(inst)
    _, before = engine_verdicts(inst, props, 4, which=which)
    for v in _add_must_not(inst):
        _, after = engine_verdicts(v, props, 4, which=which)
        for key, vb in before.items():
            if vb == "open":
                assert after[key] != "reachable", (v.rules[-1].id, key)
            if vb == "holds_to_k":
                assert after[key] != "violated", (v.rules[-1].id, key)
            if vb == "persists":
                assert after[key] != "fails", (v.rules[-1].id, key)


@pytest.mark.parametrize("make", TINY, ids=[f.__name__ for f in TINY])
def test_raising_k_never_closes_reachability_tiny(make):
    inst, props = make()
    prev = None
    for k in (1, 2, 3, 4):
        _, now = engine_verdicts(inst, props, k)
        if prev is not None:
            for (n, c), v in prev.items():
                if c == "reachable" and v == "reachable":
                    assert now[(n, c)] == "reachable", f"{inst.id} {n}: reachable at k={k - 1}, {now[(n, c)]} at k={k}"
                if c == "invariant" and v == "violated":
                    assert now[(n, c)] == "violated", f"{inst.id} {n}: violated at k={k - 1}, {now[(n, c)]} at k={k}"
        prev = now


@slow
@pytest.mark.parametrize("iid", [i.id for i in _dataset()[0]])
def test_raising_k_never_closes_reachability_dataset(iid):
    insts, props = _dataset()
    inst = next(i for i in insts if i.id == iid)
    which = _dataset_which(inst)
    prev = None
    for k in (2, 4, 6):
        _, now = engine_verdicts(inst, props, k, which=which)
        if prev is not None:
            for key, v in prev.items():
                if v == "reachable":
                    assert now[key] == "reachable", f"{inst.id} {key}: reachable at smaller k, {now[key]} at k={k}"
                if v == "violated":
                    assert now[key] == "violated", f"{inst.id} {key}: violated at smaller k, {now[key]} at k={k}"
                if v == "fails":
                    assert now[key] == "fails", f"{inst.id} {key}: fails at smaller k, {now[key]} at k={k}"
        prev = now


def _droppable_mays(inst: InstitutionJSON) -> list[InstitutionJSON]:
    """Variants with one may rule removed, only where the action keeps another may/must rule with the same
    attribute (so the action neither becomes 'always enabled' nor loses its attribute scope)."""
    out = []
    for r in inst.rules:
        if r.deontic != "may":
            continue
        act = r.aim.strip("() ").split()[0]
        others = [x for x in inst.rules if x.id != r.id and x.deontic in ("may", "must")
                  and x.aim.strip("() ").split()[0] == act and x.attribute == r.attribute]
        if not others:
            continue
        d = inst.model_dump()
        d["rules"] = [x for x in d["rules"] if x["id"] != r.id]
        out.append((r.id, InstitutionJSON.model_validate(d)))
    return out


def test_removing_a_may_never_adds_reachable_tiny():
    inst, props = inst_two_mays()
    variants = _droppable_mays(inst)
    assert variants, "fixture should have a droppable may rule"
    _, before = engine_verdicts(inst, props, 3)
    for rid, v in variants:
        _, after = engine_verdicts(v, props, 3)
        for (n, c), vb in before.items():
            if c == "reachable" and vb == "open":
                assert after[(n, c)] != "reachable", (rid, n)


@slow
def test_removing_a_may_never_adds_reachable_dataset():
    insts, props = _dataset()
    if not insts:
        pytest.skip(NO_DATASET)
    seen = 0
    for inst in insts:
        which = _dataset_which(inst)
        variants = _droppable_mays(inst)
        if not variants:
            continue
        _, before = engine_verdicts(inst, props, 4, which=which)
        for rid, v in variants:
            seen += 1
            _, after = engine_verdicts(v, props, 4, which=which)
            for key, vb in before.items():
                if vb == "open":
                    assert after[key] != "reachable", (inst.id, rid, key)
    if seen == 0:
        pytest.skip("no may rule in the dataset is droppable without changing the action's enabledness regime")


# ---------------------------------------------------------------- c. round trip on the dataset
def _dataset_results():
    insts, props = _dataset()
    rows = []
    for inst in insts:
        rep = rc.run_all(inst, props, k=6, which=_dataset_which(inst))
        for r in rep.results:
            rows.append((inst, props, rep, r))
    return rows


@slow
def test_round_trip_counterexample_traces():
    insts, props = _dataset()
    if not insts:
        pytest.skip(NO_DATASET)
    problems = []
    seen = 0
    for inst in insts:
        rep = rc.run_all(inst, props, k=6, which=_dataset_which(inst))
        assert rep.compliance == "strict" and rep.step_mode == "one"
        ref = Reference(inst, k=rep.bound_k, init=rep.init, step_mode=rep.step_mode)
        for r in rep.results:
            if r.verdict in ("reachable", "violated", "fails"):
                assert r.trace is not None, f"{inst.id} {r.property}/{r.check}: {r.verdict} without a trace"
                seen += 1
                bad = ref.replay(r.trace, props[r.property], r.check)
                if bad:
                    problems.append((inst.id, r.property, r.check, r.verdict, bad))
    assert seen > 0
    assert not problems, "\n".join(f"{i} {p}/{c} ({v}): {b}" for i, p, c, v, b in problems)
