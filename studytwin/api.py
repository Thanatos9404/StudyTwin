"""FastAPI backend; also serves the built React app (frontend/dist).

Run:  uvicorn studytwin.api:app --port 8765   (then open http://localhost:8765)
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assessment, learner, llm, retrieval, revision, store, topics, tutor
from .config import ROOT, settings
from .ingest.pdf import find_highlight
from .ingest.pipeline import SUPPORTED, ingest_source

settings.ensure_dirs()


def _warm() -> None:
    """Load the embedder, index and LLMSlim in the background so the first question is fast."""
    try:
        retrieval.get_index()
        tutor.retrieve("conditional probability", k=1)
        from llmslim import compress

        compress("Warm up the compressor. It has two sentences.", target_ratio=0.5, query="warm")
    except Exception:  # noqa: BLE001
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="StudyTwin", version="1.0.0", description="Adaptive multimodal study companion (Track D)", lifespan=lifespan)
FRONTEND = ROOT / "frontend" / "dist"  # React app (npm run build); committed so no Node is needed to run
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")
if (FRONTEND / "demo").exists():
    app.mount("/demo", StaticFiles(directory=str(FRONTEND / "demo")), name="demo")
app.mount("/media", StaticFiles(directory=str(settings.media_dir)), name="media")
EVAL_DIR = ROOT / "eval" / "results"


@app.get("/")
def index():
    page = FRONTEND / "index.html"
    if page.exists():
        return FileResponse(page)
    return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm install && npm run build"}, status_code=503)


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    return FileResponse(FRONTEND / "favicon.svg", media_type="image/svg+xml")


# ---- system ------------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    c = lambda sql: (store.one(sql) or {}).get("n", 0)  # noqa: E731
    return {
        "llm": llm.available(), "offline": not llm.available(), "provider": "Nebius Token Factory" if llm.available() else None,
        "models": {k: getattr(settings, k).id for k in ("tutor_model", "generator_model", "verifier_model", "vision_model", "judge_model")},
        "embedder": settings.embedder, "llmslim": settings.use_llmslim, "context_budget": settings.context_budget,
        "counts": {"sources": c("SELECT COUNT(*) n FROM sources"), "units": c("SELECT COUNT(*) n FROM units"),
                   "topics": c("SELECT COUNT(*) n FROM topics WHERE parent_id IS NULL"),
                   "questions": c("SELECT COUNT(*) n FROM questions WHERE verified=1"),
                   "students": c("SELECT COUNT(*) n FROM students")},
        "usage": llm.meter.snapshot(),
    }


# ---- sources & ingestion -----------------------------------------------------------------

def _run_ingest(job_id: str, kwargs: dict[str, Any]) -> None:
    store.job_update(job_id, status="running", progress=0.01, message="Starting")
    try:
        sid = ingest_source(**kwargs, progress=lambda f, m: store.job_update(job_id, progress=f, message=m))
        if not topics.has_topics():
            store.job_update(job_id, progress=0.97, message="Building the course topic map")
            topics.build_topics()
        n = store.one("SELECT COUNT(*) n FROM units WHERE source_id=?", (sid,))["n"]
        store.job_update(job_id, status="done", progress=1.0, message=f"Ingested {n} units", result={"source_id": sid, "units": n})
    except Exception as e:  # noqa: BLE001
        store.job_update(job_id, status="error", message=str(e)[:300])


@app.get("/api/sources")
def sources() -> list[dict[str, Any]]:
    out = []
    for s in store.many("SELECT * FROM sources ORDER BY created_at"):
        counts = store.many("SELECT kind, COUNT(*) n FROM units WHERE source_id=? GROUP BY kind", (s["id"],))
        s["unit_counts"] = {c["kind"]: c["n"] for c in counts}
        s.pop("path", None)
        out.append(s)
    return out


@app.post("/api/sources")
async def upload(background: BackgroundTasks, file: UploadFile = File(...), kind: str = Form(""), title: str = Form(""),
                 license: str = Form("")) -> dict[str, Any]:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "upload")
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(400, f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED))}")
    tmp_dir = settings.uploads_dir / "incoming" / store.new_id()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / name
    with tmp.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    jid = store.job_create("ingest")
    kwargs = {"path": tmp, "kind": kind or None, "title": title or None, "short_title": (title or Path(name).stem)[:28],
              "license": license}
    background.add_task(_run_ingest, jid, kwargs)
    return {"job_id": jid}


class YouTubeIn(BaseModel):
    url: str
    title: str = ""


@app.post("/api/sources/youtube")
def add_youtube(body: YouTubeIn, background: BackgroundTasks) -> dict[str, Any]:
    jid = store.job_create("ingest")
    background.add_task(_run_ingest, jid, {"youtube_url": body.url, "title": body.title or None})
    return {"job_id": jid}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    j = store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.get("/api/sources/{source_id}/file")
def source_file(source_id: str) -> FileResponse:
    s = store.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not s or not s.get("path") or not Path(s["path"]).exists():
        raise HTTPException(404, "file not available locally")
    return FileResponse(s["path"], filename=s.get("filename") or None, content_disposition_type="inline")


@app.get("/api/units/{unit_id}")
def unit(unit_id: str, q: str = "") -> dict[str, Any]:
    u = store.one("SELECT * FROM units WHERE id=?", (unit_id,))
    if not u:
        raise HTTPException(404, "unit not found")
    s = store.one("SELECT * FROM sources WHERE id=?", (u["source_id"],)) or {}
    view: dict[str, Any] = {"type": s.get("kind")}
    loc = u["loc"] or {}
    if s.get("kind") == "textbook":
        view["page_image"] = f"/media/{u['page_image']}" if u.get("page_image") else None
        view["page"] = loc.get("page")
        view["page_label"] = loc.get("page_label")
        view["pdf_url"] = f"/api/sources/{s['id']}/file#page={loc.get('page')}" if s.get("path") else None
        snippet = q or u["text"][:160]
        rects: list[list[float]] = []
        if u["kind"] == "figure" and loc.get("bbox"):
            l, b, r, t = loc["bbox"]
            H = (loc.get("page_size") or [612, 792])[1]
            rects = [[l, H - t, r - l, t - b]]
        elif s.get("path") and Path(s["path"]).exists() and loc.get("page"):
            try:
                rects = find_highlight(Path(s["path"]), loc["page"], snippet)
            except Exception:  # noqa: BLE001
                rects = []
        view["highlights"] = rects
        view["page_size"] = loc.get("page_size") or [612, 792]
    elif s.get("kind") == "slides":
        view["slide"] = loc.get("slide")
        view["image"] = f"/media/{u['image']}" if u.get("image") else None
        view["page_image"] = f"/media/{u['page_image']}" if u.get("page_image") else None
        view["pdf_url"] = f"/api/sources/{s['id']}/file#page={loc.get('page')}" if s.get("path") and loc.get("page") else None
    else:
        meta = s.get("meta") or {}
        view["start"], view["end"] = loc.get("start", 0), loc.get("end")
        if meta.get("youtube_id"):
            view["youtube_id"] = meta["youtube_id"]
        local = s.get("path") and Path(s["path"]).exists() and Path(s["path"]).suffix.lower() not in (".srt", ".vtt")
        view["video_url"] = f"/api/sources/{s['id']}/file" if local else (s.get("remote_url") or None)
    s.pop("path", None)
    return {"unit": u, "source": s, "view": view}


# ---- topics --------------------------------------------------------------------------------

@app.get("/api/topics")
def get_topics(student_id: str = "") -> dict[str, Any]:
    mastery = {m["topic_id"]: m["p"] for m in learner.summary(student_id)} if student_id else None
    return {"tree": topics.topic_tree(), "mermaid": topics.mermaid(mastery)}


@app.post("/api/topics/rebuild")
def rebuild_topics() -> dict[str, Any]:
    return topics.build_topics()


# ---- students ------------------------------------------------------------------------------

class StudentIn(BaseModel):
    name: str


@app.post("/api/students")
def create_student(body: StudentIn) -> dict[str, Any]:
    sid = store.new_id("stu_")
    store.insert("students", {"id": sid, "name": body.name.strip()[:60] or "Student", "created_at": time.time(), "intake": None, "profile": None})
    return store.one("SELECT * FROM students WHERE id=?", (sid,)) or {}


@app.get("/api/students")
def list_students() -> list[dict[str, Any]]:
    return store.many("SELECT * FROM students ORDER BY created_at")


class IntakeIn(BaseModel):
    ratings: dict[str, int]
    goals: str = ""


@app.post("/api/students/{student_id}/intake")
def intake(student_id: str, body: IntakeIn) -> dict[str, Any]:
    learner.set_intake(student_id, body.ratings, body.goals)
    return {"mastery": learner.summary(student_id)}


@app.get("/api/students/{student_id}/dashboard")
def dashboard(student_id: str) -> dict[str, Any]:
    st = store.one("SELECT * FROM students WHERE id=?", (student_id,))
    if not st:
        raise HTTPException(404, "student not found")
    summ = learner.summary(student_id)
    log = store.many("SELECT topic_id, ts, p_before, p_after, event FROM mastery_log WHERE student_id=? ORDER BY ts", (student_id,))
    assessments = store.many("SELECT id, kind, created_at, finished_at, report FROM assessments WHERE student_id=? ORDER BY created_at DESC", (student_id,))
    attempts = store.one("SELECT COUNT(*) n, SUM(score) s FROM attempts WHERE student_id=?", (student_id,)) or {}
    chats = store.one("SELECT COUNT(*) n FROM chat WHERE student_id=? AND role='user'", (student_id,)) or {}
    weak = sorted([m for m in summ if m["p"] < 0.5], key=lambda m: m["p"])
    return {
        "student": st, "mastery": summ, "log": log,
        "assessments": [{"id": a["id"], "kind": a["kind"], "created_at": a["created_at"], "finished": bool(a["finished_at"]),
                         "accuracy": (a["report"] or {}).get("accuracy") if a["report"] else None,
                         "weak_topics": (a["report"] or {}).get("weak_topics") if a["report"] else None} for a in assessments],
        "answered": attempts.get("n") or 0, "score_sum": attempts.get("s") or 0, "questions_asked": chats.get("n") or 0,
        "weak_topics": weak, "mermaid": topics.mermaid({m["topic_id"]: m["p"] for m in summ}),
        "is_new": not log and not (st.get("intake")),
    }


@app.get("/api/students/{student_id}/schedule")
def get_schedule(student_id: str, exam_date: str = "", minutes: int = 45) -> dict[str, Any]:
    return revision.schedule(student_id, exam_date or None, minutes)


@app.get("/api/topics/{topic_id}/flashcards")
def get_flashcards(topic_id: str, n: int = 6) -> list[dict[str, Any]]:
    return revision.flashcards(topic_id, n)


# ---- tutor ---------------------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str
    student_id: str | None = None
    lang: str = "en"
    allow_outside: bool = False
    history: list[dict[str, str]] = Field(default_factory=list)


@app.post("/api/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    out = tutor.answer(body.message.strip(), student_id=body.student_id, history=body.history[-6:], lang=body.lang,
                       allow_outside=body.allow_outside)
    out.pop("contexts", None)
    return out


# ---- assessments ---------------------------------------------------------------------------

class AssessmentIn(BaseModel):
    student_id: str
    kind: str = "quiz"
    topic_ids: list[str] = Field(default_factory=list)
    n: int = 6
    types: list[str] = Field(default_factory=lambda: ["mcq", "numerical", "short"])


@app.post("/api/assessments")
def new_assessment(body: AssessmentIn) -> dict[str, Any]:
    if body.kind not in ("quiz", "mock", "diagnostic"):
        raise HTTPException(400, "kind must be quiz, mock or diagnostic")
    return assessment.create_assessment(body.student_id, body.kind, body.topic_ids or None, max(1, min(body.n, 20)), body.types)


class AnswerIn(BaseModel):
    question_id: str
    response: str


@app.post("/api/assessments/{assessment_id}/answer")
def answer_question(assessment_id: str, body: AnswerIn) -> dict[str, Any]:
    try:
        return assessment.grade(assessment_id, body.question_id, body.response)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/assessments/{assessment_id}/finish")
def finish(assessment_id: str) -> dict[str, Any]:
    try:
        return assessment.report(assessment_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/bank")
def bank_stats() -> dict[str, Any]:
    rows = store.many("SELECT topic_id, type, difficulty, verified, COUNT(*) n FROM questions GROUP BY 1,2,3,4")
    return {"rows": rows}


# ---- evaluation ----------------------------------------------------------------------------

@app.get("/api/eval")
def eval_results() -> JSONResponse:
    out: dict[str, Any] = {}
    if EVAL_DIR.exists():
        for p in sorted(EVAL_DIR.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return JSONResponse(out)
