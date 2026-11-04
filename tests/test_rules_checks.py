import pytest

from philengine import rules_checks as rc
from philengine.schemas_rules import InstitutionJSON, Property, load_institutions, load_properties

from .helpers import require_dataset

from .test_rules_lower import tiny

PROPS = {
    "worker_paid": Property(name="worker_paid", formal="(exists ((w agent)) (paid w t))"),
    "paid_if_employed": Property(name="paid_if_employed", formal="(forall ((w agent)) (=> (employed w t) (paid w t)))"),
    "someone_employed": Property(name="someone_employed", formal="(exists ((w agent)) (employed w t))"),
    "boss_employed": Property(name="boss_employed", formal="(employed boss t)"),
}


def test_reachable_with_trace():
    rep = rc.run_all(tiny(), PROPS, k=4, which={"worker_paid": ["reachable"]})
    assert rep.consistent == "sat"
    assert rep.conflicts == []
    r = rep.results[0]
    assert r.verdict == "reachable"
    assert r.trace and len(r.trace) == 5
    assert any(s.property_holds for s in r.trace)
    assert any("hire(boss, worker)" in s.actions for s in r.trace)
    assert any("paid(worker)" in s.fluents for s in r.trace)
    assert rep.z3_version and rep.bound_k == 4


def test_open_is_not_safe():
    # hire(b, w) fixes w to the worker; the boss can never be employed -> open, with a reason, never "holds"
    rep = rc.run_all(tiny(), PROPS, k=4, which={"boss_employed": ["reachable"]})
    r = rep.results[0]
    assert r.verdict == "open"
    assert "not 'safe'" in r.reason


def test_invariant_violated_and_holds():
    rep = rc.run_all(tiny(), PROPS, k=4, which={"paid_if_employed": ["invariant"]})
    r = rep.results[0]
    assert r.verdict == "violated"  # pay lands one step after hire
    assert r.trace and r.trace[0].property_holds is True and any(s.property_holds is False for s in r.trace)
    # no hire action enabled at all -> employed never true -> vacuously holds
    inst = tiny()
    inst.rules.append(inst.rules[0].model_copy(update={"id": "R3", "deontic": "must_not", "aim": "(hire b w)", "conditions": "true", "or_else": None}))
    rep = rc.run_all(inst, PROPS, k=4, which={"paid_if_employed": ["invariant"]})
    assert rep.results[0].verdict == "holds_to_k"


def test_persists_strict_vs_sanctioned():
    rep = rc.run_all(tiny(), PROPS, k=4, which={"someone_employed": ["persists"]})
    assert rep.results[0].verdict == "persists"  # quitting while employed is forbidden in compliant traces
    # step_mode="many": R1 obliges pay at every employed step, so under "one" quit could never fit in a step
    rep = rc.run_all(tiny(), PROPS, k=4, which={"someone_employed": ["persists"]}, compliance="sanctioned", step_mode="many")
    r = rep.results[0]
    assert r.verdict == "fails"  # R2 has an or_else: it may be broken, the breach sets violated_R2
    assert any("quit(worker)" in s.actions for s in r.trace)
    assert any("violated_R2" in s.fluents for s in r.trace)


def test_deontic_conflict_and_inconsistent():
    inst = tiny()
    inst.rules.append(inst.rules[0].model_copy(update={"id": "R3", "deontic": "must_not", "or_else": None}))
    rep = rc.run_all(inst, PROPS, k=3, which={"worker_paid": ["reachable"]})
    assert ("R1", "R3") in rep.conflicts
    assert rep.consistent == "sat"  # conflict only bites when employed: traces that never hire are fine
    # make the conflict unconditional: no compliant trace at all
    inst2 = tiny()
    inst2.rules[0] = inst2.rules[0].model_copy(update={"conditions": "true"})
    inst2.rules.append(inst2.rules[0].model_copy(update={"id": "R3", "deontic": "must_not"}))
    rep = rc.run_all(inst2, PROPS, k=3, which={"worker_paid": ["reachable"]})
    assert rep.consistent == "unsat"
    assert rep.results[0].verdict == "inconsistent"


def test_expected_verdict_names_select_the_check():
    assert rc.check_for_expected("reachable") == "reachable"
    assert rc.check_for_expected("unreachable_open") == "reachable"
    assert rc.check_for_expected("holds_to_k") == "invariant"
    assert rc.check_for_expected("fails") == "persists"
    assert rc.check_for_expected("nonsense") is None


def test_coverture_dependent_cannot_exit():
    ip, pp = require_dataset()
    inst = {i.id: i for i in load_institutions(ip)}["coverture-household"]
    props = load_properties(pp)
    expected = rc.normalize_expected(inst.expected_properties["dependent_cannot_exit"])
    assert expected in ("reachable", "holds_to_k")
    rep = rc.run_all(inst, props, which={"dependent_cannot_exit": [rc.check_for_expected(expected)]})
    r = rep.results[0]
    assert r.verdict == expected
    assert rep.bound_k == 6 and rep.z3_version
    if r.verdict == "reachable":
        assert any("marry(husband, wife)" in s.actions for s in r.trace)
        assert any("is_subject(wife)" in s.fluents and "can_exit(wife)" not in s.fluents for s in r.trace)


def test_cli_check_all_runs(capsys, dataset_env):
    from philengine.cli import main
    rc_ = main(["rules", "check", "--inst", "coverture-household", "--prop", "dependent_cannot_exit"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "coverture-household" in out and "reachable" in out and "yes" in out


def test_step_mode_one_blocks_a_second_action_per_step():
    # under "one" the standing obligation (pay every employed step) leaves no step for quit: persists even sanctioned
    rep = rc.run_all(tiny(), PROPS, k=4, which={"someone_employed": ["persists"]}, compliance="sanctioned", step_mode="one")
    assert rep.results[0].verdict == "persists"
    assert rep.step_mode == "one"
    for mode in ("one", "many"):
        rep = rc.run_all(tiny(), PROPS, k=4, which={"worker_paid": ["reachable"]}, step_mode=mode)
        assert rep.results[0].verdict == "reachable"
        assert all(len(s.actions) <= 1 for s in rep.results[0].trace) or mode == "many"
    rep = rc.run_all(tiny(), PROPS, k=2, which={"worker_paid": ["reachable"]}, step_mode="all")
    assert any("step_mode='all'" in w for w in rep.warnings) and rep.results == []


def test_init_declared_defaults_and_initial_in_checks():
    # defaults can_claim_for=false on a fluent no action sets: never free, so no_claim holds; initial employed(worker)
    inst = tiny(fluents=[{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1}, {"name": "can_claim_for", "arity": 2}],
                defaults={"can_claim_for": "false"}, initial=["employed(worker)"])
    props = {"claim": Property(name="claim", formal="(exists ((x agent) (y agent)) (can_claim_for x y t))"),
             **PROPS}
    rep = rc.run_all(inst, props, k=3, which={"claim": ["reachable"], "someone_employed": ["invariant"]})
    assert rep.init == "declared"
    assert rep.verdict("claim") == "open"  # defaults pin it false at t=0 and nothing sets it
    assert rep.verdict("someone_employed") == "holds_to_k"  # employed at t=0 and quitting is forbidden
    # the same institution without the fields: can_claim_for is exogenous and free -> reachable at t=0
    inst2 = tiny(fluents=[{"name": "employed", "arity": 1}, {"name": "paid", "arity": 1}, {"name": "can_claim_for", "arity": 2}])
    rep = rc.run_all(inst2, props, k=3, which={"claim": ["reachable"]})
    assert rep.init == "empty" and rep.verdict("claim") == "reachable"
    # forcing --init empty on the declared institution restores the legacy reading
    rep = rc.run_all(inst, props, k=3, which={"claim": ["reachable"]}, init="empty")
    assert rep.init == "empty" and rep.verdict("claim") == "reachable"


def test_cli_table_shows_k_and_init(capsys, tmp_path):
    import json
    from philengine.cli import main
    inst = tiny(initial=["employed(worker)"], expected_properties={"someone_employed": "holds_to_k"}).model_dump()
    (tmp_path / "i.json").write_text(json.dumps([inst]))
    (tmp_path / "p.json").write_text(json.dumps([{"name": "someone_employed", "formal": PROPS["someone_employed"].formal}]))
    rc_ = main(["rules", "check-all", "--k", "3", "--institutions", str(tmp_path / "i.json"), "--properties", str(tmp_path / "p.json")])
    out = capsys.readouterr().out
    assert rc_ == 0
    hdr = out.splitlines()[0].split()
    assert hdr[-2:] == ["k", "init"]
    row = [l for l in out.splitlines() if l.startswith("tiny")][0].split()
    assert row[-2:] == ["3", "declared"]
    assert "step_mode=one" in out
    main(["rules", "check-all", "--k", "3", "--init", "empty", "--step-mode", "many",
          "--institutions", str(tmp_path / "i.json"), "--properties", str(tmp_path / "p.json")])
    out = capsys.readouterr().out
    assert "init=empty" in out and "step_mode=many" in out


# ------------------------------------------------------------ inert must-be rules, vacuity (review findings 3, 6)
from .test_rules_lower import derived_police  # noqa: E402


def test_inert_must_be_is_reported_and_breakable_one_is_not():
    inst = derived_police()
    props = {"cs": Property(name="cs", formal="(can_sanction officer subject t)")}
    rep = rc.run_all(inst, props, k=4, which={"cs": ["reachable"]})
    assert rep.inert == []  # neglect breaks provides_care while responding
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] != "R8"]  # no may neglect: neglect is unregulated, still breaks it
    rep = rc.run_all(InstitutionJSON.model_validate(d), props, k=4, which={"cs": ["reachable"]})
    assert rep.inert == []
    d["actions"] = [a for a in d["actions"] if a["name"] != "neglect"]  # nothing clears provides_care
    rep = rc.run_all(InstitutionJSON.model_validate(d), props, k=4, which={"cs": ["reachable"]})
    assert rep.inert == ["R2"]
    st = rep.rule_status[0]
    assert st.kind == "inert" and st.load_bearing and "no compliant trace" in st.detail
    # an exogenous (initial_free) fluent counts as a breaker: must_not danger-while-responding is breakable at t=0
    d2 = InstitutionJSON.model_validate(d).model_dump()
    d2["rules"].append({"id": "R9", "attribute": "officer", "deontic": "must_not", "aim": "(danger s)",
                        "conditions": "(responding o s)", "or_else": None, "strand": "tying", "var_roles": {"s": "subject"}})
    rep = rc.run_all(InstitutionJSON.model_validate(d2), props, k=4, which={"cs": ["reachable"]})
    assert "R9" not in rep.inert and "R2" in rep.inert


def test_vacuity_flags_on_invariant_and_persists():
    inst = derived_police()
    props = {
        "css": Property(name="css", formal="(forall ((x agent) (y agent)) (=> (and (provides_care x y t) (is_subject y t)) (can_sanction x y t)))"),
        "never": Property(name="never", formal="(forall ((s agent)) (=> (and (in_custody s t) (not (is_subject s t))) (can_exit s t)))"),
        "subj": Property(name="subj", formal="(forall ((s agent)) (=> (is_subject s t) (not (can_exit s t))))"),
    }
    rep = rc.run_all(inst, props, k=4, which={"css": ["invariant"], "never": ["invariant"], "subj": ["persists"]})
    by = {r.property: r for r in rep.results}
    assert by["css"].antecedent_reachable is True and by["css"].subject_exists is True and not by["css"].vacuous
    # custody without a subject never happens: holds_to_k, but vacuously
    assert by["never"].verdict == "holds_to_k" and by["never"].antecedent_reachable is False and by["never"].vacuous
    assert by["subj"].antecedent_reachable is True and by["subj"].subject_exists is True
    # no subject can ever exist: subject_exists False -> vacuous
    d = inst.model_dump()
    d["actions"][0]["effects"] = [e for e in d["actions"][0]["effects"] if e["fluent"] != "is_subject"]
    rep = rc.run_all(InstitutionJSON.model_validate(d), props, k=4, which={"subj": ["persists"]})
    r = rep.results[0]
    assert r.verdict == "persists" and r.subject_exists is False and r.vacuous
    # an institution with no is_* fluent: subject_exists is None (not applicable), never vacuous on that ground
    rep = rc.run_all(tiny(), PROPS, k=3, which={"paid_if_employed": ["invariant"]})
    assert rep.results[0].subject_exists is None and rep.results[0].antecedent_reachable is True
    assert not rep.results[0].vacuous


def test_antecedent_extraction():
    from philengine import sexpr as sx
    a = rc.antecedent(sx.parse("(forall ((x agent)) (=> (p x t) (q x t)))"))
    assert isinstance(a, sx.Quant) and a.kind == "exists" and a.body == sx.parse("(p x t)")
    f = sx.parse("(exists ((x agent)) (p x t))")
    assert rc.antecedent(f) is f


def test_cli_check_all_prints_flags_and_inert(capsys, tmp_path):
    import json
    from philengine.cli import main
    inst = derived_police().model_dump()
    inst["actions"] = [a for a in inst["actions"] if a["name"] != "neglect"]
    inst["rules"] = [r for r in inst["rules"] if r["id"] != "R8"]
    inst["expected_properties"] = {"never": "holds_to_k"}
    ip = tmp_path / "i.json"; pp = tmp_path / "p.json"
    ip.write_text(json.dumps([inst]))
    pp.write_text(json.dumps([{"name": "never", "formal": "(forall ((s agent)) (=> (and (in_custody s t) (not (is_subject s t))) (can_exit s t)))"}]))
    main(["rules", "check-all", "--k", "3", "--institutions", str(ip), "--properties", str(pp)])
    out = capsys.readouterr().out
    assert "flags" in out and "vacuous,antecedent-unreachable" in out
    assert "t-derived: inert R2 (load_bearing)" in out


# ------------------------------------------------------------ dataset falsifiers (second review 2026-11-03, items 1, 2)
def _dataset_inst(iid: str):
    ipath, ppath = require_dataset()
    return next(i for i in load_institutions(ipath) if i.id == iid), load_properties(ppath)


def _without(inst: InstitutionJSON, *rids: str) -> InstitutionJSON:
    d = inst.model_dump()
    d["rules"] = [r for r in d["rules"] if r["id"] not in rids]
    return InstitutionJSON.model_validate(d)


def test_deleting_police_sanction_rules_removes_the_bundled_power():
    """With `enabled` false for an action no may/must rule names, deleting police R3 (may detain) and R5 (may
    use_force) removes can_sanction: the old shape of care_and_sanction_same_role (care implies power) goes from
    holds to violated, and the current shape (no one but the carer sanctions) from a non-vacuous holds_to_k to a
    vacuous one (its antecedent, some sanction power, is unreachable)."""
    inst, props = _dataset_inst("police-crisis")
    old = Property(name="old_shape", formal="(forall ((x agent) (y agent)) (=> (and (provides_care x y t) (is_subject y t)) (can_sanction x y t)))")
    cur = props["care_and_sanction_same_role"]
    ps = {"old_shape": old, cur.name: cur}
    which = {n: ["invariant"] for n in ps}
    before = {r.property: r for r in rc.run_all(inst, ps, k=6, which=which).results}
    after = {r.property: r for r in rc.run_all(_without(inst, "R3", "R5"), ps, k=6, which=which).results}
    assert before[cur.name].verdict == "holds_to_k" and not before[cur.name].vacuous
    assert after[cur.name].verdict == "holds_to_k" and after[cur.name].vacuous and after[cur.name].antecedent_reachable is False
    assert before["old_shape"].verdict == "violated"  # power only while danger holds; care persists
    assert after["old_shape"].verdict == "violated"  # and never holds_to_k by an always-enabled unregulated action
    # what violates the current shape is a non-carer holding the power while someone else cares: crisis-team's R8
    ct, _ = _dataset_inst("crisis-team")
    rep = rc.run_all(ct, {cur.name: cur}, k=6, which={cur.name: ["invariant"]})
    assert rep.results[0].verdict == "violated" and not rep.results[0].vacuous
    assert rc.run_all(_without(ct, "R8"), {cur.name: cur}, k=6, which={cur.name: ["invariant"]}).results[0].verdict == "holds_to_k"


def test_removing_guardianship_R9_restores_no_standing():
    """companion-guardianship's `no_standing_persists: fails` rests on R9 (court may reassign on best interest) alone:
    without it reassign is unregulated, hence never enabled, and the property persists as in companion-ownership."""
    inst, props = _dataset_inst("companion-guardianship")
    p = props["no_standing_persists"]
    rep = rc.run_all(inst, {p.name: p}, k=6, which={p.name: ["persists"]})
    assert rep.results[0].verdict == "fails"
    rep = rc.run_all(_without(inst, "R9"), {p.name: p}, k=6, which={p.name: ["persists"]})
    assert rep.results[0].verdict == "persists" and not rep.results[0].vacuous
    assert any("(enabled reassign ...) names an action no may/must rule regulates" in w for w in rep.warnings)
