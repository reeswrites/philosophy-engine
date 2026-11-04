"""rules_gate: criteria (a)-(f). Synthetic datasets exercise the precommitted-level logic, negative controls, the
preregistered minimal-pair property and inert load-bearing rules; the real-dataset tests are skipped until the
dataset is re-encoded against the ADR 0013 schema (derived power fluents, not_isomorphic_to_control,
minimal_pair_of.differs_on, load_bearing)."""
import subprocess
import sys

import pytest

from philengine import rules_checks as rc
from philengine import rules_gate as rg
from philengine.schemas_rules import InstitutionJSON, Property, default_paths, load_institutions, load_properties

from .test_rules_iso import care_control, lease
from .test_rules_lower import derived_police


def _dataset_reencoded() -> bool:
    insts = load_institutions(default_paths()[0])
    return any(i.derived_fluents() for i in insts) and any(i.not_isomorphic_to_control for i in insts)


awaiting = pytest.mark.skipif(not _dataset_reencoded(), reason="awaiting dataset re-encode (ADR 0013: derived power "
                              "fluents, not_isomorphic_to_control, minimal_pair_of.differs_on, load_bearing)")


# ------------------------------------------------------------ synthetic cluster
def cluster(level="guard+strands", sub=("R2~R2", "R3~R3", "R4~R4"), controls=("lease",)):
    # each member carries one rule the others lack, so the cluster is partial (care + control), never fully iso
    cov = care_control("coverture-household", "husband", "wife", "maintain", "chastise", "leave", extra=[
        {"id": "R5", "attribute": "wife", "deontic": "must_not", "aim": "(misc a)", "conditions": "true", "or_else": None, "strand": "tying"}])
    pol = care_control("police-crisis", "officer", "subject", "provides_care", "use_force", "walk", extra=[
        {"id": "R5", "attribute": "officer", "deontic": "may", "aim": "(misc a)", "conditions": "true", "strand": "tying"}])
    cps = care_control("cps", "social_worker", "child", "in_home_considered", "remove", "run", extra=[
        {"id": "R5", "attribute": "social_worker", "deontic": "must", "aim": "(misc a)", "conditions": "(bound a child)", "or_else": None, "strand": "tying"}])
    pol.rules[2].conditions = "(and (bound a b) (provides_care a b))"  # exact conditions differ across members
    cps.rules[2].conditions = "(and (bound a b) (not (in_home_considered a b)))"
    team = care_control("crisis-team", "responder", "subject", "provides_care", "refer", "walk", bar=False)
    team.rules[2].strand = "superadditive"  # refer is support, not control
    by = {}
    for i in (cov, pol, cps):
        d = i.model_dump()
        d["isomorphic_to"] = [{"id": j.id, "level": level, "sub_signature": list(sub)} for j in (cov, pol, cps) if j.id != i.id]
        d["not_isomorphic_to"] = ["crisis-team"]
        d["not_isomorphic_to_control"] = list(controls)
        by[i.id] = InstitutionJSON.model_validate(d)
    by["crisis-team"] = team
    by["lease"] = lease()
    return by


def test_crit_b_passes_at_the_precommitted_level_with_controls():
    c = rg.crit_b(cluster())
    assert c.status == "PASS", c.detail
    assert "coverture-household~police-crisis@guard+strands: partial(care+control)" in c.detail
    assert "crisis-team: none at every level" in c.detail
    assert "coverture-household~lease (control): none@guard+strands" in c.detail
    assert any("care+control: care R2" in l for l in c.lines)


def test_crit_b_match_at_another_level_is_a_finding_not_a_pass():
    by = cluster(level="exact")  # at exact conditions the three share nothing: the claim fails
    c = rg.crit_b(by)
    assert c.status == "FAIL"
    assert "coverture-household~police-crisis@exact: no care+control form" in c.detail
    assert any("matches at guard+strands" in f and "not counted" in f for f in c.findings), c.findings


def test_crit_b_precommitted_sub_signature_must_be_matched():
    c = rg.crit_b(cluster(sub=("R2~R2", "R3~R1")))
    assert c.status == "FAIL"
    assert "precommitted pairs not matched: R3~R1" in c.detail


def test_crit_b_negative_control_that_matches_fails_and_controls_are_required():
    by = cluster(controls=("police-crisis",))  # a cluster member as its own control: it matches, so FAIL
    c = rg.crit_b(by)
    assert c.status == "FAIL" and "(control): partial(care+control)@guard+strands" in c.detail
    c = rg.crit_b(cluster(controls=()))
    assert c.status == "FAIL" and "no negative controls" in c.detail
    c = rg.crit_b(cluster(controls=("missing",)))
    assert c.status == "FAIL" and "control 'missing' not in dataset" in c.detail


def test_crit_b_unbundled_control_matching_fails():
    by = cluster()
    bad = care_control("crisis-team", "responder", "subject", "provides_care", "detain", "walk")  # bundled after all
    by["crisis-team"] = bad
    c = rg.crit_b(by)
    assert c.status == "FAIL" and "crisis-team: partial(care+control)@" in c.detail


# ------------------------------------------------------------ (c) preregistered property
def _pair(differs_on="css", drop_rule="R4"):
    """The pair differs on R4 alone: the b side's `may use_force` is unconditional, so the officer's power never
    lapses and css (care implies power) holds there but not on the a side (deleting R4 outright no longer changes any
    verdict: an unregulated action is never enabled, ADR 0013 amendment)."""
    a = derived_police(id="paternity-quota")
    d = a.model_dump()
    d["id"] = "transferable-leave"
    d["rules"] = [r if r["id"] != drop_rule else {**r, "conditions": "true"} for r in d["rules"]]
    d["minimal_pair_of"] = {"id": "paternity-quota", "rule": drop_rule, "differs_on": differs_on}
    b = InstitutionJSON.model_validate(d)
    props = {
        "css": Property(name="css", formal="(forall ((x agent) (y agent)) (=> (and (provides_care x y t) (is_subject y t)) (can_sanction x y t)))"),
        "custody": Property(name="custody", formal="(in_custody subject t)"),
        "force": Property(name="force", formal="(can_sanction officer subject t)"),
    }
    for i in (a, b):
        i.expected_properties = {"css": "holds_to_k", "custody": "reachable", "force": "reachable"}
    by = {a.id: a, b.id: b}
    reports = {i.id: rc.run_all(i, props, k=3) for i in by.values()}
    return by, reports


def test_crit_c_tests_the_preregistered_property_only():
    by, reports = _pair(differs_on="css")  # without R4 (may use_force) the power is detain-only: css differs?
    c = rg.crit_c(by, reports)
    va, vb = reports["paternity-quota"].verdict("css"), reports["transferable-leave"].verdict("css")
    assert (c.status == "PASS") == (va != vb), c.detail
    # a property that does not differ is preregistered: FAIL even though others differ (those are findings)
    by, reports = _pair(differs_on="custody")
    c = rg.crit_c(by, reports)
    assert c.status == "FAIL" and "preregistered custody: same" in c.detail
    assert any("not preregistered; not counted" in f for f in c.findings)
    # no preregistration: FAIL
    by, reports = _pair()
    by["transferable-leave"].minimal_pair_of = {"id": "paternity-quota", "rule": "R4"}
    c = rg.crit_c(by, reports)
    assert c.status == "FAIL" and "differs_on is not set" in "\n".join(c.lines)


def test_crit_c_post_hoc_property_is_never_called_preregistered():
    """Second review item 7: a differs_on marked postregistered prints as "post hoc", and the property it
    supersedes has its verdicts for the pair printed as a finding."""
    by, reports = _pair(differs_on="css")
    by["transferable-leave"].minimal_pair_of = {"id": "paternity-quota", "rule": "R4", "differs_on": "css",
                                                "postregistered": True, "supersedes": "custody"}
    c = rg.crit_c(by, reports)
    text = c.detail + "\n" + "\n".join(c.lines) + "\n" + "\n".join(c.findings)
    assert "preregistered css" not in text and "post hoc css" in c.detail
    assert "post hoc property css" in "\n".join(c.lines)
    assert any("originally preregistered property custody: reachable vs reachable" in f for f in c.findings)
    assert all("not preregistered" not in f for f in c.findings)
    # without the flag the wording is unchanged
    by, reports = _pair(differs_on="css")
    c = rg.crit_c(by, reports)
    assert "preregistered css" in c.detail and not any("originally preregistered" in f for f in c.findings)


# ------------------------------------------------------------ (a) inert load-bearing rules
def test_crit_a_fails_on_inert_load_bearing_rule():
    inst = derived_police()
    d = inst.model_dump()
    d["actions"] = [a for a in d["actions"] if a["name"] != "neglect"]
    d["rules"] = [r for r in d["rules"] if r["id"] != "R8"]
    stuck = InstitutionJSON.model_validate(d)
    props = {"cs": Property(name="cs", formal="(can_sanction officer subject t)")}
    rep = rc.run_all(stuck, props, k=3, which={"cs": ["reachable"]})
    c = rg.crit_a([stuck], {stuck.id: rep})
    assert c.status == "FAIL" and "load-bearing rule(s) inert: t-derived:R2" in c.detail
    d["rules"][1]["load_bearing"] = False
    loose = InstitutionJSON.model_validate(d)
    rep = rc.run_all(loose, props, k=3, which={"cs": ["reachable"]})
    c = rg.crit_a([loose], {loose.id: rep})
    assert c.status == "PASS" and "1 inert must-be rule(s), none load-bearing" in c.detail
    assert any("inert t-derived R2" in l for l in c.lines)


def test_format_gate_prints_findings():
    by = cluster(level="exact")
    rep = rg.GateReport([rg.crit_b(by)])
    txt = rg.format_gate(rep, verbose=True)
    assert "findings (true, not counted):" in txt and "[b]" in txt and "GATE FAIL" in txt


# ------------------------------------------------------------ real dataset
@awaiting
def test_gate_f_over_real_dataset():
    insts = load_institutions(default_paths()[0])
    by = {i.id: i for i in insts}
    c = rg.crit_f(by, insts)
    assert c.status == "PASS", c.detail
    assert "pure_rename=True" in c.detail and "distance=1" in c.detail
    cross = [l for l in c.lines if l.strip().startswith("cross ")]
    assert cross, "every human/non-human pair must be printed with its sub-signature"
    assert all("matched=" in l and "unmatched=" in l for l in cross)
    assert "bare iso" not in c.detail


@awaiting
def test_gate_b_c_d_over_real_dataset():
    insts = load_institutions(default_paths()[0])
    by = {i.id: i for i in insts}
    b = rg.crit_b(by)
    assert b.status == "PASS", b.detail
    assert "crisis-team: none at every level" in b.detail
    assert "(control): none@" in b.detail
    assert rg.crit_d(by).status == "deferred"


@awaiting
def test_full_gate_passes():
    insts = load_institutions(default_paths()[0])
    props = load_properties(default_paths()[1])
    rep = rg.run_gate(insts, props)
    assert rep.passed, rg.format_gate(rep, verbose=True)
    assert rep.agreement is not None and rep.agreement >= rg.AGREEMENT_MIN
    keys = [c.key for c in rep.criteria]
    assert keys == ["a", "b", "c", "d", "e", "f"]


@awaiting
def test_cli_iso_and_gate():
    out = subprocess.run([sys.executable, "-m", "philengine.cli", "rules", "iso", "--pair", "companion-ownership",
                          "companion-guardian-renamed"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "iso=True pure_rename=True" in out.stdout
    out = subprocess.run([sys.executable, "-m", "philengine.cli", "rules", "gate"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "GATE PASS" in out.stdout


def test_cli_gate_runs_and_reports_findings_on_current_dataset():
    """Whatever the dataset's state, the gate runs end to end and prints the per-criterion table."""
    out = subprocess.run([sys.executable, "-m", "philengine.cli", "rules", "gate", "--k", "3"], capture_output=True, text=True)
    assert out.returncode in (0, 1), out.stderr
    assert "criterion" in out.stdout and "GATE" in out.stdout
