import re

from studytwin import tutor
from studytwin.context import build_context
from studytwin.retrieval import get_index


def test_hybrid_retrieval_finds_the_radar_slide(kb):
    hits = get_index().search("airplane radar registers P(B | A)=0.99", k=5)
    assert any("slide 5" in h.unit["label"] for h in hits)


def test_llmslim_budget_keeps_citations_and_verbatim_sentences(kb):
    hits = get_index().search("conditional probability definition", k=8)
    pack = build_context([h.unit for h in hits], "conditional probability definition", budget=500, use_llmslim=True)
    st = pack.stats
    assert st["llmslim"] and st["tokens_after"] < st["tokens_before"]
    assert all(f"[{b.tag}]" in pack.prompt_text for b in pack.blocks)  # every marker survives
    kept, total = map(int, st["verbatim_sentences"].split("/"))
    assert total > 0 and kept == total  # extractive: every kept sentence exists in the source


def test_offline_answer_is_cited_and_quotes_verify(kb):
    r = tutor.answer("What is the definition of conditional probability?", record=False)
    assert r["status"] == "answered" and r["citations"]
    assert re.search(r"\[S\d+\]", r["answer"])
    assert all(c["quote_status"] in ("exact", "approx") for c in r["citations"])


def test_low_support_question_is_declined(kb, monkeypatch):
    monkeypatch.setattr(tutor, "MIN_SUPPORT", 0.99)
    r = tutor.answer("Who won the 2011 Cricket World Cup?", record=False)
    assert r["status"] == "not_covered" and r["citations"] == []


def test_citation_normalization_and_quote_verification():
    assert tutor.normalize_citations("a【S1】 b [S2, S3] c (S4) d [S5†L2]") == "a[S1] b [S2][S3] c [S4] d [S5]"
    src = "Definition: Assuming P(B) != 0, P(A|B) = P(A and B)/P(B)."
    assert tutor.verify_quote("assuming P(B) != 0", src) == "exact"
    assert tutor.verify_quote("the moon is made of cheese", src) == "unverified"
