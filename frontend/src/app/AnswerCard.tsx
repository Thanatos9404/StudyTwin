import { CircleSlash, Globe2, Info, ShieldCheck, Sparkles, Square, TrendingDown, TrendingUp, Volume2, Zap } from "lucide-react";
import { useState } from "react";
import { Badge } from "../kit";
import type { ChatAnswer, Citation } from "../lib/api";
import { pct } from "../lib/api";
import { Rich } from "../lib/rich";
import { canSpeak, speak, stopSpeaking } from "../lib/speech";
import { SourceList } from "./ui";

const STATUS = {
  answered: { label: "Source-backed answer", tone: "pos" as const, icon: <ShieldCheck size={13} strokeWidth={2} /> },
  partial: { label: "Partly covered by your material", tone: "accent" as const, icon: <Info size={13} strokeWidth={2} /> },
  not_covered: { label: "Not in your course material", tone: "neg" as const, icon: <CircleSlash size={13} strokeWidth={2} /> },
};

/** One tutor answer: status, cited markdown, sources with verbatim checks, LLMSlim budget line. */
export function AnswerCard({
  a,
  onCite,
  onFollowup,
  topicName,
  compact,
}: {
  a: ChatAnswer;
  onCite: (unitId: string, quote: string) => void;
  onFollowup?: (q: string) => void;
  topicName?: (id: string) => string;
  compact?: boolean;
}) {
  const st = STATUS[a.status] ?? STATUS.answered;
  const cs = a.context_stats;
  const openCite = (c: Citation) => onCite(c.unit_id, c.quote);
  const [speaking, setSpeaking] = useState(false);
  return (
    <div className="surface min-w-0 overflow-hidden p-5 text-left md:p-6">
      <div className="flex items-center justify-between gap-3">
        <Badge tone={st.tone}>
          {st.icon}
          {st.label}
        </Badge>
        {!compact && canSpeak() && (
          <button
            onClick={() => {
              if (speaking) {
                stopSpeaking();
                setSpeaking(false);
              } else {
                setSpeaking(true);
                speak(a.answer, () => setSpeaking(false));
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-full border border-hair px-3 py-1 text-[12.5px] font-medium text-ink-2 transition hover:text-ink"
            aria-label={speaking ? "Stop reading aloud" : "Read the answer aloud"}
          >
            {speaking ? <Square size={13} strokeWidth={1.8} /> : <Volume2 size={14} strokeWidth={1.8} />}
            {speaking ? "Stop" : "Listen"}
          </button>
        )}
      </div>
      <Rich text={a.answer} cites={a.citations} onCite={onCite} className="mt-3" />
      {a.outside_knowledge && (
        <div className="mt-4 flex gap-3 rounded-2xl border border-hair bg-paper-2 p-4 text-[14px]">
          <Globe2 size={17} strokeWidth={1.7} className="mt-0.5 shrink-0 text-muted" />
          <div>
            <p className="font-semibold text-ink">Outside your course material</p>
            <p className="text-[12.5px] text-muted">General knowledge, not checked against your sources.</p>
            <p className="mt-1.5 text-ink-2">{a.outside_knowledge}</p>
          </div>
        </div>
      )}
      <SourceList cites={a.citations} onOpen={openCite} compact={compact} />
      {!compact && a.followups?.length > 0 && onFollowup && (
        <div className="mt-4 flex flex-wrap gap-2">
          {a.followups.map((f) => (
            <button key={f} onClick={() => onFollowup(f)} className="rounded-full border border-hair bg-surface px-3 py-1.5 text-[13px] text-ink-2 transition hover:border-[var(--hair-strong)] hover:text-ink">
              <Sparkles size={12} strokeWidth={1.8} className="mr-1.5 inline -translate-y-px text-accent" />
              {f}
            </button>
          ))}
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-hair pt-3 text-[12.5px] text-muted">
        {cs?.llmslim ? (
          <span className="inline-flex items-center gap-1.5 text-ink-2">
            <Zap size={13} strokeWidth={1.8} className="text-accent" />
            LLMSlim: evidence {cs.tokens_before.toLocaleString()} → {cs.tokens_after.toLocaleString()} tokens (−{cs.saved_pct}%), {cs.citations_preserved} citations kept
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <Zap size={13} strokeWidth={1.8} />
            Evidence {cs?.tokens_before ?? 0} tokens, under budget
          </span>
        )}
        <span>retrieval support {a.support.toFixed(2)}</span>
        {a.latency_s != null && <span>{a.latency_s}s</span>}
        {a.mastery_update && topicName && (
          <span className="inline-flex items-center gap-1.5">
            {a.mastery_update.after >= a.mastery_update.before ? <TrendingUp size={13} strokeWidth={1.8} className="text-pos" /> : <TrendingDown size={13} strokeWidth={1.8} className="text-neg" />}
            {topicName(a.mastery_update.topic_id)} {pct(a.mastery_update.before)} → {pct(a.mastery_update.after)} ({a.mastery_update.signal})
          </span>
        )}
      </div>
    </div>
  );
}
