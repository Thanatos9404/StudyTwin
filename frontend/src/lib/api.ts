// Typed client for the StudyTwin FastAPI backend.

export type Loc = { page?: number; page_label?: number; slide?: number; start?: number; end?: number; bbox?: number[]; page_size?: number[] };

export type Citation = {
  tag: string;
  unit_id: string;
  label: string;
  kind: string;
  section: string;
  source_kind: "textbook" | "slides" | "video" | string;
  source_title: string;
  loc: Loc;
  image?: string | null;
  page_image?: string | null;
  excerpt: string;
  quote: string;
  quote_status: "exact" | "approx" | "unverified" | "";
};

export type ContextStats = {
  llmslim: boolean;
  tokens_before: number;
  tokens_after: number;
  budget: number;
  blocks: number;
  ms: number;
  saved_pct: number;
  citations_preserved: string;
  verbatim_sentences?: string;
};

export type ChatAnswer = {
  question: string;
  status: "answered" | "partial" | "not_covered";
  answer: string;
  citations: Citation[];
  outside_knowledge: string;
  student_signal: string;
  followups: string[];
  support: number;
  context_stats: ContextStats;
  latency_s: number;
  model: string | null;
  uncited_sentences?: number;
  topic_id?: string | null;
  mastery_update?: { topic_id: string; before: number; after: number; signal: string } | null;
};

export type Subtopic = { id: string; name: string; description: string; key_concepts: string[]; units: number };
export type Topic = {
  id: string;
  name: string;
  description: string;
  key_concepts: string[];
  prerequisites: string[];
  subtopics: Subtopic[];
  coverage: Record<string, number>;
};

export type Student = { id: string; name: string; created_at: number; intake: { ratings: Record<string, number>; goals: string } | null };

export type Mastery = {
  topic_id: string;
  name: string;
  p: number;
  n: number;
  accuracy: number | null;
  retention: number;
  half_life_days: number;
  level: "mastered" | "developing" | "needs work";
  due: boolean;
};

export type Dashboard = {
  student: Student;
  mastery: Mastery[];
  log: { topic_id: string; ts: number; p_before: number; p_after: number; event: string }[];
  assessments: { id: string; kind: string; created_at: number; finished: boolean; accuracy: number | null; weak_topics: string[] | null }[];
  answered: number;
  score_sum: number;
  questions_asked: number;
  weak_topics: Mastery[];
  is_new: boolean;
};

export type Question = {
  id: string;
  type: "mcq" | "numerical" | "short";
  difficulty: number;
  stem: string;
  options: string[] | null;
  topic_id: string;
  topic: string;
  sources: string[];
};

export type Assessment = { id: string; kind: string; questions: Question[]; repeats: number };

export type Feedback = {
  score: number;
  correct: boolean;
  correct_answer: string;
  explanation: string;
  feedback: string;
  misconception: string;
  citations: Citation[];
  mastery: { topic_id: string; before: number; after: number } | Record<string, never>;
};

export type Report = {
  assessment_id: string;
  kind: string;
  score: number;
  n: number;
  accuracy: number | null;
  topics: { topic_id: string; name: string; n: number; accuracy: number | null; before: number | null; after: number | null }[];
  weak_topics: string[];
  misconceptions: { topic: string; question: string; misconception: string; citations: Citation[] }[];
  recommendations: { topic_id: string; topic: string; review: Citation[]; action: string }[];
  repeats: number;
};

export type Source = {
  id: string;
  kind: string;
  title: string;
  license: string;
  attribution: string;
  meta: Record<string, unknown>;
  unit_counts: Record<string, number>;
};

export type UnitView = {
  unit: { id: string; kind: string; text: string; label: string; section: string; image: string | null; loc: Loc };
  source: { id: string; kind: string; title: string; license: string; attribution: string };
  view: {
    type: string;
    page_image?: string | null;
    image?: string | null;
    page?: number;
    page_label?: number;
    slide?: number;
    pdf_url?: string | null;
    highlights?: number[][];
    page_size?: number[];
    start?: number;
    end?: number;
    video_url?: string | null;
    youtube_id?: string;
  };
};

export type Health = {
  llm: boolean;
  offline: boolean;
  models: Record<string, string>;
  embedder: string;
  context_budget: number;
  counts: { sources: number; units: number; topics: number; questions: number; students: number };
};

export type Job = { id: string; status: "queued" | "running" | "done" | "error"; progress: number; message: string };

export type Flashcard = { front: string; back: string; citation: Citation | null };
export type Plan = { exam_date: string; minutes_per_day: number; days: { date: string; tasks: { topic: string; activity: string; minutes: number; why?: string; sources?: string[] }[] }[] };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type EvalResults = Record<string, any>;

async function req<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const opts: RequestInit = { ...init };
  if (init?.json !== undefined) {
    opts.body = JSON.stringify(init.json);
    opts.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try {
      msg = (await r.json()).detail || msg;
    } catch {
      /* not json */
    }
    throw new Error(msg || `Request failed (${r.status})`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/api/health"),
  sources: () => req<Source[]>("/api/sources"),
  topics: (studentId?: string) => req<{ tree: Topic[]; mermaid: string }>(`/api/topics${studentId ? `?student_id=${studentId}` : ""}`),
  unit: (id: string, q = "") => req<UnitView>(`/api/units/${encodeURIComponent(id)}?q=${encodeURIComponent(q)}`),
  students: () => req<Student[]>("/api/students"),
  createStudent: (name: string) => req<Student>("/api/students", { method: "POST", json: { name } }),
  intake: (id: string, ratings: Record<string, number>, goals: string) =>
    req<{ mastery: Mastery[] }>(`/api/students/${id}/intake`, { method: "POST", json: { ratings, goals } }),
  dashboard: (id: string) => req<Dashboard>(`/api/students/${id}/dashboard`),
  schedule: (id: string, exam: string, minutes: number) => req<Plan>(`/api/students/${id}/schedule?exam_date=${exam}&minutes=${minutes}`),
  flashcards: (topicId: string) => req<Flashcard[]>(`/api/topics/${topicId}/flashcards`),
  chat: (body: { message: string; student_id?: string | null; lang: string; allow_outside: boolean; history: { role: string; content: string }[] }) =>
    req<ChatAnswer>("/api/chat", { method: "POST", json: body }),
  newAssessment: (body: { student_id: string; kind: string; topic_ids: string[]; n: number; types: string[] }) =>
    req<Assessment>("/api/assessments", { method: "POST", json: body }),
  answer: (aid: string, question_id: string, response: string) =>
    req<Feedback>(`/api/assessments/${aid}/answer`, { method: "POST", json: { question_id, response } }),
  finish: (aid: string) => req<Report>(`/api/assessments/${aid}/finish`, { method: "POST" }),
  upload: (form: FormData) => req<{ job_id: string }>("/api/sources", { method: "POST", body: form }),
  youtube: (url: string) => req<{ job_id: string }>("/api/sources/youtube", { method: "POST", json: { url } }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  evals: () => req<EvalResults>("/api/eval"),
};

export const pct = (x: number | null | undefined, digits = 0) => (x == null || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(digits)}%`);
export const fmtTs = (s = 0) => {
  const t = Math.floor(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const ss = String(t % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
};
