from fastapi.testclient import TestClient

from studytwin.eval.extras import wer
from studytwin.eval.rag_eval import unit_matches


def test_api_end_to_end(kb):
    from studytwin.api import app

    c = TestClient(app)
    h = c.get("/api/health").json()
    assert h["offline"] and h["counts"]["units"] > 50
    sid = c.post("/api/students", json={"name": "API"}).json()["id"]
    r = c.post("/api/chat", json={"student_id": sid, "message": "State the total probability theorem"}).json()
    assert r["citations"] and r["context_stats"]["citations_preserved"]
    unit = c.get(f"/api/units/{r['citations'][0]['unit_id']}").json()
    assert unit["view"]["type"] in ("textbook", "slides", "video")
    a = c.post("/api/assessments", json={"student_id": sid, "kind": "diagnostic"}).json()
    q = a["questions"][0]
    fb = c.post(f"/api/assessments/{a['id']}/answer", json={"question_id": q["id"], "response": "B"}).json()
    assert "correct_answer" in fb
    assert c.post(f"/api/assessments/{a['id']}/finish").json()["n"] == 1
    d = c.get(f"/api/students/{sid}/dashboard").json()
    assert len(d["mastery"]) == h["counts"]["topics"]
    assert c.get(f"/api/students/{sid}/schedule").json()["days"]
    assert c.get("/api/topics").json()["tree"]


def test_gold_location_matching():
    titles = {"s1": "OpenStax Ch.3", "s2": "6.041 Lecture 2"}
    page = {"source_id": "s1", "loc": {"page_label": 189}}
    clip = {"source_id": "s2", "loc": {"start": 1700.0, "end": 1760.0}}
    gold = [{"source": "OpenStax Ch.3", "pages": [189]}, {"source": "6.041 Lecture 2", "time": [1720, 1800]}]
    assert unit_matches(page, gold, titles) == 0 and unit_matches(clip, gold, titles) == 1
    assert unit_matches({"source_id": "s1", "loc": {"page_label": 200}}, gold, titles) is None


def test_word_error_rate():
    assert wer("a b c d".split(), "a b c d".split()) == 0
    assert wer("a b c d".split(), "a x c".split()) == 0.5
