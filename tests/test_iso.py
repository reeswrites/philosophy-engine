import json
from pathlib import Path

import pytest

from philengine import stage_iso as iso
from philengine.models_ext import FormalizationX

from .helpers import FIX, load

ISO = Path(__file__).parent / "fixtures" / "iso"


def sk(name, aid=None, d=ISO):
    f = FormalizationX.model_validate(json.loads((d / f"{name}.json").read_text()))
    s = iso.skeleton(aid or name, f)
    assert s is not None
    return s


def test_isomorphic_under_nontrivial_mapping():
    a, b = sk("iso_a"), sk("iso_b")
    assert a.hash == b.hash
    ev = iso.match(a, b)
    assert ev and ev["z3_verified"] and ev["method"] == "hash"
    assert ev["mapping"] == {"loves": "admires", "kind": "wise", "happy": "proud", "ann": "cat", "bob": "dog"}


def test_false_friend_not_matched():
    a, f = sk("iso_a"), sk("iso_false_friend")
    assert a.hash != f.hash  # differs in one premise
    assert iso.match(a, f) is None and iso.match(f, a) is None


def test_modus_ponens_vs_affirming_consequent():
    mp = sk("modus_ponens", d=FIX)
    ac = sk("affirming_consequent", d=FIX)
    assert mp.hash != ac.hash and iso.match(mp, ac) is None


def test_modus_ponens_self_and_renamed():
    mp = sk("modus_ponens", d=FIX)
    ren = json.loads((FIX / "modus_ponens.json").read_text())
    for p in ren["predicates"]:
        p["name"] = {"rains": "snows", "wet": "white"}[p["name"]]
    ren["premises"][0]["sexpr"] = "(=> snows white)"
    ren["premises"][1]["sexpr"] = "snows"
    ren["conclusion"]["sexpr"] = "white"
    other = iso.skeleton("mp2", FormalizationX.model_validate(ren))
    ev = iso.match(mp, other)
    assert ev and ev["mapping"] == {"rains": "snows", "wet": "white"}


def test_hash_collision_caught_by_mapping_and_z3(monkeypatch):
    a, f = sk("iso_a"), sk("iso_false_friend")
    f.hash = a.hash  # force a collision
    assert iso.match(a, f) is None  # mapping search / Z3 stage refuses


def test_z3_stage_rejects_wrong_mapping():
    a, b = sk("iso_a"), sk("iso_b")
    bad = {"loves": "admires", "kind": "proud", "happy": "wise", "ann": "cat", "bob": "dog"}
    assert not iso.z3_confirm(a, b, bad)


def test_match_all_and_eval(tmp_path):
    from philengine.store import Store
    skels = [sk("iso_a"), sk("iso_b"), sk("iso_false_friend")]
    pairs = iso.match_all(skels)
    assert [(x.argument_id, y.argument_id) for x, y, _ in pairs] == [("iso_a", "iso_b")]
