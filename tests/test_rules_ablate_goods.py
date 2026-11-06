"""Goods in rule ablation (plans/priority-slice2.md section 6 and revision 2, R2.1 / R2.2): the four goods states
(not_applicable, absent, fragile, stable) read from the good's own subject, the guaranteed and possible measures,
contested alternatives chosen by name and never pooled, goods k-disagreement, readings and strand agreement, loader
checks. Mutations R2.2 names (M1, M2, M5, M6', M8, M9) are each killed by a test below (record: the engine commit);
so are the revision-2 correctness review's survivors M10, M11, M12 (test_4e, test_4f, test_4g)."""
import itertools
import json

import pytest

from philengine import rules_ablate as ra
from philengine import rules_checks
from philengine.schemas_rules import InstitutionJSON, Property, RulesLoadError, load_properties

CARED = "(forall ((s agent)) (=> (is_subject s t) (exists ((c agent)) (cares c s t))))"
SUBJ = "(exists ((s agent)) (is_subject s t))"
TRIVIAL = "(forall ((s agent)) (=> (is_subject s t) (is_subject s t)))"  # holds for every bearer: never lost
HOME = "(forall ((s agent)) (=> (is_subject s t) (at_home s t)))"


def good(name, formal, contested=(), subject=SUBJ, encoders=("e1", "e2"), primary_measure="possible",
         primary_measure_reason="test fixture", **kw):
    return Property(name=name, kind="goods", polarity="good", check="persists", encoders=list(encoders),
                    contested=list(contested), formal=formal, subject=subject, primary_measure=primary_measure,
                    primary_measure_reason=primary_measure_reason, **kw)


ROLES = [{"name": "carer"}, {"name": "subj"}]
FLUENTS = [{"name": "is_subject", "arity": 1, "arg_roles": ["subj"]},
           {"name": "cares", "arity": 2, "arg_roles": ["carer", "subj"]},
           {"name": "at_home", "arity": 1, "arg_roles": ["subj"]}]


def act(name, args, roles, *effects):
    return {"name": name, "args": args, "arg_roles": roles,
            "effects": [{"fluent": f, "args": a, "value": v} for f, a, v in effects]}


def inst_of(id_, actions, rules, **kw):
    return InstitutionJSON.model_validate({"id": id_, "roles": ROLES, "fluents": kw.pop("fluents", FLUENTS),
                                          "actions": actions, "rules": rules, "expected_properties": {}, **kw})


def care():
    """Stable care by a must-be duty. A carer may enrol a subject (R1, which also starts care); while s is a subject,
    care must hold (R2, must-be). neglect (unregulated) breaks care and give (unregulated) restores it, so deleting R2
    removes the guarantee and keeps the possibility. go_home is barred by a disability (R3)."""
    inst = inst_of("t-care", [
        act("enrol", ["c", "s"], ["carer", "subj"], ("is_subject", ["s"], True), ("cares", ["c", "s"], True)),
        act("neglect", ["c", "s"], ["carer", "subj"], ("cares", ["c", "s"], False)),
        act("give", ["c", "s"], ["carer", "subj"], ("cares", ["c", "s"], True)),
        act("go_home", ["s"], ["subj"], ("at_home", ["s"], True)),
    ], [
        {"id": "R1", "attribute": "carer", "deontic": "may", "aim": "(enrol c s)", "conditions": "true", "strand": "tying"},
        {"id": "R2", "attribute": "carer", "deontic": "must", "aim": "(cares c s)", "conditions": "(is_subject s)",
         "or_else": None, "strand": "superadditive"},
        {"id": "R3", "attribute": "subj", "deontic": "must_not", "aim": "(go_home s)", "conditions": "true",
         "or_else": None, "strand": "rival"},
    ])
    return inst, {"cared": good("cared", CARED)}


def care2():
    """Fragile care by permission. R1: a carer may enrol (creates the bearer, no care); R2: a carer may give care
    (the only care permission, condition true, so its prohibit is ranked); neglect (unregulated) breaks it."""
    inst = inst_of("t-care2", [
        act("enrol", ["c", "s"], ["carer", "subj"], ("is_subject", ["s"], True)),
        act("give", ["c", "s"], ["carer", "subj"], ("cares", ["c", "s"], True)),
        act("neglect", ["c", "s"], ["carer", "subj"], ("cares", ["c", "s"], False)),
    ], [
        {"id": "R1", "attribute": "carer", "deontic": "may", "aim": "(enrol c s)", "conditions": "true", "strand": "tying"},
        {"id": "R2", "attribute": "carer", "deontic": "may", "aim": "(give c s)", "conditions": "true",
         "strand": "superadditive"},
    ])
    return inst, {"cared": good("cared", CARED)}


def barred():
    """The kibbutz R4 shape: the bearer exists from step 0 (initial), go_home is the only action that realises the
    good, and a disability (R3) bars it."""
    inst = inst_of("t-barred", [
        act("go_home", ["s"], ["subj"], ("at_home", ["s"], True)),
        act("leave", ["s"], ["subj"], ("at_home", ["s"], False)),
    ], [
        {"id": "R3", "attribute": "subj", "deontic": "must_not", "aim": "(go_home s)", "conditions": "true",
         "or_else": None, "strand": "rival"},
    ], initial=["is_subject(subj)"])
    return inst, {"home": good("home", HOME)}


def row(res, rid):
    return next(a for a in res if a.rule_id == rid)


def base_state(inst, p, k=4):
    rep = rules_checks.run_all(inst, {p.name: p}, k=k, which={p.name: ["persists"]})
    r = rep.results[0]
    return r.goods_state, r.goods_reason


# ------------------------------------------------------------------ 1. transition table (kills M1)
EXPECTED = {  # (before, after) -> (guaranteed, possible)
    ("stable", "fragile"): ("lost", None), ("fragile", "stable"): ("gained", None),
    ("stable", "absent"): ("lost", "lost"), ("absent", "stable"): ("gained", "gained"),
    ("fragile", "absent"): (None, "lost"), ("absent", "fragile"): (None, "gained"),
}


@pytest.mark.parametrize("before,after", list(itertools.product(ra.GOODS_STATES, repeat=2)))
def test_transition_table_all_16_pairs(before, after):
    g, p = EXPECTED.get((before, after), (None, None))  # same state, or any pair with not_applicable: neither
    assert ra.goods_transition(before, after) == {"guaranteed": g, "possible": p}


def test_measure_values():
    assert [ra.measure_value(s, "guaranteed") for s in ("absent", "fragile", "stable")] == [False, False, True]
    assert [ra.measure_value(s, "possible") for s in ("absent", "fragile", "stable")] == [False, True, True]


# ------------------------------------------------------------------ 5. the possible measure
def test_5a_barred_good_reads_absent_and_deleting_the_bar_makes_it_possible():
    inst, props = barred()
    assert base_state(inst, props["home"]) == ("absent", None)
    a = row(ra.ablate(inst, props, k=4), "R3")
    assert a.goods_states["home"] == ["absent", "fragile"]
    assert (a.load_goods_possible, a.load_goods_possible_gained, a.goods_families_possible_gained) == (0, 1, ["home"])
    assert (a.load_goods_guaranteed, a.load_goods_guaranteed_gained) == (0, 0)
    assert a.reading("possible") == "unread" == a.reading("guaranteed")


def test_5b_step0_grace_with_bearer_at_step0_and_good_never_holding_is_absent():
    inst, _ = barred()
    grace = good("g", "(forall ((s agent) (t0 step)) (=> (and (succ t0 t) (is_subject s t0) (is_subject s t)) "
                      "(at_home s t)))")
    assert base_state(inst, grace) == ("absent", None)  # step 0 is no witness step, so its truth there is not the good


def test_5c_guarantee_removed_possibility_kept():
    inst, props = care()
    assert base_state(inst, props["cared"]) == ("stable", None)
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    a = row([x.by_k[4] for x in m], "R2")
    assert a.goods_states["cared"] == ["stable", "fragile"]
    assert (a.load_goods_guaranteed, a.load_goods_possible) == (1, 0)
    assert a.load_freedom_up == 0
    assert (a.reading("guaranteed"), a.reading("possible")) == ("guarantee-carrying", "unread")
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert "R2" in summ["guarantee_carrying"] and "R2" not in summ["constitutive"]
    assert ra.strand_agreement(a.strand, a.reading("guaranteed")) == "agree"


def test_5d_made_impossible_fragile_to_absent_is_possible_lost_and_constitutive():
    inst, props = care2()
    assert base_state(inst, props["cared"]) == ("fragile", None)
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    a = row([x.by_k[4] for x in m], "R2~prohibit")
    assert a.goods_states["cared"] == ["fragile", "absent"]
    assert (a.load_goods_possible, a.load_goods_guaranteed) == (1, 0)
    assert (a.reading("possible"), a.reading("guaranteed")) == ("constitutive", "unread")
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert summ["constitutive"] == ["R2~prohibit"] and summ["guarantee_carrying"] == []
    assert ra.strand_agreement("superadditive", "constitutive") == "agree"
    # label only (faithfulness review major 3): R2 prohibits `give`, which sets `cares`, which the lost good reads
    assert a.possible_lost_label == ra.CARE_ACT_LABEL == "prohibition of the care act"
    assert summ["constitutive_labels"] == {"R2~prohibit": "prohibition of the care act"}
    assert all(x.by_k[4].possible_lost_label is None for x in m if x.rule_id != "R2~prohibit")


def test_5f_care_act_label_is_label_only():
    inst, props = care2()
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    a = row([x.by_k[4] for x in m], "R2~prohibit")
    assert a.possible_lost_label == ra.CARE_ACT_LABEL
    # an action that sets no fluent the lost good reads gets no label
    assert ra.care_act_label(inst, "enrol", a, props) is None
    # the readings table prints it beside the reading; the agreement cell is unchanged
    txt = ra.readings_table({"t": m}, (4,))
    line = next(x for x in txt.splitlines() if "| R2~prohibit |" in x)
    assert "| constitutive (prohibition of the care act) | agree |" in line
    # no count, load or reading changes with the label removed
    b = a.to_dict() | {"possible_lost_label": None}
    assert {k: v for k, v in b.items() if k != "possible_lost_label"} == {
        k: v for k, v in a.to_dict().items() if k != "possible_lost_label"}
    assert a.reading("possible") == "constitutive"


def test_5e_formula_without_implication_shape_uses_subject_as_witness():
    inst, _ = care()
    flat = good("flat", "(forall ((s agent)) (or (not (is_subject s t)) (at_home s t)))")
    # true at step 0 (no bearer), but that step is no witness step: with Subj as witness the good never holds
    assert base_state(inst, flat) == ("absent", None)


# ------------------------------------------------------------------ 4. not_applicable
def test_4a_prohibiting_the_act_that_creates_the_bearer_is_not_applicable_never_a_loss():
    # replaces, deliberately, the revision-1 assertion that pinned stable > absent for "no subject is ever enrolled"
    inst, props = care()
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    a = row([x.by_k[4] for x in m], "R1~prohibit")
    assert a.goods_states["cared"] == ["stable", "not_applicable"]
    assert (a.load_goods_guaranteed, a.load_goods_possible) == (0, 0)
    assert (a.load_goods_guaranteed_gained, a.load_goods_possible_gained) == (0, 0)
    assert a.reading("possible") == "unread" == a.reading("guaranteed")
    assert a.goods_not_applicable == ["cared"] and a.na_move()
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert "R1~prohibit" not in summ["constitutive"] + summ["guarantee_carrying"]
    assert summ["goods_not_applicable_rows"] == ["R1~prohibit"]


def test_4b_the_goods_own_subject_is_read_not_any_is_fluent():
    inst = InstitutionJSON.model_validate({
        "id": "t-marry", "roles": [{"name": "h"}, {"name": "w"}],
        "fluents": [{"name": "married", "arity": 2, "arg_roles": ["h", "w"]},
                    {"name": "cares", "arity": 2, "arg_roles": ["h", "w"]},
                    {"name": "is_ward", "arity": 1, "arg_roles": ["w"]}],  # an is_* fluent that never holds
        "actions": [act("marry", ["x", "y"], ["h", "w"], ("married", ["x", "y"], True)),
                    act("tend", ["x", "y"], ["h", "w"], ("cares", ["x", "y"], True)),
                    act("admit", ["y"], ["w"], ("is_ward", ["y"], True))],
        "rules": [{"id": "R1", "attribute": "h", "deontic": "may", "aim": "(marry x y)", "conditions": "true",
                   "strand": "tying"},
                  {"id": "R2", "attribute": "h", "deontic": "may", "aim": "(tend x y)", "conditions": "true",
                   "strand": "superadditive"},
                  {"id": "R3", "attribute": "w", "deontic": "must_not", "aim": "(admit y)", "conditions": "true",
                   "or_else": None, "strand": "rival"}],  # is_ward is barred, so it never holds
        "expected_properties": {}})
    g = good("mutual", "(forall ((x agent) (y agent)) (=> (married x y t) (cares x y t)))",
             subject="(exists ((x agent) (y agent)) (married x y t))")
    assert base_state(inst, g) == ("fragile", None)


def _unknown_goods_queries(monkeypatch, which=lambda prop: True):
    """z3 answers unknown to every goods query of the properties `which` selects."""
    real = rules_checks._check

    def fake(exprs, **kw):
        if rules_checks._CTX["phase"] == "goods" and which(rules_checks._CTX["property"]):
            rules_checks._LOG.append({"phase": "goods", "property": "", "check": "", "build_ms": 0, "solve_ms": 0,
                                      "result": "unknown", "retries": 0})
            return rules_checks._Res("unknown", None, "test")
        return real(exprs, **kw)
    monkeypatch.setattr(rules_checks, "_check", fake)


def test_4c_undecided_subject_query_is_uncounted_never_stable(monkeypatch):
    inst, props = care()  # stable when decided
    _unknown_goods_queries(monkeypatch)
    assert base_state(inst, props["cared"]) == (None, "subject_unknown")
    a = row(ra.ablate(inst, props, k=4), "R2")
    assert a.uncounted == ["cared"] and "subject_unknown" in a.uncounted_reasons["cared"]
    assert a.goods_states == {} and a.load_goods_guaranteed == 0


def _unknown_at_goods_query(monkeypatch, n):
    """z3 answers unknown to the n-th goods query of each property run only (0 subject, 1 witness, 2 possible,
    3 guaranteed = check_invariant's query); every other query is decided."""
    real_check, real_begin = rules_checks._check, rules_checks._begin
    cnt = {"i": 0}

    def begin(phase, property="", check=""):
        cnt["i"] = 0
        real_begin(phase, property, check)

    def fake(exprs, **kw):
        if rules_checks._CTX["phase"] == "goods":
            i, cnt["i"] = cnt["i"], cnt["i"] + 1
            if i == n:
                rules_checks._LOG.append({"phase": "goods", "property": "", "check": "", "build_ms": 0, "solve_ms": 0,
                                          "result": "unknown", "retries": 0})
                return rules_checks._Res("unknown", None, "test")
        return real_check(exprs, **kw)
    monkeypatch.setattr(rules_checks, "_begin", begin)
    monkeypatch.setattr(rules_checks, "_check", fake)


def test_4e_undecided_guaranteed_query_is_uncounted_never_stable(monkeypatch):
    # kills M10 (an undecided invariant read as stable: `inv.verdict != "violated"`)
    inst, props = care()  # stable when decided
    _unknown_at_goods_query(monkeypatch, 3)
    state, reason = base_state(inst, props["cared"])
    assert (state, reason) == (None, "guaranteed_unknown")
    a = row(ra.ablate(inst, props, k=4), "R2")
    assert a.uncounted == ["cared"] and "guaranteed_unknown" in a.uncounted_reasons["cared"]
    assert a.goods_states == {} and (a.load_goods_guaranteed, a.load_goods_possible) == (0, 0)


def test_4f_undecided_possible_query_is_uncounted_never_absent(monkeypatch):
    # kills M11 (an undecided possible query read as absent: `!= "sat"`)
    inst, props = care2()  # fragile when decided
    _unknown_at_goods_query(monkeypatch, 2)
    assert base_state(inst, props["cared"]) == (None, "possible_unknown")
    a = row(ra.ablate(inst, props, k=4), "R2~prohibit")  # decided: fragile > absent, possible lost 1
    assert a.uncounted == ["cared"] and "possible_unknown" in a.uncounted_reasons["cared"]
    assert a.goods_states == {} and a.load_goods_possible == 0 and a.reading("possible") == "unread"


def test_4g_no_witness_within_k_is_uncounted_never_absent():
    # kills M12 (no_witness_within_k read as absent). The bearer exists (subject sat) but the premise needs at_home,
    # which R3 bars: no witness step within k. Deleting R3 makes the good hold trivially; with the before side
    # uncounted that is no gain.
    inst, _ = barred()
    g = good("w", "(forall ((s agent)) (=> (and (is_subject s t) (at_home s t)) (at_home s t)))")
    assert base_state(inst, g) == (None, "no_witness_within_k")
    a = row(ra.ablate(inst, {"w": g}, k=4), "R3")
    assert a.uncounted == ["w"] and "no_witness_within_k" in a.uncounted_reasons["w"]
    assert a.goods_states == {} and (a.load_goods_possible_gained, a.load_goods_guaranteed_gained) == (0, 0)


def test_4h_subject_with_a_free_step_variable_is_a_clean_load_error(tmp_path):
    # correctness review minor 2(a): a RulesLoadError (exit 2), not a raw z3 Sort mismatch out of load_properties
    p = tmp_path / "p.json"
    p.write_text(json.dumps([good("x", CARED).model_dump(mode="json") | {"subject": "(exists ((s agent)) (is_subject s t0))"}]))
    with pytest.raises(RulesLoadError, match="does not type-check"):
        load_properties(p)


def test_4d_loader_rejects_missing_subject_undeclared_subject_fluent_and_unimplied_subject(tmp_path):
    with pytest.raises(ValueError, match="subject"):
        Property(name="x", kind="goods", polarity="good", check="persists", encoders=["a", "b"], contested=[],
                 formal=CARED, primary_measure="possible", primary_measure_reason="r")
    with pytest.raises(ValueError, match="does not imply"):
        good("x", CARED, subject="(exists ((s agent)) (at_home s t))")
    with pytest.raises(ValueError, match="does not imply"):  # an alternative's premise is checked against its subject
        good("x", CARED, contested=[{"encoder": "e2", "formal": HOME, "subject": "(exists ((s agent)) (cares carer s t))"}])
    with pytest.raises(ValueError, match="only for kind goods"):
        Property(name="x", kind="structure", formal="(held ward t)", subject="(held ward t)")
    inst, _ = care()
    bad = good("x", CARED, subject="(or (exists ((s agent)) (is_subject s t)) (ghost_fluent t))")
    with pytest.raises(RulesLoadError, match="undeclared fluent"):
        ra.applicable_which(inst, {"x": bad})
    # the CLI loader refuses it too (exit 2), before any check runs
    from philengine.cli import build_parser
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([bad.model_dump(mode="json")]))
    a = build_parser().parse_args(["rules", "ablate", "--k", "3", "--institutions", str(tmp_path / "i.json"),
                                   "--properties", str(tmp_path / "p.json")])
    with pytest.raises(SystemExit) as e:
        a.fn(a)
    assert e.value.code == 2


# ------------------------------------------------------------------ 2. contested alternatives (kills M2, M9)
def test_2_alternative_flips_primary_does_not_never_pooled():
    inst, props = care()
    props["cared"] = good("cared", TRIVIAL, contested=[{"encoder": "e2", "formal": CARED}])
    res = ra.ablate(inst, props, k=4)
    a = row(res, "R2")  # alternative stable > fragile, primary stable > stable
    assert a.goods_states["cared"] == ["stable", "stable"] and a.goods_alt_states["cared@e2"] == ["stable", "fragile"]
    assert (a.load_goods_guaranteed, a.load_goods_possible) == (0, 0)
    assert a.load_goods_by_encoder["e2"]["guaranteed"]["lost"] == 1 and a.load_goods_by_encoder["e1"]["guaranteed"]["lost"] == 0
    assert a.reading_by_encoder("guaranteed") == {"e1": "unread", "e2": "guarantee-carrying"}
    assert "cared@e2" not in {f[0] for f in a.flips}

    inst2, props2 = care2()
    props2["cared"] = good("cared", TRIVIAL, contested=[{"encoder": "e2", "formal": CARED}])
    m = ra.ablate_multi_k(inst2, props2, ks=(4,))
    b = row([x.by_k[4] for x in m], "R2~prohibit")  # alternative fragile > absent, primary stable > stable
    assert b.goods_alt_states["cared@e2"] == ["fragile", "absent"] and b.goods_states["cared"] == ["stable", "stable"]
    assert (b.load_goods_guaranteed, b.load_goods_possible) == (0, 0)
    assert b.load_goods_by_encoder["e2"]["possible"]["lost"] == 1 and b.load_goods_by_encoder["e1"]["possible"]["lost"] == 0
    assert b.reading_by_encoder("possible") == {"e1": "unread", "e2": "constitutive"}
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert summ["constitutive"] == [] and summ["contested_readings"] == ["R2~prohibit"]
    assert ra.scoreboard_stats({"t": m}, (4,))["contested_readings"] == 1


def test_2a_alternative_chosen_by_name_not_by_encoder_position():
    inst, _ = care()
    # the first goods property puts e1 first, so position-based selection would treat e1 as primary everywhere
    props = {"first": good("first", TRIVIAL, encoders=("e1", "e2")),
             "cared": good("cared", TRIVIAL, encoders=("e2", "e1"), contested=[{"encoder": "e1", "formal": CARED}])}
    assert ra.goods_encoders(props) == ["e1", "e2"]
    a = row(ra.ablate(inst, props, k=4), "R2")
    assert a.load_goods_by_encoder["e1"]["guaranteed"]["lost"] == 1  # e1's view reads cared@e1
    assert a.load_goods_by_encoder["e2"]["guaranteed"]["lost"] == 0  # e2 wrote the primary


def test_2b_uncounted_alternative_with_counted_primary_is_listed_for_that_encoder(monkeypatch):
    inst, props = care()
    props["cared"] = good("cared", TRIVIAL, contested=[{"encoder": "e2", "formal": CARED}])
    _unknown_goods_queries(monkeypatch, which=lambda prop: prop.endswith("@e2"))
    a = row(ra.ablate(inst, props, k=4), "R2")
    assert a.goods_states["cared"] == ["stable", "stable"] and "cared@e2" in a.uncounted
    assert a.load_goods_by_encoder["e2"]["uncounted"] == ["cared"]
    assert a.load_goods_by_encoder["e1"]["uncounted"] == []


# ------------------------------------------------------------------ 3. goods k-disagreement (kills M5)
def chain():
    """Care can first hold for a bearer only after four actions (prep1, prep2, give, enrol in some order: one action
    per step), so at k=3 it is absent and at k=4 fragile. Prohibiting prep1 (R1, condition true) makes it impossible."""
    fl = FLUENTS + [{"name": "p1", "arity": 0}, {"name": "p2", "arity": 0}]
    inst = inst_of("t-chain", [
        act("prep1", ["c"], ["carer"], ("p1", [], True)),
        act("prep2", ["c"], ["carer"], ("p2", [], True)),
        act("give", ["c", "s"], ["carer", "subj"], ("cares", ["c", "s"], True)),
        act("enrol", ["c", "s"], ["carer", "subj"], ("is_subject", ["s"], True)),
    ], [
        {"id": "R1", "attribute": "carer", "deontic": "may", "aim": "(prep1 c)", "conditions": "true", "strand": "tying"},
        {"id": "R2", "attribute": "carer", "deontic": "may", "aim": "(prep2 c)", "conditions": "p1", "strand": "tying"},
        {"id": "R3", "attribute": "carer", "deontic": "may", "aim": "(give c s)", "conditions": "p2", "strand": "tying"},
        {"id": "R4", "attribute": "carer", "deontic": "may", "aim": "(enrol c s)", "conditions": "true", "strand": "tying"},
    ], fluents=fl)
    return inst, {"cared": good("cared", CARED)}


def test_3_goods_state_differing_by_k_is_a_k_disagreement_with_unchanged_verdicts():
    inst, props = chain()
    m = ra.ablate_multi_k(inst, props, ks=(3, 4))
    r = next(x for x in m if x.rule_id == "R1~prohibit")
    assert r.by_k[3].goods_states["cared"] == ["absent", "absent"]
    assert r.by_k[4].goods_states["cared"] == ["fragile", "absent"]
    assert r.by_k[4].load_goods_possible == 1 and r.by_k[3].load_goods_possible == 0
    assert all(f[0] != "cared" for a in r.by_k.values() for f in a.flips)  # persists `fails` on both sides at both k
    assert r.k_disagreement == ["cared"]
    assert ra.scoreboard_stats({"t": m}, (3, 4))["k_disagreements"] >= 1


# ------------------------------------------------------------------ 6. kept from revision 1, new fields
def test_adding_goods_changes_no_freedom_column():
    inst, props = care()
    props["subj_free"] = Property(name="subj_free", kind="freedom", polarity="unfreedom", check="persists",
                                  formal="(forall ((s agent)) (=> (is_subject s t) (not (at_home s t))))")
    only_freedom = {"subj_free": props["subj_free"]}
    keys = ("rule_id", "load_freedom", "load_freedom_up", "load_freedom_down", "load_freedom_unsigned", "families_up",
            "families_down", "families_mixed", "flip_directions", "deregulated", "offcondition_free", "inconsistent_after")
    a = [{k: x.to_dict()[k] for k in keys} for x in ra.ablate(inst, only_freedom, k=4)]
    b = [{k: x.to_dict()[k] for k in keys} for x in ra.ablate(inst, props, k=4)]
    assert a == b and any(r["load_freedom"] for r in a)


def test_entries_make_a_goods_property_applicable_despite_undeclared_fluent():
    inst, _ = care()
    g = good("g", "(forall ((s agent)) (=> (is_subject s t) (or (cares carer s t) (elsewhere s t))))")
    which, na = ra.applicable_which(inst, {"g": g})
    assert "g" in na and "g" not in which
    g2 = g.model_copy(update={"entries": ["t-care"]})
    which, na = ra.applicable_which(inst, {"g": g2})
    assert which == {"g": ["persists"]} and na == []


def test_reading_and_strand_agreement_table():
    assert [ra.reading(u, l) for u, l in ((1, 0), (0, 2), (1, 1), (0, 0))] == ["tying", "constitutive", "hard case", "unread"]
    assert [ra.reading(u, l, "guaranteed") for u, l in ((1, 0), (0, 2), (1, 1), (0, 0))] == [
        "tying", "guarantee-carrying", "hard case (guarantee)", "unread"]
    assert ra.strand_agreement("tying", "tying") == "agree"
    assert ra.strand_agreement("superadditive", "constitutive") == "agree"
    assert ra.strand_agreement("superadditive", "guarantee-carrying") == "agree"
    assert ra.strand_agreement("tying", "hard case") == "mismatch"
    assert ra.strand_agreement("superadditive", "tying") == "mismatch"
    assert ra.strand_agreement("tying", "guarantee-carrying") == "mismatch"
    assert ra.strand_agreement("rival", "tying") == "no_row"
    assert ra.strand_agreement(None, "tying") == "untagged" and ra.strand_agreement(None, "unread") == "unread"
    assert ra.strand_agreement("tying", "unread") == "unread" and ra.strand_agreement("rival", "unread") == "unread"


def test_null_strand_is_accepted_and_required():
    inst, _ = care()
    d = inst.model_dump()
    d["rules"][2]["strand"] = None
    assert InstitutionJSON.model_validate(d).rules[2].strand is None
    del d["rules"][2]["strand"]
    with pytest.raises(ValueError, match="strand"):
        InstitutionJSON.model_validate(d)


GOODS_BASE = {"kind": "goods", "polarity": "good", "check": "persists", "subject": "(held ward t)",
              "primary_measure": "possible", "primary_measure_reason": "r"}


@pytest.mark.parametrize("item,match", [
    ({**GOODS_BASE, "encoders": ["a", "b"]}, "contested"),
    ({**GOODS_BASE, "encoders": ["a"], "contested": []}, "two encoders"),
    ({**GOODS_BASE, "encoders": ["a", "a"], "contested": []}, "two encoders"),
    ({**GOODS_BASE, "polarity": "unfreedom", "encoders": ["a", "b"], "contested": []}, "polarity: good"),
    ({"kind": "goods", "check": "persists", "encoders": ["a", "b"], "contested": []}, "polarity: good"),
    ({**GOODS_BASE, "check": "invariant", "encoders": ["a", "b"], "contested": []}, "persists"),
    ({**{k: v for k, v in GOODS_BASE.items() if k != "subject"}, "encoders": ["a", "b"], "contested": []}, "subject"),
    ({"kind": "freedom", "polarity": "good"}, "polarity"),
    ({"kind": "structure", "polarity": "good"}, "only for kind goods"),
    ({**GOODS_BASE, "encoders": ["a", "b"], "contested": [{"encoder": "b", "formal": "(and (held ward t)"}]},
     "does not parse"),
])
def test_validator_rejections(tmp_path, item, match):
    p = tmp_path / "p.json"
    p.write_text(json.dumps([{"name": "x", "formal": "(held ward t)", **item}]))
    with pytest.raises(RulesLoadError, match=match):
        load_properties(p)


def test_validator_accepts_goods_and_expand_contested_is_idempotent():
    p = good("x", "(held ward t)", subject="(held ward t)",
             contested=[{"encoder": "e2", "formal": "(not (held ward t))", "subject": "(free ward t)"}])
    assert p.contested[0].encoder == "e2" and p.contested[0].note == ""
    ex = ra.expand_contested({"x": p})
    assert set(ex) == {"x", "x@e2"} and ex["x@e2"].subject == "(free ward t)"
    assert ra.expand_contested(ex).keys() == {"x", "x@e2"}
    q = good("y", CARED, contested=[{"encoder": "e2", "formal": TRIVIAL}])
    assert ra.expand_contested({"y": q})["y@e2"].subject == SUBJ  # no own subject: the primary's


def all_states():
    """care2 plus a trivially kept good with a contested alternative: base fragile / stable; R2~prohibit fragile >
    absent; R1~prohibit > not_applicable."""
    inst, props = care2()
    props["kept"] = good("kept", TRIVIAL, contested=[{"encoder": "e2", "formal": CARED}])
    return inst, props


def test_fixture_carries_all_four_states():
    inst, props = all_states()
    res = ra.ablate(inst, props, k=4)
    seen = {s for a in res for v in {**a.goods_states, **a.goods_alt_states}.values() for s in v}
    assert seen == set(ra.GOODS_STATES)


def test_spawn_workers_match_serial_on_goods(monkeypatch):
    from philengine.abm import parallel
    monkeypatch.setenv("PHIL_START_METHOD", "spawn")
    inst, props = all_states()
    s1 = ra.ablate_multi_k(inst, props, (3, 4), workers=1)
    with parallel.pool(4):
        s4 = ra.ablate_multi_k(inst, props, (3, 4), workers=None)
    assert [m.to_dict() for m in s1] == [m.to_dict() for m in s4]


def test_cli_ablate_readings_table(tmp_path):
    from philengine.cli import build_parser
    inst, props = care()
    (tmp_path / "i.json").write_text(json.dumps([inst.model_dump(mode="json")]))
    (tmp_path / "p.json").write_text(json.dumps([p.model_dump(mode="json") for p in props.values()]))
    out = tmp_path / "r.md"
    a = build_parser().parse_args(["rules", "ablate", "--k", "4", "--institutions", str(tmp_path / "i.json"),
                                   "--properties", str(tmp_path / "p.json"), "--readings", str(out)])
    assert a.fn(a) == 0
    txt = out.read_text()
    assert txt.splitlines()[0] == (
        "| entry | rule | ranked | tag | k | up | G lost [e1] | G gained [e1] | G reading [e1] | G agreement [e1] | "
        "G lost [e2] | G gained [e2] | G reading [e2] | G agreement [e2] | P lost [e1] | P gained [e1] | "
        "P reading [e1] | P agreement [e1] | P lost [e2] | P gained [e2] | P reading [e2] | P agreement [e2] | "
        "primary lost [e1] | primary gained [e1] | primary reading [e1] | primary agreement [e1] | "
        "primary lost [e2] | primary gained [e2] | primary reading [e2] | primary agreement [e2] | "
        "goods changes |")
    assert ("| t-care | R2 | yes | superadditive | 4 | 0 | 1 | 0 | guarantee-carrying | agree | 1 | 0 | "
            "guarantee-carrying | agree | 0 | 0 | unread | unread | 0 | 0 | unread | unread | "
            "0 | 0 | unread | unread | 0 | 0 | unread | unread | cared: stable>fragile |") in txt  # possible-primary
    assert "cared: stable>n/a" in txt  # R1~prohibit: an n/a move is printed


def test_dataset_goods_have_two_encoders_contested_and_subject(dataset_env):
    props = load_properties(dataset_env[1])
    for n, p in props.items():
        if p.kind == "goods":
            assert len(set(p.encoders)) >= 2 and p.contested is not None and p.polarity == "good", n
            assert p.subject, n


# ------------------------------------------------------------------ R3.1 primary column (plans/priority-slice2.md
# revision 3; kills MP1 the primary reads the other measure, MP2 pooling, MP3 an alternative reads a default measure)
def _two_measures(inst_props, rid, k=4):
    m = ra.ablate_multi_k(*inst_props, ks=(k,))
    return m, row([x.by_k[k] for x in m], rid)


def test_P1_primary_reads_each_good_under_its_own_measure_only():
    inst, _ = care()
    props = {"cared_g": good("cared_g", CARED, primary_measure="guaranteed"),
             "cared_p": good("cared_p", CARED, primary_measure="possible")}
    _, a = _two_measures((inst, props), "R2")  # both stable > fragile: guarantee lost, possibility kept
    assert a.goods_states == {"cared_g": ["stable", "fragile"], "cared_p": ["stable", "fragile"]}
    assert (a.load_goods_guaranteed, a.load_goods_possible) == (2, 0)
    assert (a.load_goods_primary, a.goods_families_primary_lost) == (1, ["cared_g"])
    assert a.goods_primary_measures == {"cared_g": "guaranteed", "cared_p": "possible"}
    assert a.reading("primary") == "carrying (guaranteed)"
    assert ra.strand_agreement(a.strand, a.reading("primary")) == "agree"  # superadditive
    # a guaranteed-primary good going fragile > absent: possible lost 1, primary lost 0
    inst2, _ = care2()
    _, b = _two_measures((inst2, {"cared": good("cared", CARED, primary_measure="guaranteed")}), "R2~prohibit")
    assert b.goods_states["cared"] == ["fragile", "absent"]
    assert (b.load_goods_possible, b.load_goods_guaranteed, b.load_goods_primary) == (1, 0, 0)
    assert b.reading("primary") == "unread" and b.reading("possible") == "constitutive"
    # the same row read with a possible-primary good: primary lost 1, carrying (possible)
    _, c = _two_measures((inst2, {"cared": good("cared", CARED, primary_measure="possible")}), "R2~prohibit")
    assert (c.load_goods_primary, c.reading("primary")) == (1, "carrying (possible)")
    # gains: primary gained reads the primary measure too (barred: absent > fragile is a possible gain only)
    inst3, _ = barred()
    _, d = _two_measures((inst3, {"home": good("home", HOME, primary_measure="guaranteed")}), "R3")
    assert d.goods_states["home"] == ["absent", "fragile"]
    assert (d.load_goods_possible_gained, d.load_goods_primary_gained) == (1, 0)
    _, e = _two_measures((inst3, {"home": good("home", HOME, primary_measure="possible")}), "R3")
    assert (e.load_goods_primary_gained, e.goods_families_primary_gained) == (1, ["home"])


def test_P1b_primary_reading_words():
    fm = {"a": "guaranteed", "b": "possible"}
    assert ra.primary_reading(1, [], fm) == "tying"
    assert ra.primary_reading(0, ["a"], fm) == "carrying (guaranteed)"
    assert ra.primary_reading(0, ["b"], fm) == "carrying (possible)"
    assert ra.primary_reading(0, ["a", "b"], fm) == "carrying (both)"
    assert ra.primary_reading(1, ["a"], fm) == "hard case (primary)"
    assert ra.primary_reading(0, [], fm) == "unread"
    assert ra.strand_agreement("superadditive", "carrying (both)") == "agree"
    assert ra.strand_agreement("tying", "carrying (possible)") == "mismatch"
    assert ra.strand_agreement("tying", "hard case (primary)") == "mismatch"
    assert ra.strand_agreement("rival", "carrying (guaranteed)") == "no_row"


def test_P2_alternative_inherits_the_primarys_measure():
    inst, _ = care()
    props = {"cared": good("cared", TRIVIAL, primary_measure="guaranteed", contested=[{"encoder": "e2", "formal": CARED}])}
    assert ra.expand_contested(props)["cared@e2"].primary_measure is None  # carries none of its own
    assert ra.primary_measure_of("cared@e2", ra.expand_contested(props)) == "guaranteed"
    m, a = _two_measures((inst, props), "R2")  # alternative stable > fragile, primary stable > stable
    assert a.goods_alt_states["cared@e2"] == ["stable", "fragile"]
    assert a.load_goods_by_encoder["e2"]["primary"]["lost"] == 1 and a.load_goods_by_encoder["e1"]["primary"]["lost"] == 0
    assert a.load_goods_primary == 0  # never pooled into the primary load
    assert a.reading_by_encoder("primary") == {"e1": "unread", "e2": "carrying (guaranteed)"}
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert summ["contested_readings"] == ["R2"]  # also by the guaranteed column here
    # the same alternative under a possible-primary good: stable > fragile keeps the possibility, primary lost 0
    props["cared"] = props["cared"].model_copy(update={"primary_measure": "possible"})
    _, b = _two_measures((inst, props), "R2")
    assert b.load_goods_by_encoder["e2"]["primary"]["lost"] == 0
    # an alternative carrying its own measure is rejected
    for k in ("primary_measure", "primary_measure_reason"):
        with pytest.raises(ValueError, match="not allowed on an alternative"):
            good("x", TRIVIAL, contested=[{"encoder": "e2", "formal": CARED, k: "guaranteed"}])


def test_P2b_primary_reading_difference_by_encoder_is_a_contested_reading():
    # both measure columns agree between the encoders (each loses one guarantee, no possibility); only the primary
    # column differs: e1 loses the guarantee of a guaranteed-primary good, e2 that of a possible-primary good
    inst, _ = care()
    props = {"g1": good("g1", CARED, primary_measure="guaranteed", contested=[{"encoder": "e2", "formal": TRIVIAL}]),
             "g2": good("g2", TRIVIAL, primary_measure="possible", contested=[{"encoder": "e2", "formal": CARED}])}
    m, a = _two_measures((inst, props), "R2")
    for ms in ("guaranteed", "possible"):
        assert len(set(a.reading_by_encoder(ms).values())) == 1
    assert a.reading_by_encoder("primary") == {"e1": "carrying (guaranteed)", "e2": "unread"}
    assert ra.summarize({"t": m}, (4,))["entries"]["t"]["contested_readings"] == ["R2"]


def _write_props(tmp_path, items):
    p = tmp_path / "p.json"
    p.write_text(json.dumps(items))
    return p


GOOD_ITEM = {"kind": "goods", "polarity": "good", "check": "persists", "subject": "(held ward t)", "encoders": ["a", "b"],
             "contested": [], "formal": "(held ward t)", "primary_measure": "possible", "primary_measure_reason": "r"}


@pytest.mark.parametrize("change,match", [
    ({"primary_measure": None}, "requires primary_measure"),
    ({"primary_measure_reason": None}, "non-empty primary_measure_reason"),
    ({"primary_measure_reason": "  "}, "non-empty primary_measure_reason"),
    ({"primary_measure_reason": "one\ntwo"}, "one line"),
    ({"primary_measure_reason": "x" * 201}, "at most 200"),
    ({"primary_measure": "both"}, "primary_measure"),
])
def test_P3_loader_rejects_goods_without_a_valid_measure(tmp_path, change, match):
    item = {"name": "x", **GOOD_ITEM, **change}
    item = {k: v for k, v in item.items() if v is not None}
    with pytest.raises(RulesLoadError, match=match):
        load_properties(_write_props(tmp_path, [item]))


@pytest.mark.parametrize("key", ["primary_measure", "primary_measure_reason"])
@pytest.mark.parametrize("kind", ["freedom", "structure"])
def test_P3_loader_rejects_the_keys_on_a_non_goods_property(tmp_path, key, kind):
    item = {"name": "x", "kind": kind, "formal": "(held ward t)", key: "possible"}
    if kind == "freedom":
        item["polarity"] = "unfreedom"
    with pytest.raises(RulesLoadError, match="only for kind goods"):
        load_properties(_write_props(tmp_path, [item]))


def test_P3_loader_rejects_a_family_with_two_measures(tmp_path):
    a = {"name": "x", **GOOD_ITEM, "family": "f"}
    b = {"name": "y", **GOOD_ITEM, "family": "f", "primary_measure": "guaranteed"}
    with pytest.raises(RulesLoadError, match="goods family 'f': members differ in primary_measure"):
        load_properties(_write_props(tmp_path, [a, b]))
    b["primary_measure"] = "possible"
    assert set(load_properties(_write_props(tmp_path, [a, b]))) == {"x", "y"}
    assert load_properties(_write_props(tmp_path, [{"name": "x", **GOOD_ITEM, "primary_measure_reason": "x" * 200}]))


PRIMARY_KEYS = ("load_goods_primary", "load_goods_primary_gained", "goods_families_primary_lost",
                "goods_families_primary_gained", "goods_families_primary_mixed", "goods_primary_measures")


def _without_primary(m):
    d = m.to_dict()
    for a in d["by_k"].values():
        for k in PRIMARY_KEYS:
            a.pop(k)
        for e in a["load_goods_by_encoder"].values():
            e.pop("primary")
    for x in d["loads"].values():
        for k in ("load_goods_primary", "load_goods_primary_gained"):
            x.pop(k)
        for v in x["load_goods_by_encoder"].values():
            v.pop("primary")
        x["reading"].pop("primary")
        x["reading_by_encoder"].pop("primary")
    return d


@pytest.mark.parametrize("make", [care, care2, barred, all_states])
def test_P4_flipping_every_primary_measure_changes_no_measure_field(make):
    inst, props = make()
    flip = {"possible": "guaranteed", "guaranteed": "possible"}
    flipped = {n: p.model_copy(update={"primary_measure": flip[p.primary_measure]}) for n, p in props.items()}
    a = ra.ablate_multi_k(inst, props, ks=(3, 4))
    b = ra.ablate_multi_k(inst, flipped, ks=(3, 4))
    assert [_without_primary(m) for m in a] == [_without_primary(m) for m in b]
    sa, sb = (ra.summarize({"t": x}, (3, 4))["entries"]["t"] for x in (a, b))
    keep = ("top_rules", "constitutive", "hard_cases", "guarantee_carrying", "hard_cases_guaranteed",
            "goods_not_applicable_rows", "constitutive_labels")
    assert {k: sa[k] for k in keep} == {k: sb[k] for k in keep}
    assert ra.scoreboard_stats({"t": a}, (3, 4)) == ra.scoreboard_stats({"t": b}, (3, 4))


def test_P5_summary_primary_lists_and_readings_table():
    inst, _ = care()
    props = {"cared": good("cared", CARED, primary_measure="guaranteed")}
    m = ra.ablate_multi_k(inst, props, ks=(4,))
    summ = ra.summarize({"t": m}, (4,))["entries"]["t"]
    assert summ["primary_carrying"] == ["R2"] and summ["hard_cases_primary"] == []
    assert summ["top_goods_rules"] == ["R2"] and summ["top_load_goods_primary"] == 1
    assert summ["guarantee_carrying"] == ["R2"] and summ["constitutive"] == []  # measure lists unchanged
    d = next(x for x in m if x.rule_id == "R2").to_dict()["loads"]["4"]
    assert d["load_goods_primary"] == 1 and d["reading"]["primary"] == "carrying (guaranteed)"
    assert d["load_goods_by_encoder"]["e1"]["primary"] == 1
    txt = ra.readings_table({"t": m}, (4,))
    hdr = txt.splitlines()[0]
    assert hdr.endswith("| P agreement [e2] | primary lost [e1] | primary gained [e1] | primary reading [e1] | "
                        "primary agreement [e1] | primary lost [e2] | primary gained [e2] | primary reading [e2] | "
                        "primary agreement [e2] | goods changes |")
    line = next(x for x in txt.splitlines() if "| R2 |" in x)
    assert "| 1 | 0 | carrying (guaranteed) | agree | 1 | 0 | carrying (guaranteed) | agree | cared: stable>fragile |" in line
    # possible-primary: no goods ranking (nothing lost in its sense)
    m2 = ra.ablate_multi_k(inst, {"cared": good("cared", CARED, primary_measure="possible")}, ks=(4,))
    s2 = ra.summarize({"t": m2}, (4,))["entries"]["t"]
    assert s2["top_goods_rules"] == [] and s2["top_load_goods_primary"] == 0 and s2["primary_carrying"] == []
    # the care-act label prints beside the primary reading
    inst2, _ = care2()
    m3 = ra.ablate_multi_k(inst2, {"cared": good("cared", CARED, primary_measure="possible")}, ks=(4,))
    line = next(x for x in ra.readings_table({"t": m3}, (4,)).splitlines() if "| R2~prohibit |" in x)
    assert "| carrying (possible) (prohibition of the care act) | agree |" in line
