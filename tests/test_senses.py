"""Sense-drift guards (senses.py, store registry) and the soft biconditional penalty in select."""
from philengine import checks, config, senses
from philengine.models_ext import FormalizationX, JudgeReportX, PremiseX, ReconstructionX
from philengine.stage_select import select_for
from philengine.store import Store
from philengine.verbalize import verbalization_text


def fx(preds, premises, concl, consts=()):
    return FormalizationX.model_validate({
        "predicates": [{"name": n, "arg_sorts": ["Obj"] * a, "gloss": g, "sense": s} for n, a, g, s in preds],
        "constants": [{"name": n, "sort": "Obj", "gloss": g, "sense": s} for n, g, s in consts],
        "premises": [{"premise_id": f"P{i + 1}", "sexpr": x} for i, x in enumerate(premises)],
        "conclusion": {"premise_id": "C", "sexpr": concl}})


def rec(*texts, implicit=(), types=None):
    ps = [PremiseX(id=f"P{i + 1}", text=t, implicit=(i + 1) in implicit, type=(types or {}).get(i + 1, "empirical"))
          for i, t in enumerate(texts)]
    return ReconstructionX(premises=ps, conclusion="C text")


ANSELM = rec("God exists in the understanding.", "If God exists in the understanding then God exists in reality.")
SPLIT_PREDS = [("exists_in_understanding", 1, "{0} exists in the understanding", "exists:in-understanding"),
               ("exists_in_reality", 1, "{0} exists in reality", "exists:in-reality")]


def test_equivocated_anselm_gets_hint():
    # P1 says "in the understanding" but is formalized with the in-reality symbol
    f = fx(SPLIT_PREDS, ["(exists_in_reality god)", "(=> (exists_in_understanding god) (exists_in_reality god))"],
           "(exists_in_reality god)", consts=[("god", "God", "person:god")])
    hints = senses.mismatch_hints(f, ANSELM)
    assert len(hints) == 1 and hints[0].startswith("P1:") and "exists_in_understanding" in hints[0]


def test_correctly_split_anselm_no_hint():
    f = fx(SPLIT_PREDS, ["(exists_in_understanding god)",
                         "(=> (exists_in_understanding god) (exists_in_reality god))"],
           "(exists_in_reality god)", consts=[("god", "God", "person:god")])
    assert senses.mismatch_hints(f, ANSELM) == []


def test_gloss_collision_error():
    f = fx([("exists_in_reality", 1, "{0} exists", "exists:in-reality"),
            ("exists_in_understanding", 1, "{0}  Exists", "exists:in-understanding")], ["(exists_in_reality god)"],
           "(exists_in_reality god)", consts=[("god", "God", "person:god")])
    errs = senses.gloss_collision_errors(f)
    assert len(errs) == 1 and errs[0].startswith("sense_gloss_collision")
    assert senses.gloss_collision_errors(fx(SPLIT_PREDS, ["(exists_in_reality god)"], "(exists_in_reality god)",
                                           consts=[("god", "God", "person:god")])) == []


def test_formalize_retries_on_gloss_collision_and_records_hint():
    from philengine.llm import MockLLMClient
    from philengine.runner import Ctx, Unit
    from philengine import stage_formalize
    st = Store(":memory:")
    st.ingest_argument({"id": "a", "reconstruction": {"premises": [
        {"id": "P1", "text": "God exists in the understanding.", "type": "empirical"}], "conclusion": "God exists in reality."}})
    r = st.latest_reconstruction("a", "human")
    bad = fx([("p", 0, "x holds", "s1"), ("q", 0, "x holds", "s2")], ["p"], "q").model_dump()
    good = fx([("p", 0, "x holds one way", "s1"), ("q", 0, "x holds another way", "s2")], ["p"], "q").model_dump()

    class L(MockLLMClient):
        n = 0
        prompts = []

        def _complete(self, *, user, **_):
            import json
            L.prompts.append(user)
            L.n += 1
            return json.dumps(bad if L.n == 1 else good), 0, 0
    rid = st.new_run(mock=True)
    ctx = Ctx(store=st, llm=L(st, rid), run_id=rid, options={})
    stage_formalize.formalize_one(ctx, "a", r, 0)
    assert L.n == 2 and "sense_gloss_collision" in L.prompts[1]
    assert st.list_formalizations(r.id)[0].status == "ok"


def test_legend_and_mock_parse_contract():
    f = fx([("human", 1, "{0} is human", "human:biological"), ("mortal", 1, "{0} is mortal", "mortal:ceases-to-live")],
           ["(forall ((x Obj)) (=> (human x) (mortal x)))"], "(forall ((x Obj)) (mortal x))")
    t = verbalization_text(f, show_symbols=True)
    assert t.splitlines()[0] == ("[P1] For every Obj x: if x is human then x is mortal"
                                 "  {human=human:biological, mortal=mortal:ceases-to-live}")
    assert verbalization_text(f) == "\n".join(l.split("  {")[0] for l in t.splitlines())
    from philengine.llm import _LINE_ID
    assert _LINE_ID.findall(t) == ["P1", "C"]


def test_registry_sense_split_and_alias():
    st = Store(":memory:")
    st.upsert_concept("exists", "{0} exists in reality", "exists:in-reality", "anselm")
    st.upsert_concept("exists", "{0} exists in thought", "exists:in-understanding", "descartes")
    assert len(st.concepts_by_label("exists")) == 2  # not merged
    (rel,) = st.relations("sense-split")
    assert rel["src_id"] == "exists" and rel["evidence"]["senses"] == ["exists:in-reality", "exists:in-understanding"]
    assert rel["evidence"]["argument_ids"] == ["anselm", "descartes"]
    assert any("label reused across senses" in r["reason"] for r in st.query("SELECT reason FROM review"))
    st.upsert_concept("real_existence", "{0} is real", "exists:in-reality", "kant")
    (al,) = st.relations("sense-alias")
    assert al["src_id"] == "real_existence" and al["dst_id"] == "exists"
    assert len(st.concepts_by_sense("exists:in-reality")) == 2
    n = len(st.relations())
    st.upsert_concept("exists", "{0} exists in reality", "exists:in-reality", "anselm")  # idempotent
    assert len(st.relations()) == n


# ---- select: soft biconditional ----
def _select(types, implicit):
    st = Store(":memory:")
    r = rec("D holds.", "D iff C.", types=types, implicit=implicit)
    st.ingest_argument({"id": "m", "reconstruction": r.model_dump()})
    rid = st.latest_reconstruction("m", "human").id
    f = fx([("c", 0, "C holds", "s:c"), ("d", 0, "D holds", "s:d")], ["d", "(iff c d)"], "c")
    chk = checks.run_all(f)
    assert chk.suspect_biconditional == ["P2"] and chk.nontrivial is True
    j = JudgeReportX(back_translations={}, scores={"P1": 0.9, "P2": 0.9}, conclusion_score=0.9,
                     min_score=0.9, mean_score=0.9, flags=[], per_item_comments={})
    st.insert_formalization(rid, 0, "ok", f, chk, j)
    return st, select_for(st, rid), rid


def _score_without_penalty(st, rid):
    from philengine.stage_select import score
    form = st.list_formalizations(rid)[0]
    return round(score(form, 2), 6)


def test_select_penalizes_implicit_biconditional():
    st, sel, rid = _select({2: "definitional"}, implicit=(2,))
    e = sel.ranking[0]
    assert e["score"] == round(_score_without_penalty(st, rid) - config.SUSPECT_BICONDITIONAL_PENALTY, 6)
    assert sel.chosen_formalization_id is not None  # penalized, not rejected
    assert any("implicit/non-definitional biconditional" in r["reason"] for r in st.query("SELECT reason FROM review"))


def test_select_penalizes_nondefinitional_biconditional():
    st, sel, rid = _select({2: "empirical"}, implicit=())
    assert sel.ranking[0]["score"] < _score_without_penalty(st, rid)


def test_select_explicit_definitional_biconditional_no_penalty():
    st, sel, rid = _select({2: "definitional"}, implicit=())
    e = sel.ranking[0]
    assert e["score"] == _score_without_penalty(st, rid)
    assert e["notes"] and "definitional bridge" in e["notes"][0]
    assert not st.query("SELECT 1 FROM review WHERE reason LIKE '%biconditional%'")
