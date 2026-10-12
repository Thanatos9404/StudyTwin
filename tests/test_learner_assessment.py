from studytwin import assessment, learner


def test_bkt_moves_in_the_right_direction():
    p = 0.4
    up, down, half = learner.bkt_update(p, 1.0), learner.bkt_update(p, 0.0), learner.bkt_update(p, 0.5)
    assert down < p < up and down < half < up
    # a correct MCQ (guessable) is weaker evidence than a correct numerical answer
    assert learner.bkt_update(p, 1.0, 2, "mcq") < learner.bkt_update(p, 1.0, 2, "numerical")


def test_difficulty_and_allocation_follow_mastery():
    assert learner.pick_difficulty(0.1) <= learner.pick_difficulty(0.95)
    state = {t: {"p": p, "last_ts": None, "half_life": 1.0} for t, p in {"T1": 0.9, "T2": 0.2, "T3": 0.5, "T4": 0.1}.items()}
    slots = learner.allocate(state, {}, 6, focus=2)
    assert set(slots) == {"T4", "T2"}  # the two weakest topics, not the mastered one
    assert learner.retention(1.0, 1.0) < 1.0


def test_answer_parsing():
    assert abs(assessment.parse_number("3/11") - 3 / 11) < 1e-9
    assert assessment.parse_number("34%") == 0.34
    assert assessment.numbers_match("0.3426", "0.342", 0.005)
    assert assessment.numbers_match("34.3", "0.343", 0.005)  # percent written without the sign
    assert not assessment.numbers_match("0.5", "0.342", 0.005)
    assert assessment.mcq_letter("(c) because...") == "C"


def test_assessment_flow_updates_mastery_and_never_repeats(kb):
    store = kb["store"]
    assert store.one("SELECT COUNT(*) n FROM questions WHERE verified=1")["n"] >= 5
    sid = "stu_test"
    store.insert("students", {"id": sid, "name": "Test", "created_at": 0, "intake": None, "profile": None})
    learner.set_intake(sid, {learner.topic_ids()[0]: 1})
    first = assessment.create_assessment(sid, "quiz", n=3, types=["mcq"], seed=1, allow_generate=False)
    for q in first["questions"]:
        fb = assessment.grade(first["id"], q["id"], "A")
        assert fb["citations"] and "mastery" in fb
    rep = assessment.report(first["id"])
    assert rep["n"] == len(first["questions"]) and "weak_topics" in rep
    second = assessment.create_assessment(sid, "quiz", n=3, types=["mcq"], seed=2, allow_generate=False)
    ids1 = {q["id"] for q in first["questions"]}
    ids2 = {q["id"] for q in second["questions"]}
    if store.one("SELECT COUNT(*) n FROM questions WHERE verified=1")["n"] >= 6:
        assert not ids1 & ids2
    assert store.many("SELECT * FROM mastery_log WHERE student_id=?", (sid,))


def test_diagnostic_covers_every_topic_with_questions(kb):
    store = kb["store"]
    sid = "stu_diag"
    store.insert("students", {"id": sid, "name": "New", "created_at": 0, "intake": None, "profile": None})
    a = assessment.create_assessment(sid, "diagnostic", seed=3, allow_generate=False)
    covered = {q["topic_id"] for q in a["questions"]}
    with_bank = {r["topic_id"] for r in store.many("SELECT DISTINCT topic_id FROM questions WHERE verified=1")}
    assert covered == with_bank & set(learner.topic_ids())
