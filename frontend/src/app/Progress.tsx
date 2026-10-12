import { AnimatePresence, motion } from "motion/react";
import { BrainCircuit, CalendarDays, CheckCheck, Layers3, MessageSquareText, RotateCw, Sparkles, Target, UserPlus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Panel, StatTile } from "../kit";
import { EASE } from "../kit/lib/motion";
import { api, pct, type Dashboard, type Flashcard, type Plan } from "../lib/api";
import { Rich } from "../lib/rich";
import { CourseMap, LineChart } from "./charts";
import { useSource } from "./SourceViewer";
import { useApp } from "./StudyApp";
import { Empty, ErrorNote, LevelBadge, MasteryBar, Skeleton } from "./ui";

export function Progress() {
  const { student, topics, go, newStudent } = useApp();
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    if (!student) return;
    setErr("");
    try {
      setD(await api.dashboard(student.id));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [student]);
  useEffect(() => {
    setD(null);
    load();
  }, [load]);

  if (!student)
    return (
      <Panel>
        <Empty icon={<UserPlus />} title="No student yet" body="Create a student to start tracking per-topic mastery." action={<Button onClick={newStudent}>New student</Button>} />
      </Panel>
    );
  if (err) return <ErrorNote message={err} onRetry={load} />;
  if (!d)
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[118px] rounded-[18px]" />
        ))}
        <Skeleton className="h-80 sm:col-span-2" />
        <Skeleton className="h-80 sm:col-span-2" />
      </div>
    );

  const mastered = d.mastery.filter((m) => m.level === "mastered").length;
  const acc = d.answered ? d.score_sum / d.answered : null;
  const masteryMap = Object.fromEntries(d.mastery.map((m) => [m.topic_id, m.p]));

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={<CheckCheck />} label="Questions answered" value={d.answered} hint="graded attempts" />
        <StatTile icon={<Target />} label="Accuracy" value={pct(acc)} hint="partial credit counts half" />
        <StatTile icon={<MessageSquareText />} label="Tutor questions" value={d.questions_asked} hint="also update mastery (soft evidence)" />
        <StatTile icon={<BrainCircuit />} label="Topics mastered" value={`${mastered}/${d.mastery.length}`} hint="P(known) at least 80%" />
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        <Panel className="xl:col-span-5" title="Topic mastery" description="Bayesian Knowledge Tracing, updated after every answer and tutor conversation." action={<Button size="sm" variant="ghost" onClick={load} icon={<RotateCw size={14} />}>Refresh</Button>}>
          {d.is_new && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl bg-accent-soft/60 p-4 text-[14px]">
              <span className="text-ink">New learner: a diagnostic calibrates these estimates.</span>
              <Button size="sm" onClick={() => go("practice", { practiceMode: "diagnostic" })}>Start</Button>
            </div>
          )}
          <ul className="divide-y divide-[var(--hair)]">
            {d.mastery.map((m) => (
              <li key={m.topic_id} className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[14px] font-medium text-ink">{m.name}</p>
                    <p className="text-[12.5px] text-muted">
                      {m.n} answers{m.accuracy != null ? ` · ${pct(m.accuracy)} correct` : ""} · retention {pct(m.retention)}
                      {m.due && <span className="font-semibold text-accent"> · review due</span>}
                    </p>
                  </div>
                  <LevelBadge level={m.level} p={m.p} />
                </div>
                <MasteryBar p={m.p} className="mt-2.5" />
              </li>
            ))}
          </ul>
        </Panel>
        <Panel className="xl:col-span-7" title="Course flow map" description="Topics in prerequisite order. Click a topic to practise it.">
          <CourseMap topics={topics} mastery={masteryMap} onSelect={(id) => go("practice", { practiceTopics: [id], practiceMode: "quiz" })} />
          <Timeline d={d} />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        <StudyPlan studentId={student.id} />
        <Flashcards weakest={[...d.mastery].sort((a, b) => a.p - b.p).map((m) => ({ id: m.topic_id, name: m.name, p: m.p }))} />
      </div>
    </div>
  );
}

function Timeline({ d }: { d: Dashboard }) {
  const { topicName } = useApp();
  const series = useMemo(() => {
    if (!d.log.length) return [];
    const ids = d.mastery.map((m) => m.topic_id);
    const cur: Record<string, number> = {};
    d.log.forEach((e) => (cur[e.topic_id] ??= e.p_before));
    ids.forEach((id) => (cur[id] ??= d.mastery.find((m) => m.topic_id === id)!.p));
    const snaps: Record<string, number>[] = [{ ...cur }];
    d.log.forEach((e) => {
      cur[e.topic_id] = e.p_after;
      snaps.push({ ...cur });
    });
    const touched = [...new Set(d.log.map((e) => e.topic_id))].slice(0, 5);
    return [
      { name: "Average", values: snaps.map((s) => ids.reduce((a, id) => a + s[id], 0) / ids.length), color: "var(--ink)" },
      ...touched.map((id) => ({ name: topicName(id), values: snaps.map((s) => s[id]) })),
    ];
  }, [d, topicName]);
  return (
    <div className="mt-6 border-t border-hair pt-5">
      <p className="mb-3 font-display text-[15px] font-semibold text-ink">Mastery over time</p>
      {series.length ? (
        <LineChart series={series} xLabel="evidence (answers and tutor turns)" guide={{ y: 0.8, label: "mastered" }} />
      ) : (
        <p className="text-[14px] text-muted">No evidence yet. Answer questions or talk to the tutor and this chart fills in.</p>
      )}
    </div>
  );
}

function StudyPlan({ studentId }: { studentId: string }) {
  const [exam, setExam] = useState(() => new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10));
  const [mins, setMins] = useState(45);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Panel className="xl:col-span-6" title="Study plan to exam day" description="Weakest topics first in prerequisite order, then spaced reviews when predicted retention drops below 80%.">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[13px] text-muted">
          Exam date
          <input type="date" value={exam} onChange={(e) => setExam(e.target.value)} className="mt-1 block h-10 rounded-full border border-hair bg-surface px-4 text-[14px] text-ink" />
        </label>
        <label className="text-[13px] text-muted">
          Minutes per day
          <input type="number" min={15} max={240} value={mins} onChange={(e) => setMins(Number(e.target.value))} className="mt-1 block h-10 w-28 rounded-full border border-hair bg-surface px-4 text-[14px] text-ink" />
        </label>
        <Button
          icon={<CalendarDays size={15} />}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setPlan(await api.schedule(studentId, exam, mins));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Planning…" : "Make my plan"}
        </Button>
      </div>
      {plan && (
        <ol className="mt-5 max-h-[420px] space-y-2.5 overflow-y-auto pr-1">
          {plan.days.map((day) => (
            <li key={day.date} className="rounded-2xl bg-paper-2 p-4">
              <p className="t-eyebrow mb-2 !text-[11px]">{new Date(day.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</p>
              <ul className="space-y-1.5">
                {day.tasks.map((t, i) => (
                  <li key={i} className="text-[14px] text-ink-2">
                    <b className="text-ink">{t.topic}</b> · {t.activity} · {t.minutes} min
                    {t.why && <span className="text-muted"> ({t.why})</span>}
                    {t.sources && <span className="block text-[12.5px] text-muted">Read: {t.sources.join(", ")}</span>}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function Flashcards({ weakest }: { weakest: { id: string; name: string; p: number }[] }) {
  const { open } = useSource();
  const [topic, setTopic] = useState(weakest[0]?.id ?? "");
  const [cards, setCards] = useState<Flashcard[] | null>(null);
  const [flip, setFlip] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  return (
    <Panel className="xl:col-span-6" title="Flashcards for weak topics" description="Generated from your sources; each card links to the page, slide or timestamp it came from.">
      <div className="flex flex-wrap items-center gap-2">
        {weakest.slice(0, 4).map((w) => (
          <button key={w.id} onClick={() => setTopic(w.id)} className={`rounded-full border px-3 py-1.5 text-[13px] transition ${topic === w.id ? "border-transparent bg-ink text-paper" : "border-hair text-ink-2 hover:text-ink"}`}>
            {w.name} <span className="opacity-60">{pct(w.p)}</span>
          </button>
        ))}
        <Button
          size="sm"
          icon={<Sparkles size={14} />}
          disabled={busy || !topic}
          onClick={async () => {
            setBusy(true);
            setFlip(new Set());
            try {
              setCards(await api.flashcards(topic));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Writing…" : "Make cards"}
        </Button>
      </div>
      {busy && <Skeleton className="mt-4 h-40" />}
      {cards && !busy && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <AnimatePresence>
            {cards.map((c, i) => (
              <motion.button
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: EASE, delay: i * 0.04 }}
                onClick={() => setFlip((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; })}
                className="flex min-h-[132px] flex-col justify-between rounded-2xl border border-hair bg-paper-2 p-4 text-left transition hover:-translate-y-0.5"
              >
                <div>
                  <Badge tone={flip.has(i) ? "accent" : "neutral"}>{flip.has(i) ? "Answer" : "Question"}</Badge>
                  <Rich text={flip.has(i) ? c.back : c.front} className="mt-2 !text-[14px]" />
                </div>
                {c.citation && (
                  <span
                    role="link"
                    tabIndex={0}
                    onClick={(e) => {
                      e.stopPropagation();
                      open(c.citation!.unit_id);
                    }}
                    className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] font-medium text-accent hover:underline"
                  >
                    <Layers3 size={13} /> {c.citation.label}
                  </span>
                )}
              </motion.button>
            ))}
          </AnimatePresence>
        </div>
      )}
    </Panel>
  );
}
