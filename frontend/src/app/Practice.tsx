import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CheckCircle2, CircleAlert, Lightbulb, ListChecks, Minus, Plus, RotateCcw, Target, TriangleAlert, UserPlus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Panel, Segmented, StatTile } from "../kit";
import { cn } from "../kit/lib/cn";
import { EASE } from "../kit/lib/motion";
import { api, pct, type Assessment, type Feedback, type Report } from "../lib/api";
import { Rich } from "../lib/rich";
import { useSource } from "./SourceViewer";
import { useApp } from "./StudyApp";
import { ChipToggle, Empty, ErrorNote, Skeleton, SourceList } from "./ui";

type Mode = "quiz" | "mock" | "diagnostic";
const HINT: Record<Mode, string> = {
  quiz: "Focuses on your three weakest topics (respecting prerequisites) and picks difficulty so you succeed about 70% of the time.",
  mock: "A fixed exam blueprint across the chosen topics: every question type and all three difficulty levels.",
  diagnostic: "One medium question per topic, to calibrate the learner model for a new student.",
};
const consumed = { n: 0 }; // an intent from another screen starts one assessment, not one per remount
const TYPES = [
  { v: "mcq", l: "Multiple choice" },
  { v: "numerical", l: "Numerical" },
  { v: "short", l: "Short answer" },
];

export function Practice() {
  const { student, topics, intent, newStudent } = useApp();
  const [mode, setMode] = useState<Mode>("quiz");
  const [scope, setScope] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<Set<string>>(new Set(TYPES.map((t) => t.v)));
  const [n, setN] = useState(6);
  const [quiz, setQuiz] = useState<Assessment | null>(null);
  const [idx, setIdx] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (topics.length && scope.size === 0) setScope(new Set(topics.map((t) => t.id)));
  }, [topics, scope.size]);
  useEffect(() => {
    if ((intent.practiceMode || intent.practiceTopics) && intent.nonce > consumed.n) {
      consumed.n = intent.nonce;
      const m = (intent.practiceMode as Mode) || "quiz";
      setMode(m);
      if (intent.practiceTopics) setScope(new Set(intent.practiceTopics));
      start(m, intent.practiceTopics);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intent.nonce]);

  async function start(m: Mode = mode, topicIds?: string[]) {
    if (!student) return;
    setLoading(true);
    setErr("");
    setReport(null);
    setQuiz(null);
    try {
      const a = await api.newAssessment({ student_id: student.id, kind: m, topic_ids: topicIds ?? [...scope], n, types: [...types] });
      setQuiz(a);
      setIdx(0);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (!student) {
    return (
      <Panel>
        <Empty icon={<UserPlus />} title="Create a student first" body="StudyTwin keeps a separate learner model for every student. A new student starts with a short intake and a diagnostic quiz." action={<Button onClick={newStudent}>New student</Button>} />
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Panel title="Build an assessment" description={HINT[mode]}>
          <Segmented id="mode" value={mode} onChange={setMode} options={[{ value: "quiz", label: "Adaptive" }, { value: "mock", label: "Mock exam" }, { value: "diagnostic", label: "Diagnostic" }]} />
          {mode !== "diagnostic" && (
            <>
              <p className="t-eyebrow mb-2.5 mt-6 !text-[11px]">Scope</p>
              <div className="flex flex-wrap gap-2">
                {topics.map((t) => (
                  <ChipToggle key={t.id} on={scope.has(t.id)} onClick={() => setScope((s) => toggle(s, t.id))}>
                    {t.name}
                  </ChipToggle>
                ))}
              </div>
              <p className="t-eyebrow mb-2.5 mt-6 !text-[11px]">Question types</p>
              <div className="flex flex-wrap gap-2">
                {TYPES.map((t) => (
                  <ChipToggle key={t.v} on={types.has(t.v)} onClick={() => setTypes((s) => (s.size === 1 && s.has(t.v) ? s : toggle(s, t.v)))}>
                    {t.l}
                  </ChipToggle>
                ))}
              </div>
              <div className="mt-6 flex items-center justify-between rounded-2xl bg-paper-2 px-4 py-3">
                <span className="text-[14px] text-ink-2">Questions</span>
                <div className="flex items-center gap-3">
                  <Step onClick={() => setN((v) => Math.max(1, v - 1))} label="Fewer">
                    <Minus size={15} />
                  </Step>
                  <span className="t-num w-6 text-center text-[18px]">{n}</span>
                  <Step onClick={() => setN((v) => Math.min(20, v + 1))} label="More">
                    <Plus size={15} />
                  </Step>
                </div>
              </div>
            </>
          )}
          <Button className="mt-6 w-full" size="lg" onClick={() => start()} disabled={loading || scope.size === 0} icon={<ArrowRight size={17} />}>
            {loading ? "Selecting questions…" : mode === "diagnostic" ? "Start the diagnostic" : "Start"}
          </Button>
          <p className="mt-3 text-[12.5px] text-muted">Questions you have already answered are never repeated while unseen ones remain; when a scope runs out, new ones are generated and verified on demand.</p>
        </Panel>

        <div className="min-w-0">
          {err && <ErrorNote message={err} onRetry={() => start()} />}
          {loading && (
            <div className="surface space-y-4 p-6">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-6 w-4/5" />
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          )}
          {!loading && !quiz && !err && (
            <Panel>
              <Empty icon={<ListChecks />} title="Ready when you are" body="Each question is tagged with its topic, difficulty and source, and was solved independently by a second model before it entered the bank." />
            </Panel>
          )}
          {quiz && !report && quiz.questions.length === 0 && (
            <Panel>
              <Empty icon={<CircleAlert />} title="No questions for this scope yet" body="Add material to the library or widen the scope." />
            </Panel>
          )}
          {quiz && !report && quiz.questions[idx] && (
            <QuestionCard
              key={quiz.questions[idx].id}
              quiz={quiz}
              idx={idx}
              onNext={async () => {
                if (idx + 1 < quiz.questions.length) setIdx(idx + 1);
                else setReport(await api.finish(quiz.id));
              }}
            />
          )}
          {report && <ReportView r={report} onPractice={(t) => { setMode("quiz"); setScope(new Set([t])); start("quiz", [t]); }} onAgain={() => start()} />}
        </div>
      </div>
    </div>
  );
}

function toggle(s: Set<string>, v: string) {
  const n = new Set(s);
  if (n.has(v)) n.delete(v);
  else n.add(v);
  return n;
}

function Step({ children, onClick, label }: { children: ReactNode; onClick: () => void; label: string }) {
  return (
    <button aria-label={label} onClick={onClick} className="grid size-8 place-items-center rounded-full border border-hair bg-surface text-ink-2 transition hover:text-ink">
      {children}
    </button>
  );
}

function QuestionCard({ quiz, idx, onNext }: { quiz: Assessment; idx: number; onNext: () => void }) {
  const { open } = useSource();
  const { topicName } = useApp();
  const q = quiz.questions[idx];
  const [resp, setResp] = useState("");
  const [fb, setFb] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const last = idx + 1 === quiz.questions.length;

  async function submit() {
    if (!resp.trim()) return;
    setBusy(true);
    setErr("");
    try {
      setFb(await api.answer(quiz.id, q.id, resp));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const tone = fb ? (fb.score >= 0.75 ? "good" : fb.score > 0 ? "half" : "bad") : null;
  const m = fb && "topic_id" in fb.mastery ? fb.mastery : null;

  return (
    <motion.div initial={{ opacity: 0, y: 14, filter: "blur(8px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.5, ease: EASE }} className="surface p-5 md:p-7">
      <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-paper-3">
        <motion.div className="h-full rounded-full bg-accent" initial={false} animate={{ width: `${((idx + (fb ? 1 : 0)) / quiz.questions.length) * 100}%` }} transition={{ duration: 0.6, ease: EASE }} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge>
          {quiz.kind === "quiz" ? "Adaptive" : quiz.kind === "mock" ? "Mock exam" : "Diagnostic"} · {idx + 1}/{quiz.questions.length}
        </Badge>
        <Badge tone="accent">{q.topic}</Badge>
        <Badge>{q.type === "mcq" ? "Multiple choice" : q.type === "numerical" ? "Numerical" : "Short answer"}</Badge>
        <Badge>
          Difficulty{" "}
          <span aria-label={`${q.difficulty} of 3`} className="tracking-[2px]">
            {"●".repeat(q.difficulty)}
            <span className="opacity-30">{"●".repeat(3 - q.difficulty)}</span>
          </span>
        </Badge>
      </div>
      <Rich text={q.stem} className="mt-5 !text-[17px] !leading-relaxed" />
      <p className="mt-2 text-[12.5px] text-muted">Source: {q.sources.join(", ")}</p>

      <div className="mt-5">
        {q.type === "mcq" && q.options ? (
          <div className="grid gap-2.5">
            {q.options.map((o, i) => {
              const L = "ABCD"[i];
              const right = fb && fb.correct_answer.startsWith(L + ")");
              const wrong = fb && resp === L && !right;
              return (
                <button
                  key={L}
                  disabled={!!fb}
                  onClick={() => setResp(L)}
                  className={cn(
                    "flex items-start gap-3 rounded-2xl border px-4 py-3 text-left text-[15px] transition",
                    right ? "border-[color-mix(in_oklab,var(--pos)_45%,transparent)] bg-[color-mix(in_oklab,var(--pos)_8%,transparent)]" : wrong ? "border-[color-mix(in_oklab,var(--neg)_45%,transparent)] bg-[color-mix(in_oklab,var(--neg)_7%,transparent)]" : resp === L ? "border-ink bg-paper-2" : "border-hair hover:border-[var(--hair-strong)] hover:bg-paper-2",
                  )}
                >
                  <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-[12px] font-semibold", resp === L || right ? "bg-ink text-paper" : "bg-paper-3 text-ink-2")}>{L}</span>
                  <Rich text={o} className="!text-[15px]" />
                </button>
              );
            })}
          </div>
        ) : q.type === "numerical" ? (
          <input
            value={resp}
            disabled={!!fb}
            onChange={(e) => setResp(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Your answer: a decimal, a fraction like 3/11, or a percentage"
            className="h-12 w-full rounded-2xl border border-hair bg-paper-2 px-4 text-[15px] outline-none focus:border-[var(--hair-strong)]"
          />
        ) : (
          <textarea value={resp} disabled={!!fb} onChange={(e) => setResp(e.target.value)} rows={3} placeholder="Answer in one to three sentences" className="w-full rounded-2xl border border-hair bg-paper-2 px-4 py-3 text-[15px] outline-none focus:border-[var(--hair-strong)]" />
        )}
      </div>
      {err && <div className="mt-4"><ErrorNote message={err} onRetry={submit} /></div>}
      {!fb && (
        <Button className="mt-5" onClick={submit} disabled={busy || !resp.trim()}>
          {busy ? "Checking…" : "Check answer"}
        </Button>
      )}

      <AnimatePresence>
        {fb && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }} className="mt-6 rounded-[20px] border border-hair bg-paper-2 p-5">
            <div className="flex flex-wrap items-center gap-2">
              {tone === "good" ? (
                <Badge tone="pos"><CheckCircle2 size={13} strokeWidth={2} /> Correct</Badge>
              ) : tone === "half" ? (
                <Badge tone="accent">Partly correct</Badge>
              ) : (
                <Badge tone="neg"><TriangleAlert size={13} strokeWidth={2} /> Not quite</Badge>
              )}
              {q.type !== "mcq" && <span className="text-[14px] text-ink-2">Answer: <b className="text-ink">{fb.correct_answer}</b></span>}
              {m && (
                <span className="ml-auto text-[13px] text-muted">
                  {topicName(m.topic_id)}: {pct(m.before)} → <b className="text-ink">{pct(m.after)}</b>
                </span>
              )}
            </div>
            {fb.misconception && (
              <p className="mt-3 flex gap-2 text-[14px] text-ink">
                <Lightbulb size={16} strokeWidth={1.7} className="mt-0.5 shrink-0 text-accent" />
                <span><b>Likely misconception:</b> {fb.misconception}</span>
              </p>
            )}
            {fb.feedback && <Rich text={fb.feedback} cites={fb.citations} onCite={open} className="mt-3" />}
            <Rich text={fb.explanation} cites={fb.citations} onCite={open} className="mt-3" />
            <SourceList cites={fb.citations} onOpen={(c) => open(c.unit_id)} compact />
            <Button className="mt-4" onClick={onNext} icon={<ArrowRight size={16} />}>
              {last ? "Finish and see the report" : "Next question"}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function ReportView({ r, onPractice, onAgain }: { r: Report; onPractice: (topicId: string) => void; onAgain: () => void }) {
  const { open } = useSource();
  const { go } = useApp();
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={<Target />} label="Score" value={pct(r.accuracy)} delta={`${r.score}/${r.n}`} />
        <StatTile icon={<TriangleAlert />} label="Weak topics" value={r.weak_topics.length} />
        <StatTile icon={<Lightbulb />} label="Misconceptions" value={r.misconceptions.length} />
        <StatTile icon={<RotateCcw />} label="Repeated questions" value={r.repeats} tone={r.repeats ? "neg" : "pos"} delta={r.repeats ? "bank exhausted" : "none"} />
      </div>
      <Panel title="Post-assessment report" description="Mastery is the Bayesian Knowledge Tracing estimate before and after this assessment." action={<Button size="sm" variant="ghost" onClick={onAgain} icon={<RotateCcw size={14} />}>New assessment</Button>}>
        <ul className="divide-y divide-[var(--hair)]">
          {r.topics.map((t) => (
            <li key={t.topic_id} className="grid grid-cols-[1fr_auto] items-center gap-3 py-3 text-[14px] sm:grid-cols-[1fr_90px_160px]">
              <span className="font-medium text-ink">{t.name}</span>
              <span className="text-muted">{t.n} q · {pct(t.accuracy)}</span>
              <span className="col-span-2 text-ink-2 sm:col-span-1">
                {pct(t.before)} → <b className={cn((t.after ?? 0) >= (t.before ?? 0) ? "text-pos" : "text-neg")}>{pct(t.after)}</b>
              </span>
            </li>
          ))}
        </ul>
      </Panel>
      {r.misconceptions.length > 0 && (
        <Panel title="Likely misconceptions" description="From the distractor you chose or the grader's reading of your answer.">
          <ul className="space-y-3">
            {r.misconceptions.map((m, i) => (
              <li key={i} className="rounded-2xl bg-paper-2 p-4">
                <p className="text-[14px] text-ink"><b>{m.topic}:</b> {m.misconception}</p>
                <p className="mt-1 text-[13px] text-muted">{m.question}</p>
                <SourceList cites={m.citations} onOpen={(c) => open(c.unit_id)} compact />
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel title="What to review next">
        {r.recommendations.length === 0 ? (
          <p className="text-[14px] text-muted">No weak topics in this assessment. Try a mock exam or a harder adaptive quiz.</p>
        ) : (
          <ul className="space-y-4">
            {r.recommendations.map((x) => (
              <li key={x.topic_id} className="rounded-2xl border border-hair p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-display text-[15px] font-semibold text-ink">{x.topic}</p>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => go("tutor", { ask: `Explain ${x.topic} with an example from my course.` })}>Ask the tutor</Button>
                    <Button size="sm" onClick={() => onPractice(x.topic_id)}>Practice this topic</Button>
                  </div>
                </div>
                <SourceList cites={x.review} onOpen={(c) => open(c.unit_id)} compact />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </motion.div>
  );
}
