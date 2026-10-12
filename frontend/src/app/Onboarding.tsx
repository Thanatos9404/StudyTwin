import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, X } from "lucide-react";
import { useState } from "react";
import { Button, Segmented } from "../kit";
import { EASE } from "../kit/lib/motion";
import { api, type Student } from "../lib/api";
import { useApp } from "./StudyApp";

const LEVELS = ["Never seen it", "Heard of it", "Somewhat", "Comfortable", "Confident"];

/** Cold start: name -> intake self-rating per topic (sets BKT priors) -> diagnostic quiz. */
export function Onboarding({ open, onClose, onCreated, onDiagnostic }: { open: boolean; onClose: () => void; onCreated: (s: Student) => Promise<void>; onDiagnostic: () => void }) {
  const { topics } = useApp();
  const [step, setStep] = useState<"name" | "intake">("name");
  const [name, setName] = useState("");
  const [student, setStudent] = useState<Student | null>(null);
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);

  const close = () => {
    onClose();
    setTimeout(() => {
      setStep("name");
      setName("");
      setStudent(null);
      setRatings({});
      setGoal("");
    }, 300);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-[color-mix(in_oklab,var(--ink)_24%,transparent)] p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, y: 16, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: 10, filter: "blur(6px)" }}
            transition={{ duration: 0.45, ease: EASE }}
            className="surface max-h-[90dvh] w-full max-w-[640px] overflow-y-auto p-6 md:p-8"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="t-eyebrow">{step === "name" ? "New student · step 1 of 2" : "Intake · step 2 of 2"}</p>
                <h2 className="t-h3 mt-2">{step === "name" ? "Who is studying?" : `How familiar are you with each topic, ${student?.name}?`}</h2>
              </div>
              <button aria-label="Close" onClick={close} className="grid size-9 place-items-center rounded-full border border-hair text-ink-2 hover:text-ink">
                <X size={17} strokeWidth={1.7} />
              </button>
            </div>
            {step === "name" ? (
              <form
                className="mt-6"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  try {
                    const s = await api.createStudent(name.trim() || "Student");
                    await onCreated(s);
                    setStudent(s);
                    setStep("intake");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <p className="t-body">StudyTwin keeps a separate learner model per student. New students start with a short self-rating, then a diagnostic quiz with one question per topic.</p>
                <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" className="mt-5 h-12 w-full rounded-full border border-hair bg-paper-2 px-5 text-[15px] outline-none focus:border-[var(--hair-strong)]" />
                <Button className="mt-5" disabled={busy} icon={<ArrowRight size={16} />}>
                  Continue
                </Button>
              </form>
            ) : (
              <div className="mt-6">
                <ul className="divide-y divide-[var(--hair)]">
                  {topics.map((t) => (
                    <li key={t.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <span className="text-[14px] font-medium text-ink">{t.name}</span>
                      <Segmented
                        id={`r-${t.id}`}
                        value={ratings[t.id] ?? "1"}
                        onChange={(v) => setRatings((r) => ({ ...r, [t.id]: v }))}
                        options={["1", "2", "3", "4", "5"].map((v) => ({ value: v, label: <span title={LEVELS[Number(v) - 1]}>{v}</span> }))}
                      />
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[12.5px] text-muted">1 = {LEVELS[0]}, 5 = {LEVELS[4]}. Ratings only set starting estimates; answers override them.</p>
                <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Your goal, e.g. midterm on conditional probability next week" className="mt-5 h-12 w-full rounded-full border border-hair bg-paper-2 px-5 text-[15px] outline-none focus:border-[var(--hair-strong)]" />
                <div className="mt-6 flex flex-wrap gap-3">
                  <Button
                    disabled={busy}
                    icon={<ArrowRight size={16} />}
                    onClick={async () => {
                      if (!student) return;
                      setBusy(true);
                      try {
                        const r = Object.fromEntries(topics.map((t) => [t.id, Number(ratings[t.id] ?? "1")]));
                        await api.intake(student.id, r, goal);
                        onDiagnostic();
                        close();
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Save and take the diagnostic
                  </Button>
                  <Button variant="ghost" onClick={close}>
                    Skip for now
                  </Button>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
