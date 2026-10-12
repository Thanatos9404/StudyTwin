import { motion } from "motion/react";
import { ChartNoAxesColumn, FlaskConical, Gauge, Library as LibraryIcon, ListChecks, MessageSquareText, Plus, RefreshCw } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, Button, IconButton, Wordmark } from "../kit";
import { cn } from "../kit/lib/cn";
import { SPRING_SNAPPY } from "../kit/lib/motion";
import { api, type Health, type Student, type Topic } from "../lib/api";
import { Evaluation } from "./Evaluation";
import { Library } from "./Library";
import { Onboarding } from "./Onboarding";
import { Practice } from "./Practice";
import { Progress } from "./Progress";
import { SourceProvider } from "./SourceViewer";
import { Tutor } from "./Tutor";

export type TabId = "tutor" | "practice" | "progress" | "library" | "eval";

type AppState = {
  health: Health | null;
  topics: Topic[];
  topicName: (id: string) => string;
  student: Student | null;
  students: Student[];
  refreshTopics: () => Promise<void>;
  go: (tab: TabId, opts?: { practiceTopics?: string[]; practiceMode?: string; ask?: string }) => void;
  intent: { practiceTopics?: string[]; practiceMode?: string; ask?: string; nonce: number };
  newStudent: () => void;
};
const Ctx = createContext<AppState>(null as unknown as AppState);
export const useApp = () => useContext(Ctx);

const NAV: { id: TabId; label: string; icon: ReactNode; sub: string }[] = [
  { id: "tutor", label: "Tutor", icon: <MessageSquareText />, sub: "Ask anything about your course. Every claim opens its source." },
  { id: "practice", label: "Practice", icon: <ListChecks />, sub: "Adaptive quizzes, mock exams and the cold-start diagnostic." },
  { id: "progress", label: "Progress", icon: <Gauge />, sub: "Mastery per topic, what to review next, and a plan to exam day." },
  { id: "library", label: "Library", icon: <LibraryIcon />, sub: "Your lecture videos, slides and textbook, organised into topics." },
  { id: "eval", label: "Evaluation", icon: <FlaskConical />, sub: "How well grounding, assessment and personalization actually work." },
];

function tabFromHash(): TabId {
  const t = location.hash.replace(/^#app\/?/, "") as TabId;
  return NAV.some((n) => n.id === t) ? t : "tutor";
}

export function StudyApp() {
  const [tab, setTab] = useState<TabId>(tabFromHash());
  const [health, setHealth] = useState<Health | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [studentId, setStudentId] = useState<string | null>(() => {
    try {
      return localStorage.getItem("st_student");
    } catch {
      return null;
    }
  });
  const [intent, setIntent] = useState<AppState["intent"]>({ nonce: 0 });
  const [onboarding, setOnboarding] = useState(false);

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const refreshTopics = useCallback(async () => setTopics((await api.topics()).tree), []);
  const loadStudents = useCallback(async (select?: string) => {
    const list = await api.students();
    setStudents(list);
    setStudentId((cur) => {
      const want = select ?? cur;
      const pick = list.find((s) => s.id === want) ?? list[list.length - 1] ?? null;
      try {
        if (pick) localStorage.setItem("st_student", pick.id);
      } catch {
        /* storage blocked */
      }
      return pick ? pick.id : null;
    });
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    refreshTopics().catch(() => undefined);
    loadStudents().catch(() => undefined);
  }, [refreshTopics, loadStudents]);

  const student = students.find((s) => s.id === studentId) ?? null;
  const topicName = useCallback((id: string) => topics.find((t) => t.id === id)?.name ?? id, [topics]);
  const go: AppState["go"] = useCallback((t, opts) => {
    if (opts) setIntent((i) => ({ ...opts, nonce: i.nonce + 1 }));
    location.hash = `#app/${t}`;
    setTab(t);
  }, []);
  const value = useMemo<AppState>(
    () => ({ health, topics, topicName, student, students, refreshTopics, go, intent, newStudent: () => setOnboarding(true) }),
    [health, topics, topicName, student, students, refreshTopics, go, intent],
  );
  const current = NAV.find((n) => n.id === tab)!;

  return (
    <Ctx.Provider value={value}>
      <SourceProvider>
        <AppShell
          brand={
            <a href="#top" className="inline-block" aria-label="StudyTwin home">
              <Wordmark name="STUDYTWIN" />
            </a>
          }
          nav={[
            { section: "Study", items: NAV.slice(0, 3).map(({ id, label, icon }) => ({ id, label, icon })) },
            { section: "Course", items: NAV.slice(3).map(({ id, label, icon }) => ({ id, label, icon, badge: id === "library" && health ? String(health.counts.sources) : undefined })) },
          ]}
          active={tab}
          onNavigate={(id) => go(id as TabId)}
          greeting={student ? `Hello, ${student.name}` : "Welcome to StudyTwin"}
          subtitle={current.sub}
          actions={
            <>
              <StudentPicker students={students} value={studentId} onChange={(id) => loadStudents(id)} />
              <IconButton label="Refresh" onClick={() => { refreshTopics(); loadStudents(); api.health().then(setHealth); }}>
                <RefreshCw />
              </IconButton>
              <Button size="sm" onClick={() => setOnboarding(true)} icon={<Plus size={15} strokeWidth={1.8} />}>
                <span className="hidden sm:inline">New student</span>
                <span className="sm:hidden">New</span>
              </Button>
            </>
          }
          footer={<ModelStatus health={health} />}
        >
          <div className="pb-20 md:pb-0">
            {tab === "tutor" && <Tutor />}
            {tab === "practice" && <Practice />}
            {tab === "progress" && <Progress />}
            {tab === "library" && <Library />}
            {tab === "eval" && <Evaluation />}
          </div>
        </AppShell>
        <MobileTabs active={tab} onChange={(t) => go(t)} />
        <Onboarding
          open={onboarding}
          onClose={() => setOnboarding(false)}
          onCreated={async (s) => {
            await loadStudents(s.id);
          }}
          onDiagnostic={() => {
            setOnboarding(false);
            go("practice", { practiceMode: "diagnostic" });
          }}
        />
      </SourceProvider>
    </Ctx.Provider>
  );
}

function StudentPicker({ students, value, onChange }: { students: Student[]; value: string | null; onChange: (id: string) => void }) {
  if (!students.length) return null;
  return (
    <label className="relative hidden h-10 items-center rounded-full border border-hair bg-surface pl-4 pr-2 text-[14px] shadow-[var(--shadow-soft)] sm:flex">
      <span className="sr-only">Active student</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="h-full max-w-[180px] cursor-pointer appearance-none bg-transparent pr-6 font-display font-medium text-ink outline-none"
      >
        {students.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      <ChartNoAxesColumn size={14} strokeWidth={1.7} className="pointer-events-none absolute right-3 text-muted" />
    </label>
  );
}

function ModelStatus({ health }: { health: Health | null }) {
  return (
    <div className="px-3 text-[12px] leading-relaxed text-muted">
      <div className="flex items-center gap-2 font-display text-[13px] font-semibold text-ink">
        <span className={cn("size-2 rounded-full", health?.llm ? "bg-pos" : "bg-muted")} />
        {health ? (health.llm ? "Live · Nebius Token Factory" : "Offline mode") : "Connecting…"}
      </div>
      {health && (
        <p className="mt-1">
          {health.counts.units} knowledge units · {health.counts.questions} verified questions
        </p>
      )}
      <a href="#top" className="mt-2 inline-block text-ink-2 underline-offset-4 hover:underline">
        Back to the site
      </a>
    </div>
  );
}

function MobileTabs({ active, onChange }: { active: TabId; onChange: (t: TabId) => void }) {
  return (
    <nav className="glass fixed inset-x-3 bottom-3 z-30 flex justify-between rounded-full p-1.5 shadow-[var(--shadow-lift)] md:hidden">
      {NAV.map((n) => (
        <button key={n.id} onClick={() => onChange(n.id)} className="relative flex flex-1 flex-col items-center gap-0.5 rounded-full py-1.5 text-[11px] font-medium" aria-label={n.label}>
          {active === n.id && <motion.span layoutId="mob-pill" transition={SPRING_SNAPPY} className="absolute inset-0 rounded-full bg-paper-3" />}
          <span className={cn("relative [&>svg]:size-[18px] [&>svg]:stroke-[1.6]", active === n.id ? "text-ink" : "text-ink-2")}>{n.icon}</span>
          <span className={cn("relative", active === n.id ? "text-ink" : "text-muted")}>{n.label}</span>
        </button>
      ))}
    </nav>
  );
}
