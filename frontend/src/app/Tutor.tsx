import { motion } from "motion/react";
import { ArrowUp, BookOpenCheck, Clapperboard, Languages, Layers, Search } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Panel, Segmented } from "../kit";
import { EASE } from "../kit/lib/motion";
import { api, type ChatAnswer } from "../lib/api";
import { AnswerCard } from "./AnswerCard";
import { useSource } from "./SourceViewer";
import { useApp } from "./StudyApp";
import { ErrorNote, Skeleton } from "./ui";

type Msg = { role: "user"; text: string } | { role: "bot"; a: ChatAnswer } | { role: "error"; text: string; retry: string };

const threads = new Map<string, Msg[]>(); // keeps each student's conversation across tab switches
const consumed = { ask: 0 };

const SUGGEST = [
  "In the radar example, what is P(airplane present | radar registers)?",
  "So independent events are the same as mutually exclusive events, right?",
  "Why does zero probability not mean impossible?",
  "State the total probability theorem and when to use it.",
  "How many BB outcomes are in the tree diagram for drawing two balls with replacement?",
  "Explain the central limit theorem.",
];

export function Tutor() {
  const { student, topicName, intent } = useApp();
  const { open } = useSource();
  const key = student?.id ?? "guest";
  const [msgs, setMsgs] = useState<Msg[]>(() => threads.get(key) ?? []);
  const [text, setText] = useState("");
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [outside, setOutside] = useState(false);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMsgs(threads.get(key) ?? []), [key]);
  useEffect(() => {
    threads.set(key, msgs);
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, key]);
  useEffect(() => {
    if (intent.ask && intent.nonce > consumed.ask) {
      consumed.ask = intent.nonce; // run a handed-over question once, not on every remount
      send(intent.ask);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intent.nonce]);

  async function send(q?: string) {
    const message = (q ?? text).trim();
    if (!message || busy) return;
    setText("");
    setBusy(true);
    const history = msgs.flatMap((m) => (m.role === "user" ? [{ role: "user", content: m.text }] : m.role === "bot" ? [{ role: "assistant", content: m.a.answer }] : []));
    setMsgs((m) => [...m, { role: "user", text: message }]);
    try {
      const a = await api.chat({ message, student_id: student?.id, lang, allow_outside: outside, history });
      setMsgs((m) => [...m, { role: "bot", a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", text: (e as Error).message, retry: message }]);
    } finally {
      setBusy(false);
    }
  }

  const last = [...msgs].reverse().find((m): m is { role: "bot"; a: ChatAnswer } => m.role === "bot")?.a;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-h-[calc(100dvh-170px)] flex-col">
        <div className="flex-1 space-y-4">
          {msgs.length === 0 && (
            <Panel title="Ask your course anything" description="Answers come only from the lecture video, slides and textbook in your library. If the material does not cover a question, StudyTwin says so instead of guessing.">
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGEST.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-2xl border border-hair bg-paper-2 px-4 py-3 text-left text-[14px] text-ink-2 transition hover:-translate-y-px hover:border-[var(--hair-strong)] hover:text-ink">
                    {s}
                  </button>
                ))}
              </div>
            </Panel>
          )}
          {msgs.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 12, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 0.5, ease: EASE }}>
              {m.role === "user" && (
                <div className="flex justify-end">
                  <p className="max-w-[78%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[15px] text-paper">{m.text}</p>
                </div>
              )}
              {m.role === "bot" && <AnswerCard a={m.a} onCite={open} onFollowup={(f) => send(f)} topicName={topicName} />}
              {m.role === "error" && <ErrorNote message={m.text} onRetry={() => send(m.retry)} />}
            </motion.div>
          ))}
          {busy && (
            <div className="surface space-y-3 p-5">
              <p className="inline-flex items-center gap-2 text-[13px] text-muted">
                <Search size={14} strokeWidth={1.8} className="animate-pulse" /> Searching your course material and checking citations…
              </p>
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="sticky bottom-20 mt-4 rounded-[22px] border border-hair bg-surface p-3 shadow-[var(--shadow-lift)] md:bottom-4"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <div className="flex items-end gap-3">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={2}
              placeholder="Ask about conditional probability, Bayes' rule, independence…"
              aria-label="Your question"
              className="min-h-[52px] flex-1 bg-transparent px-2 py-1.5 text-[15px] text-ink outline-none placeholder:text-muted"
            />
            <button
              type="submit"
              disabled={busy || !text.trim()}
              aria-label="Ask"
              className="grid size-11 shrink-0 place-items-center rounded-full bg-ink text-paper transition hover:-translate-y-px disabled:opacity-40"
            >
              <ArrowUp size={19} strokeWidth={1.9} />
            </button>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-hair px-1 pt-2.5">
            <Segmented id="lang" value={lang} onChange={setLang} options={[{ value: "en", label: "English" }, { value: "hi", label: "हिन्दी" }]} />
            <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-ink-2">
              <input type="checkbox" checked={outside} onChange={(e) => setOutside(e.target.checked)} className="size-4 accent-[var(--accent)]" />
              Allow general knowledge, shown separately and flagged
            </label>
          </div>
        </form>
      </div>

      <aside className="space-y-4">
        <Panel title="Last answer" description="What the tutor actually sent to the model.">
          {last ? (
            <ul className="space-y-3 text-[13.5px]">
              <Row icon={<Layers size={15} />} k="Evidence" v={`${last.context_stats.blocks} units`} />
              <Row icon={<BookOpenCheck size={15} />} k="Tokens" v={`${last.context_stats.tokens_before.toLocaleString()} → ${last.context_stats.tokens_after.toLocaleString()}`} />
              <Row icon={<Clapperboard size={15} />} k="Cited" v={sourceMix(last)} />
              <Row icon={<Languages size={15} />} k="Model" v={last.model ?? "retrieval gate (no model call)"} />
            </ul>
          ) : (
            <p className="text-[13.5px] text-muted">Ask a question to see the evidence budget, the sources used and the model.</p>
          )}
        </Panel>
        <Panel title="How grounding works">
          <ol className="space-y-2.5 text-[13.5px] text-ink-2">
            {[
              "Hybrid search (BM25 + BGE embeddings) over pages, slides, figures and 1-minute video segments.",
              "Low retrieval support: declined before any model call.",
              "LLMSlim compresses the evidence to a token budget; [S#] markers are re-attached after compression.",
              "The model must cite a source for every claim and quote it; quotes are checked against the original text.",
            ].map((s, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-paper-3 text-[11px] font-semibold text-ink-2">{i + 1}</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </Panel>
      </aside>
    </div>
  );
}

function Row({ icon, k, v }: { icon: ReactNode; k: string; v: string }) {
  return (
    <li className="flex items-start gap-2.5">
      <span className="mt-0.5 text-muted">{icon}</span>
      <span className="w-16 shrink-0 text-muted">{k}</span>
      <span className="min-w-0 flex-1 break-words font-medium text-ink">{v}</span>
    </li>
  );
}

function sourceMix(a: ChatAnswer) {
  if (!a.citations.length) return "none";
  const c: Record<string, number> = {};
  a.citations.forEach((x) => (c[x.source_kind] = (c[x.source_kind] ?? 0) + 1));
  const name: Record<string, string> = { textbook: "textbook", slides: "slides", video: "video" };
  return Object.entries(c)
    .map(([k, n]) => `${n} ${name[k] ?? k}`)
    .join(", ");
}
