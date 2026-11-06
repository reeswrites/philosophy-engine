"""Derived obligation fluents (plans/priority-slice2.md revision 3, R3.2; ADR 0013 amendment "derived obligation
fluents"): `(obliged AIM args)` inside a derived definition, in the engine (rules_lower.Grounded.obliged) and in the
reference (rules_reference.Reference.obligation). Tests O1, O2, O4 (a)-(c), O6 here; O3 (differential), O4 (d) rename
and O4 (e) polarity in tests/test_rules_meta.py. Mutations MO1-MO6 (record: the engine commit) are each killed below.

The fixture `ward()`: a carer, a ward and a boss. R2 is a sanctioned must-be (tended, or_else R9), R3 an unsanctioned
must-be (safe), R4 an action duty (feed) whose condition has a free variable q (alarm q, over every agent), R5 a may
(neglect), R6 a disability on R4's instance (must_not feed while busy), `rest` a default-capacity action no rule names.
Hand pins, in every state: must_tend = must_safe = enrolled(ward); must_feed = enrolled(ward) and some alarm;
must_neglect, must_rest and feed_reversed (not an instance) are false.
"""
import itertools

import pytest

from philengine import rules_checks as rc
from philengine import rules_lower as rl
from philengine.rules_reference import Reference
from philengine.schemas_rules import InstitutionJSON, Property

K = 3


def act(name, args, roles, *effects, **kw):
    return {"name": name, "args": args, "arg_roles": roles, **kw,
            "effects": [{"fluent": f, "args": a, "value": v} for f, a, v in effects]}


def rule(id_, attr, deontic, aim, cond="true", or_else=None, strand="tying"):
    r = {"id": id_, "attribute": attr, "deontic": deontic, "aim": aim, "conditions": cond, "strand": strand}
    if deontic != "may":
        r["or_else"] = or_else
    return r


DERIVED = [
    {"name": "must_tend", "arity": 2, "arg_roles": ["carer", "ward"], "params": ["c", "w"], "derived": "(obliged tended c w)"},
    {"name": "must_safe", "arity": 1, "arg_roles": ["ward"], "params": ["w"], "derived": "(obliged safe w)"},
    {"name": "must_feed", "arity": 2, "arg_roles": ["carer", "ward"], "params": ["c", "w"], "derived": "(obliged feed c w)"},
    {"name": "must_neglect", "arity": 2, "arg_roles": ["carer", "ward"], "params": ["c", "w"],
     "derived": "(obliged neglect c w)"},
    {"name": "must_rest", "arity": 1, "arg_roles": ["carer"], "params": ["c"], "derived": "(obliged rest c)"},
    {"name": "feed_reversed", "arity": 0, "params": [], "derived": "(obliged feed ward carer)"},
]


def ward_dict(or_else_r2="R9"):
    return {
        "id": "t-obliged",
        "roles": [{"name": "carer"}, {"name": "ward"}, {"name": "boss"}],
        "fluents": [{"name": "enrolled", "arity": 1, "arg_roles": ["ward"]},
                    {"name": "tended", "arity": 2, "arg_roles": ["carer", "ward"]},
                    {"name": "safe", "arity": 1, "arg_roles": ["ward"]},
                    {"name": "alarm", "arity": 1},
                    {"name": "busy", "arity": 0}] + DERIVED,
        "actions": [
            act("enrol", ["c", "w"], ["carer", "ward"], ("enrolled", ["w"], True), ("tended", ["c", "w"], True),
                ("safe", ["w"], True)),
            act("leave", ["w"], ["ward"], ("enrolled", ["w"], False)),
            act("tend", ["c", "w"], ["carer", "ward"], ("tended", ["c", "w"], True)),
            act("neglect", ["c", "w"], ["carer", "ward"], ("tended", ["c", "w"], False)),
            act("make_safe", ["c", "w"], ["carer", "ward"], ("safe", ["w"], True)),
            act("endanger", ["c", "w"], ["carer", "ward"], ("safe", ["w"], False)),
            act("feed", ["c", "w"], ["carer", "ward"]),
            act("raise", ["b", "x"], ["boss", None], ("alarm", ["x"], True)),
            act("rest", ["c"], ["carer"], ("busy", [], True), default_capacity=True),
            act("scold", ["b", "c"], ["boss", "carer"]),
        ],
        "rules": [
            rule("R1", "carer", "may", "(enrol c w)"),
            rule("R2", "carer", "must", "(tended c w)", "(enrolled w)", or_else_r2),
            rule("R3", "carer", "must", "(safe w)", "(enrolled w)", None),
            rule("R4", "carer", "must", "(feed c w)", "(and (enrolled w) (alarm q))", None),
            rule("R5", "carer", "may", "(neglect c w)"),
            rule("R6", "carer", "must_not", "(feed c w)", "busy", None),
            rule("R7", "ward", "may", "(leave w)"),
            rule("R8", "boss", "may", "(raise b x)"),
            rule("R9", "boss", "may", "(scold b c)"),
            rule("R10", "carer", "may", "(tend c w)"),
            rule("R11", "carer", "may", "(make_safe c w)"),
            rule("R12", "carer", "may", "(endanger c w)"),
        ],
        "expected_properties": {},
        "initial": [],
    }


def ward(**kw) -> InstitutionJSON:
    return InstitutionJSON.model_validate(ward_dict(**kw))


def hand(state) -> dict:
    """The hand pins: derived fluent (with its one typed tuple) -> value in a state."""
    enrolled = ("enrolled", ("ward",)) in state
    alarm = any(("alarm", (a,)) in state for a in ("carer", "ward", "boss"))
    return {("must_tend", ("carer", "ward")): enrolled, ("must_safe", ("ward",)): enrolled,
            ("must_feed", ("carer", "ward")): enrolled and alarm, ("must_neglect", ("carer", "ward")): False,
            ("must_rest", ("carer",)): False, ("feed_reversed", ()): False}


def all_states(ref: Reference):
    atoms = sorted(ref.all_atoms)
    for bits in itertools.product([False, True], repeat=len(atoms)):
        yield frozenset(a for a, b in zip(atoms, bits) if b)


def obliged_values(ref: Reference, state) -> dict:
    return {(n, tup): ref.atom(state, n, tup) for n, tup in hand(frozenset())}


def P(name, formal):
    return Property(name=name, kind="structure", formal=formal)


PINS = {  # invariant: the derived fluent equals its hand formula at every step of every compliant trace
    "tend_iff": P("tend_iff", "(iff (must_tend carer ward t) (enrolled ward t))"),
    "safe_iff": P("safe_iff", "(iff (must_safe ward t) (enrolled ward t))"),
    "feed_iff": P("feed_iff", "(iff (must_feed carer ward t) (and (enrolled ward t) (exists ((q agent)) (alarm q t))))"),
    "neglect_never": P("neglect_never", "(not (must_neglect carer ward t))"),
    "rest_never": P("rest_never", "(not (must_rest carer t))"),
    "reversed_never": P("reversed_never", "(not (feed_reversed t))"),
}
PROBES = {  # reachable (each pin is non-vacuous: both values occur)
    "tend_true": P("tend_true", "(must_tend carer ward t)"),
    "tend_false": P("tend_false", "(not (must_tend carer ward t))"),
    "feed_true": P("feed_true", "(must_feed carer ward t)"),
    "feed_enrolled_no_alarm": P("feed_enrolled_no_alarm", "(and (enrolled ward t) (not (must_feed carer ward t)))"),
    # MO5: the free variable q is existential, not fixed to its first binding (carer)
    "feed_by_ward_alarm": P("feed_by_ward_alarm", "(and (must_feed carer ward t) (alarm ward t) (not (alarm carer t)))"),
    # MO2: the disability R6 on R4's instance does not cancel the obligation (reached at step k)
    "feed_while_busy": P("feed_while_busy", "(and (must_feed carer ward t) (busy t))"),
}


def _engine(inst, props, which, compliance="strict", k=K):
    rep = rc.run_all(inst, props, k=k, which=which, compliance=compliance)
    assert not any("lowering failed" in w for w in rep.warnings), rep.warnings
    return rep, {r.property: r.verdict for r in rep.results}


# ------------------------------------------------------------------ O1 pinned semantics, engine and reference
def test_O1_reference_pins_in_every_state():
    ref = Reference(ward(), k=K)
    n = 0
    for st in all_states(ref):
        assert obliged_values(ref, st) == hand(st), sorted(st)
        n += 1
    assert n == 2 ** len(ref.all_atoms) and n >= 64
    # the pseudo-predicate itself, directly
    st = frozenset({("enrolled", ("ward",)), ("alarm", ("ward",)), ("busy", ())})
    assert ref.obligation(st, "feed", ("carer", "ward")) is True  # a disability on the instance does not cancel it
    assert ref.obligation(st, "neglect", ("carer", "ward")) is False  # may never obliges
    assert ref.obligation(st, "feed", ("ward", "carer")) is False  # not an instance
    assert ref.obligation(st, "tended", ("carer", "ward")) is True  # state aim
    assert ref.obligation(frozenset(), "tended", ("carer", "ward")) is False  # condition false


def test_O1_reference_pins_along_every_trace():
    ref = Reference(ward(), k=K)
    trs = ref.traces()
    assert trs
    seen = set()
    for tr in trs:
        for st in tr:
            got = obliged_values(ref, st)
            assert got == hand(st)
            seen |= {(k_, v) for k_, v in got.items()}
    # both values of every obliged fluent that can be true occur on some trace
    for name in ("must_tend", "must_safe", "must_feed"):
        assert any(k_[0] == name and v for k_, v in seen) and any(k_[0] == name and not v for k_, v in seen), name


def test_O1_engine_pins_and_probes():
    rep, v = _engine(ward(), {**PINS, **PROBES}, {**{n: ["invariant"] for n in PINS}, **{n: ["reachable"] for n in PROBES}})
    assert {n: v[n] for n in PINS} == {n: "holds_to_k" for n in PINS}
    assert {n: v[n] for n in PROBES} == {n: "reachable" for n in PROBES}
    # the reference agrees on every probe
    ref = Reference(ward(), k=K)
    assert {n: ref.verdict(p, "invariant") for n, p in PINS.items()} == {n: "holds_to_k" for n in PINS}
    assert {n: ref.verdict(p, "reachable") for n, p in PROBES.items()} == {n: "reachable" for n in PROBES}
    # warnings: an aim no must names is never obliged. (R4/R6 is a deontic conflict, but check_deontic_conflict lowers a
    # condition with its free variable unbound, so it does not report this pair: a pre-existing limit, recorded in the
    # revision-3 results ("Revision 3 fix pass", known limit 1; rules_lower module doc), not changed here.)
    for aim in ("neglect", "rest"):
        assert any(f"(obliged {aim} ...) names an aim no `must` rule names" in w for w in rep.warnings), rep.warnings
    assert not any("(obliged feed ...)" in w or "(obliged tended ...)" in w for w in rep.warnings)


def test_O1_engine_lowering_pointwise():
    """Grounded.obliged itself, per step: constant false for a non-instance, a may, an unnamed aim."""
    import z3
    G = rl.ground(ward(), k=K)
    for t in range(K + 1):
        for aim, args in (("feed", ("ward", "carer")), ("neglect", ("carer", "ward")), ("rest", ("carer",)),
                          ("tended", ("ward", "carer"))):
            assert z3.is_false(z3.simplify(G.obliged(aim, args, t))), (aim, args, t)
    s = z3.Solver()
    s.add(G.system())
    s.add(G.fluent("enrolled", ("ward",), 2), z3.Not(G.obliged("tended", ("carer", "ward"), 2)))
    assert s.check() == z3.unsat


# ------------------------------------------------------------------ O2 sanctioned vs unsanctioned
def test_O2_or_else_plays_no_part_in_obliged():
    ref_s, ref_u = Reference(ward(or_else_r2="R9"), k=K), Reference(ward(or_else_r2=None), k=K)
    for st in all_states(ref_s):
        assert obliged_values(ref_s, st) == obliged_values(ref_u, st)


BREACH = {"tend_breach": P("tend_breach", "(and (must_tend carer ward t) (not (tended carer ward t)))"),
          "safe_breach": P("safe_breach", "(and (must_safe ward t) (not (safe ward t)))")}


@pytest.mark.parametrize("or_else", ["R9", None])
def test_O2_breach_reachable_only_for_a_sanctioned_must_be_under_sanctioned_compliance(or_else):
    which = {n: ["reachable"] for n in BREACH}
    _, strict = _engine(ward(or_else_r2=or_else), BREACH, which)
    assert strict == {"tend_breach": "open", "safe_breach": "open"}  # a state duty is met at the same step
    _, sanc = _engine(ward(or_else_r2=or_else), BREACH, which, compliance="sanctioned")
    assert sanc == {"tend_breach": "reachable" if or_else else "open", "safe_breach": "open"}
    # obliged reads the rules and the state, not the compliance mode: the pins hold under sanctioned too
    _, v = _engine(ward(or_else_r2=or_else), PINS, {n: ["invariant"] for n in PINS}, compliance="sanctioned")
    assert set(v.values()) == {"holds_to_k"}


def test_O2b_obliged_lowering_is_the_same_under_sanctioned_compliance():
    """Second pin for "independent of the compliance mode" (revision-3 correctness review finding 6, mutant OWN6:
    obliged drops sanctioned musts under compliance="sanctioned"). Grounded.obliged itself, pointwise: in a system
    grounded under sanctioned compliance, R2's sanctioned must (tended, or_else R9) and R3's unsanctioned one
    (safe) both oblige whenever the ward is enrolled, at every step, and the probes keep their verdicts."""
    import z3
    for compliance in ("strict", "sanctioned"):
        G = rl.ground(ward(or_else_r2="R9"), k=K, compliance=compliance)
        for t in range(K + 1):
            for aim, args in (("tended", ("carer", "ward")), ("safe", ("ward",))):
                s = z3.Solver()
                s.add(G.system())
                s.add(G.fluent("enrolled", ("ward",), t), z3.Not(G.obliged(aim, args, t)))
                assert s.check() == z3.unsat, (compliance, aim, t)
    _, v = _engine(ward(or_else_r2="R9"), PROBES, {n: ["reachable"] for n in PROBES}, compliance="sanctioned")
    assert v == {n: "reachable" for n in PROBES}


# ------------------------------------------------------------------ O1b instance arguments
def _ward_with_alarm_duty():
    """ward() plus a must-be on one tuple of the untyped fluent alarm (R13: the boss must keep (alarm ward) while
    busy) and a derived must_alarm(x) := (obliged alarm x) over all three agents."""
    d = ward_dict()
    d["fluents"] = d["fluents"] + [{"name": "must_alarm", "arity": 1, "params": ["x"], "derived": "(obliged alarm x)"}]
    d["rules"] = d["rules"] + [rule("R13", "boss", "must", "(alarm ward)", "busy", None)]
    return InstitutionJSON.model_validate(d)


def test_O1b_instance_arguments_select_the_obliged_tuple():
    """Second pin for instance arguments (revision-3 correctness review finding 6, mutant OWN3: any must on the aim
    obliges every tuple). Only (alarm ward) is obliged, and only while busy; (alarm carer) and (alarm boss), tuples of
    the same fluent, never are. Engine and reference."""
    inst = _ward_with_alarm_duty()
    pins = {"ward_iff_busy": P("ward_iff_busy", "(iff (must_alarm ward t) (busy t))"),
            "carer_never": P("carer_never", "(not (must_alarm carer t))"),
            "boss_never": P("boss_never", "(not (must_alarm boss t))")}
    probes = {"ward_obliged": P("ward_obliged", "(must_alarm ward t)"),
              "busy_carer_unobliged": P("busy_carer_unobliged", "(and (busy t) (not (must_alarm carer t)))")}
    _, v = _engine(inst, {**pins, **probes}, {**{n: ["invariant"] for n in pins}, **{n: ["reachable"] for n in probes}})
    assert v == {**{n: "holds_to_k" for n in pins}, **{n: "reachable" for n in probes}}
    ref = Reference(inst, k=K)
    for st in all_states(ref):
        busy = ("busy", ()) in st
        assert ref.obligation(st, "alarm", ("ward",)) is busy
        assert ref.obligation(st, "alarm", ("carer",)) is False
        assert ref.obligation(st, "alarm", ("boss",)) is False


# ------------------------------------------------------------------ O4 metamorphic and pointwise laws (a)-(c)
def _with(d, **kw):
    return InstitutionJSON.model_validate({**d, **kw})


def test_O4a_adding_a_must_ors_its_condition_into_obliged():
    d = ward_dict()
    ref0 = Reference(ward(), k=K)
    ref1 = Reference(_with(d, rules=d["rules"] + [rule("R13", "carer", "must", "(neglect c w)", "busy")]), k=K)
    ref2 = Reference(_with(d, rules=d["rules"] + [rule("R13", "carer", "must", "(tended c w)", "(alarm ward)")]), k=K)
    for st in all_states(ref0):
        a, b, c = obliged_values(ref0, st), obliged_values(ref1, st), obliged_values(ref2, st)
        key = ("must_neglect", ("carer", "ward"))
        assert b[key] == (a[key] or ("busy", ()) in st)
        assert {x: y for x, y in b.items() if x != key} == {x: y for x, y in a.items() if x != key}
        key = ("must_tend", ("carer", "ward"))
        assert c[key] == (a[key] or ("alarm", ("ward",)) in st)
        assert {x: y for x, y in c.items() if x != key} == {x: y for x, y in a.items() if x != key}
    # the engine agrees on the added must (R13 on neglect while busy)
    p = {"neglect_iff_busy": P("neglect_iff_busy", "(iff (must_neglect carer ward t) (busy t))")}
    _, v = _engine(_with(d, rules=d["rules"] + [rule("R13", "carer", "must", "(neglect c w)", "busy")]), p,
                   {"neglect_iff_busy": ["invariant"]})
    assert v == {"neglect_iff_busy": "holds_to_k"}


def test_O4b_deleting_a_must_never_makes_obliged_true():
    d = ward_dict()
    ref0 = Reference(ward(), k=K)
    for rid in [r["id"] for r in d["rules"] if r["deontic"] == "must"]:
        rules = [r for r in d["rules"] if r["id"] != rid]
        ref1 = Reference(_with(d, rules=rules), k=K)
        changed = False
        for st in all_states(ref0):
            a, b = obliged_values(ref0, st), obliged_values(ref1, st)
            assert all(a[x] or not b[x] for x in a), (rid, sorted(st))
            changed |= a != b
        assert changed, rid  # deleting a must makes its instances unobliged somewhere


def test_O4c_default_capacity_never_changes_obliged():
    d = ward_dict()
    ref0 = Reference(ward(), k=K)
    for a in d["actions"]:
        acts = [dict(x, default_capacity=not x.get("default_capacity", False)) if x["name"] == a["name"] else x
                for x in d["actions"]]
        ref1 = Reference(_with(d, actions=acts), k=K)
        for st in all_states(ref0):
            assert obliged_values(ref0, st) == obliged_values(ref1, st), a["name"]
    # engine: the pins hold with every action's default_capacity flipped
    acts = [dict(x, default_capacity=not x.get("default_capacity", False)) for x in d["actions"]]
    _, v = _engine(_with(d, actions=acts), PINS, {n: ["invariant"] for n in PINS})
    assert set(v.values()) == {"holds_to_k"}


# ------------------------------------------------------------------ O6 loader
def _derived_err(derived, params=("c", "w"), arity=2, roles=("carer", "ward")):
    d = ward_dict()
    d["fluents"] = d["fluents"] + [{"name": "probe", "arity": arity, "arg_roles": list(roles) if roles else None,
                                    "params": list(params), "derived": derived}]
    return "\n".join(rl.validate_institution(InstitutionJSON.model_validate(d)))


def test_O6_loader_rejections():
    assert _derived_err("(obliged tended c w)") == ""
    assert "(obliged nurse ...): not a declared action or fluent" in _derived_err("(obliged nurse c w)")
    assert "'must_tend' is a derived fluent" in _derived_err("(obliged must_tend c w)")
    assert "'feed' takes 2 argument(s), got 1" in _derived_err("(obliged feed c)")
    assert "'safe' takes 1 argument(s), got 2" in _derived_err("(obliged safe c w)")
    assert "'q' is neither a param, a role nor a bound variable" in _derived_err("(obliged feed c q)")
    assert "parse error" in _derived_err("(obliged)")  # rejected by the parser already
    # inside a rule condition
    d = ward_dict()
    d["rules"][4] = rule("R5", "carer", "may", "(neglect c w)", "(obliged tended c w)")
    errs = "\n".join(rl.validate_institution(InstitutionJSON.model_validate(d)))
    assert "(obliged ...) is only available inside a derived fluent's definition" in errs
    # inside a property formula: an error, not an undeclared-fluent warning lowered as false
    for f in ("(obliged tended carer ward t)", "(enabled feed carer ward t)"):
        errs, warns = rl.validate_property(P("x", f), ward())
        assert any("is only available inside a derived fluent's definition" in e for e in errs), (f, errs)
        assert not warns
    # a fluent may not be named obliged
    d = ward_dict()
    d["fluents"] = d["fluents"] + [{"name": "obliged", "arity": 0}]
    assert "invalid fluent name 'obliged'" in "\n".join(rl.validate_institution(InstitutionJSON.model_validate(d)))
    # a cycle through a must condition
    d = ward_dict()
    d["rules"][1] = rule("R2", "carer", "must", "(tended c w)", "(and (enrolled w) (must_tend c w))", "R9")
    errs = "\n".join(rl.validate_institution(InstitutionJSON.model_validate(d)))
    assert "derived fluents are cyclic: must_tend -> must_tend" in errs
    # ... but a may/must_not condition reading it is not a cycle for obliged (only must conditions are read)
    d = ward_dict()
    d["rules"][5] = rule("R6", "carer", "must_not", "(feed c w)", "(and busy (must_tend c w))", None)
    assert rl.validate_institution(InstitutionJSON.model_validate(d)) == []
    with pytest.raises(rl.LowerError, match="cyclic"):
        d = ward_dict()
        d["rules"][3] = rule("R4", "carer", "must", "(feed c w)", "(and (enrolled w) (alarm q) (must_feed c w))", None)
        rl.ground(InstitutionJSON.model_validate(d), k=2)


# ------------------------------------------------------------------ fixtures for tests/test_rules_meta.py (O3, O4 d-e)
def inst_obliged_household():
    """Coverture's shape (R3.2): both spouses obliged to care while married (R2 unsanctioned, R3 sanctioned by R5),
    the wife barred from leaving while married (R6), `care_obliged` derived; `misbehave` lets R5's sanction fire."""
    return InstitutionJSON.model_validate({
        "id": "t-obliged-household",
        "roles": [{"name": "husband"}, {"name": "wife"}],
        "fluents": [{"name": "married", "arity": 2, "arg_roles": ["husband", "wife"]},
                    {"name": "provides_care", "arity": 2},
                    {"name": "misbehaves", "arity": 1, "arg_roles": ["wife"]},
                    {"name": "care_obliged", "arity": 2, "params": ["x", "y"], "derived": "(obliged provides_care x y)"},
                    {"name": "can_exit", "arity": 1, "arg_roles": ["wife"], "params": ["w"], "derived": "(enabled leave w)"}],
        "actions": [
            act("marry", ["h", "w"], ["husband", "wife"], ("married", ["h", "w"], True), ("provides_care", ["h", "w"], True),
                ("provides_care", ["w", "h"], True)),
            act("misbehave", ["w"], ["wife"], ("misbehaves", ["w"], True)),
            act("chastise", ["h", "w"], ["husband", "wife"]),
            act("leave", ["w"], ["wife"], ("married", ["x", "w"], False)),
        ],
        "rules": [
            rule("R1", "husband", "may", "(marry h w)", "(not (married h w))"),
            rule("R2", "husband", "must", "(provides_care h w)", "(married h w)", None, "superadditive"),
            rule("R3", "wife", "must", "(provides_care w h)", "(married h w)", "R5", "superadditive"),
            rule("R5", "husband", "may", "(chastise h w)", "(misbehaves w)", strand="rival"),
            rule("R6", "wife", "must_not", "(leave w)", "(married husband w)", None),
            rule("R7", "wife", "may", "(misbehave w)"),
            rule("R8", "wife", "may", "(leave w)"),
        ],
        "expected_properties": {},
        "initial": [],
    }), {
        # R3.2 O5 writes (married h w t) on the left; over every ordered pair that is false for (wife, husband) while
        # both duties hold, so the pin reads the marriage in either order (drift recorded with the dataset pin)
        "mutual_obliged": P("mutual_obliged", "(forall ((h agent) (w agent)) (iff (or (married h w t) (married w h t)) "
                                              "(and (care_obliged h w t) (care_obliged w h t))))"),
        "mutual_obliged_as_written": P("mutual_obliged_as_written", "(forall ((h agent) (w agent)) (iff (married h w t) "
                                                                    "(and (care_obliged h w t) (care_obliged w h t))))"),
        "wife_obliged": P("wife_obliged", "(care_obliged wife husband t)"),
        "obliged_not_caring": P("obliged_not_caring", "(and (care_obliged wife husband t) (not (provides_care wife husband t)))"),
        "chosen": P("chosen", "(=> (married husband wife t) (and (provides_care wife husband t) "
                              "(not (care_obliged wife husband t)) (can_exit wife t)))"),
        "reversed": P("reversed", "(care_obliged wife wife t)"),
    }


def inst_obliged_action():
    """An action duty with a free condition variable (feed while enrolled and some alarm), a disability on its
    instance while busy, a may (enrol) and a default-capacity action (rest) that no must names."""
    return InstitutionJSON.model_validate({
        "id": "t-obliged-action",
        "roles": [{"name": "carer"}, {"name": "ward"}, {"name": "boss"}],
        "fluents": [{"name": "enrolled", "arity": 1, "arg_roles": ["ward"]},
                    {"name": "alarm", "arity": 1},
                    {"name": "busy", "arity": 0},
                    {"name": "must_feed", "arity": 2, "arg_roles": ["carer", "ward"], "params": ["c", "w"],
                     "derived": "(obliged feed c w)"},
                    {"name": "must_enrol", "arity": 2, "arg_roles": ["carer", "ward"], "params": ["c", "w"],
                     "derived": "(or (obliged enrol c w) (obliged rest c))"}],
        "actions": [
            act("enrol", ["c", "w"], ["carer", "ward"], ("enrolled", ["w"], True)),
            act("feed", ["c", "w"], ["carer", "ward"]),
            act("raise", ["b", "x"], ["boss", None], ("alarm", ["x"], True)),
            act("rest", ["c"], ["carer"], ("busy", [], True), default_capacity=True),
        ],
        "rules": [
            rule("R1", "carer", "may", "(enrol c w)"),
            rule("R4", "carer", "must", "(feed c w)", "(and (enrolled w) (alarm q))", None),
            rule("R6", "carer", "must_not", "(feed c w)", "busy", None),
            rule("R8", "boss", "may", "(raise b x)"),
        ],
        "expected_properties": {},
        "initial": [],
    }), {
        "feed_iff": P("feed_iff", "(iff (must_feed carer ward t) (and (enrolled ward t) (exists ((q agent)) (alarm q t))))"),
        "feed": P("feed", "(must_feed carer ward t)"),
        "feed_ward_alarm": P("feed_ward_alarm", "(and (must_feed carer ward t) (alarm ward t) (not (alarm carer t)))"),
        "feed_busy": P("feed_busy", "(and (must_feed carer ward t) (busy t))"),
        "enrol": P("enrol", "(must_enrol carer ward t)"),
    }


def test_O5_household_pins_mirror_the_dataset_pins():
    """The tiny analogue of the dataset pins (computational-liberation tests/test_dataset_claims.py, O5)."""
    inst, props = inst_obliged_household()
    _, v = _engine(inst, props, {"mutual_obliged": ["invariant"], "mutual_obliged_as_written": ["invariant"],
                                 "wife_obliged": ["reachable"], "obliged_not_caring": ["reachable"],
                                 "chosen": ["invariant"], "reversed": ["reachable"]})
    assert v == {"mutual_obliged": "holds_to_k", "mutual_obliged_as_written": "violated", "wife_obliged": "reachable",
                 "obliged_not_caring": "open", "chosen": "violated", "reversed": "open"}
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] != "R3"]
    # R3.2 O5 writes (forall ((h agent) (w agent)) (not (care_obliged w h t))); over every ordered pair that includes
    # (husband, wife), whom R2 still obliges, so the pin names the wife's duty to the husband (drift recorded)
    p = {"wife_never": P("wife_never", "(not (care_obliged wife husband t))"),
         "as_written": P("as_written", "(forall ((h agent) (w agent)) (not (care_obliged w h t)))")}
    _, v = _engine(InstitutionJSON.model_validate(d), p, {"wife_never": ["invariant"], "as_written": ["invariant"]})
    assert v == {"wife_never": "holds_to_k", "as_written": "violated"}
