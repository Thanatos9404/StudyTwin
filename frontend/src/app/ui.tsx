import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, BookOpen, CheckCircle2, Clapperboard, Presentation, RotateCcw, X } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Button } from "../kit";
import { cn } from "../kit/lib/cn";
import { EASE } from "../kit/lib/motion";
import type { Citation } from "../lib/api";
import { fmtTs } from "../lib/api";

export function KindIcon({ kind, size = 14 }: { kind: string; size?: number }) {
  const p = { size, strokeWidth: 1.7 };
  if (kind === "video") return <Clapperboard {...p} />;
  if (kind === "slides") return <Presentation {...p} />;
  return <BookOpen {...p} />;
}

export function KindBadge({ kind }: { kind: string }) {
  const label = kind === "video" ? "Lecture video" : kind === "slides" ? "Slides" : "Textbook";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-3 px-2.5 py-1 text-[12px] font-semibold text-ink-2">
      <KindIcon kind={kind} size={13} />
      {label}
    </span>
  );
}

export function locText(c: Pick<Citation, "loc">) {
  const l = c.loc || {};
  if (l.start != null) return `${fmtTs(l.start)}–${fmtTs(l.end)}`;
  if (l.slide != null) return `slide ${l.slide}`;
  if (l.page_label != null) return `p. ${l.page_label}`;
  return "";
}

export function SourceList({ cites, onOpen, compact }: { cites: Citation[]; onOpen: (c: Citation) => void; compact?: boolean }) {
  if (!cites.length) return null;
  return (
    <ul className="mt-4 space-y-1.5 border-t border-hair pt-4">
      {cites.map((c) => (
        <li key={c.unit_id + c.tag}>
          <button
            onClick={() => onOpen(c)}
            className="group flex w-full items-start gap-3 rounded-2xl px-3 py-2.5 text-left transition hover:bg-paper-2"
          >
            {c.tag && <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">{c.tag.slice(1)}</span>}
            <span className="mt-0.5 shrink-0 text-muted">
              <KindIcon kind={c.source_kind} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13.5px] font-medium text-ink">
                {c.label}
                {c.section && c.source_kind !== "video" && <span className="font-normal text-muted"> · {c.section}</span>}
              </span>
              {!compact && c.quote && (
                <span className="mt-0.5 block text-[13px] leading-snug text-ink-2">
                  “{c.quote.length > 150 ? c.quote.slice(0, 150) + "…" : c.quote}”
                  {c.quote_status === "exact" && (
                    <span className="ml-1.5 inline-flex items-center gap-1 align-middle text-[11.5px] font-semibold text-pos">
                      <CheckCircle2 size={12} strokeWidth={2} /> verbatim
                    </span>
                  )}
                  {c.quote_status === "approx" && <span className="ml-1.5 align-middle text-[11.5px] font-semibold text-muted">close match</span>}
                </span>
              )}
            </span>
            <span className="shrink-0 self-center text-[12px] text-muted opacity-0 transition group-hover:opacity-100">Open</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ChipToggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={cn(
        "rounded-full border px-3.5 py-1.5 text-[13.5px] font-medium transition",
        on ? "border-transparent bg-ink text-paper" : "border-hair bg-surface text-ink-2 hover:border-[var(--hair-strong)] hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

export function MasteryBar({ p, className }: { p: number; className?: string }) {
  return (
    <div className={cn("relative h-2 overflow-hidden rounded-full bg-paper-3", className)}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(2, p * 100)}%` }}
        transition={{ duration: 0.9, ease: EASE }}
        className={cn("absolute inset-y-0 left-0 rounded-full", p >= 0.8 ? "bg-pos" : "bg-accent")}
        style={p < 0.8 ? { opacity: 0.35 + p * 0.65 } : undefined}
      />
    </div>
  );
}

export function LevelBadge({ level, p }: { level: string; p: number }) {
  const tone = level === "mastered" ? "pos" : level === "developing" ? "accent" : "neutral";
  return (
    <span className="shrink-0 whitespace-nowrap">
      <Badge tone={tone}>
        {Math.round(p * 100)}% · {level}
      </Badge>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

export function Empty({ icon, title, body, action }: { icon: ReactNode; title: string; body: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="grid size-11 place-items-center rounded-full border border-hair bg-paper-2 text-ink [&>svg]:size-5 [&>svg]:stroke-[1.6]">{icon}</div>
      <p className="mt-4 font-display text-[16px] font-semibold text-ink">{title}</p>
      <div className="mt-1.5 max-w-[46ch] text-[14px] text-muted">{body}</div>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-hair bg-paper-2 p-4 text-[14px]">
      <AlertTriangle size={18} strokeWidth={1.7} className="mt-0.5 shrink-0 text-neg" />
      <div className="flex-1">
        <p className="font-medium text-ink">Something went wrong</p>
        <p className="text-muted">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry} icon={<RotateCcw size={14} />}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** Right-hand sheet (source viewer). Matches the kit surfaces and the blur-fade motion. */
export function Sheet({ open, onClose, title, subtitle, children }: { open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="scrim"
            className="fixed inset-0 z-40 bg-[color-mix(in_oklab,var(--ink)_18%,transparent)]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            key="sheet"
            role="dialog"
            aria-modal="true"
            initial={{ x: 40, opacity: 0, filter: "blur(6px)" }}
            animate={{ x: 0, opacity: 1, filter: "blur(0px)" }}
            exit={{ x: 40, opacity: 0, filter: "blur(4px)" }}
            transition={{ duration: 0.45, ease: EASE }}
            className="fixed inset-y-2 right-2 z-50 flex w-[min(620px,calc(100vw-16px))] flex-col overflow-hidden rounded-[22px] border border-hair bg-surface shadow-[var(--shadow-lift)]"
          >
            <div className="flex items-start justify-between gap-4 border-b border-hair px-5 py-4">
              <div className="min-w-0">
                <div className="font-display text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</div>
                {subtitle && <div className="mt-1 text-[13px] text-muted">{subtitle}</div>}
              </div>
              <button aria-label="Close" onClick={onClose} className="grid size-9 shrink-0 place-items-center rounded-full border border-hair text-ink-2 transition hover:text-ink">
                <X size={17} strokeWidth={1.7} />
              </button>
            </div>
            <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
