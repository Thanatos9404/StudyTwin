import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { EASE } from "../kit/lib/motion";
import type { Topic } from "../lib/api";

function wrap(text: string, max = 22): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > max && cur) {
      lines.push(cur);
      cur = w;
    } else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
}

/** Course flow map: topics laid out by prerequisite depth, coloured by mastery when given. */
export function CourseMap({ topics, mastery, onSelect }: { topics: Topic[]; mastery?: Record<string, number>; onSelect?: (id: string) => void }) {
  const layout = useMemo(() => {
    const depth: Record<string, number> = {};
    const by = Object.fromEntries(topics.map((t) => [t.id, t]));
    const d = (id: string, seen = new Set<string>()): number => {
      if (depth[id] != null) return depth[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const ps = (by[id]?.prerequisites ?? []).filter((p) => by[p]);
      depth[id] = ps.length ? Math.max(...ps.map((p) => d(p, seen))) + 1 : 0;
      return depth[id];
    };
    topics.forEach((t) => d(t.id));
    const cols: string[][] = [];
    topics.forEach((t) => (cols[depth[t.id]] ??= []).push(t.id));
    const W = 200, H = 74, GX = 64, GY = 22;
    const rows = Math.max(...cols.map((c) => c.length), 1);
    const pos: Record<string, { x: number; y: number }> = {};
    cols.forEach((c, ci) => {
      const off = ((rows - c.length) * (H + GY)) / 2;
      c.forEach((id, ri) => (pos[id] = { x: 12 + ci * (W + GX), y: 12 + off + ri * (H + GY) }));
    });
    return { pos, W, H, width: 24 + cols.length * W + (cols.length - 1) * GX, height: 24 + rows * H + (rows - 1) * GY };
  }, [topics]);
  const [hover, setHover] = useState<string | null>(null);
  if (!topics.length) return null;
  const { pos, W, H } = layout;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${layout.width} ${layout.height}`} className="h-auto w-full min-w-[640px]" role="img" aria-label="Course flow map of topics and prerequisites">
        {topics.flatMap((t) =>
          (t.prerequisites || []).filter((p) => pos[p]).map((p) => {
            const a = pos[p], b = pos[t.id];
            const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
            const on = hover === t.id || hover === p;
            return (
              <path
                key={p + t.id}
                d={`M${x1},${y1} C${x1 + 36},${y1} ${x2 - 36},${y2} ${x2},${y2}`}
                fill="none"
                stroke={on ? "var(--accent)" : "var(--hair-strong)"}
                strokeWidth={on ? 2 : 1.4}
                markerEnd="url(#arrow)"
              />
            );
          }),
        )}
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
          </marker>
        </defs>
        {topics.map((t) => {
          const p = pos[t.id];
          const m = mastery?.[t.id];
          const lines = wrap(t.name);
          return (
            <g
              key={t.id}
              transform={`translate(${p.x},${p.y})`}
              onMouseEnter={() => setHover(t.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(t.id)}
              className={onSelect ? "cursor-pointer" : ""}
            >
              <rect width={W} height={H} rx={16} fill="var(--surface)" stroke={hover === t.id ? "var(--accent)" : "var(--hair-strong)"} />
              {m != null && <rect x={0} y={H - 5} width={W * Math.max(0.03, m)} height={5} rx={2.5} fill={m >= 0.8 ? "var(--pos)" : "var(--accent)"} opacity={m >= 0.8 ? 1 : 0.35 + m * 0.65} />}
              <text x={14} y={20} fontSize={10.5} fill="var(--muted)" fontFamily="var(--font-mono)" letterSpacing="0.06em">
                {t.id}
                {m != null ? ` · ${Math.round(m * 100)}%` : ""}
              </text>
              {lines.map((l, i) => (
                <text key={i} x={14} y={38 + i * 15} fontSize={13} fontWeight={600} fill="var(--ink)" fontFamily="var(--font-display)">
                  {l}
                </text>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

const PALETTE = ["#6E56CF", "#C9502E", "#2F8F6B", "#B4536A", "#3E7CB1", "#A07B1E", "#7A6F6A", "#8E3B6C"];

/** Hairline line chart (no heavy axes), one series per key, tooltip on hover. */
export function LineChart({
  series,
  height = 220,
  yMax = 1,
  xLabel,
  format = (v: number) => `${Math.round(v * 100)}%`,
  guide,
}: {
  series: { name: string; values: number[]; color?: string }[];
  height?: number;
  yMax?: number;
  xLabel?: string;
  format?: (v: number) => string;
  guide?: { y: number; label: string };
}) {
  const [hx, setHx] = useState<number | null>(null);
  const W = 640, P = 28;
  const n = Math.max(...series.map((s) => s.values.length), 2);
  const x = (i: number) => P + (i / (n - 1)) * (W - 2 * P);
  const y = (v: number) => height - P - (v / yMax) * (height - 2 * P);
  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="h-auto w-full"
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const rel = ((e.clientX - r.left) / r.width) * W;
          setHx(Math.max(0, Math.min(n - 1, Math.round(((rel - P) / (W - 2 * P)) * (n - 1)))));
        }}
        onMouseLeave={() => setHx(null)}
      >
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={P} x2={W - P} y1={y(t * yMax)} y2={y(t * yMax)} stroke="var(--hair)" />
            <text x={P - 6} y={y(t * yMax) + 4} fontSize={10} textAnchor="end" fill="var(--muted)">
              {format(t * yMax)}
            </text>
          </g>
        ))}
        {guide && (
          <g>
            <line x1={P} x2={W - P} y1={y(guide.y)} y2={y(guide.y)} stroke="var(--muted)" strokeDasharray="4 4" opacity={0.5} />
            <text x={W - P} y={y(guide.y) - 5} fontSize={10} textAnchor="end" fill="var(--muted)">
              {guide.label}
            </text>
          </g>
        )}
        {series.map((s, k) => {
          const c = s.color ?? PALETTE[k % PALETTE.length];
          const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
          return (
            <g key={s.name}>
              {k === 0 && (
                <>
                  <defs>
                    <linearGradient id="fill0" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor={c} stopOpacity={0.2} />
                      <stop offset="100%" stopColor={c} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <path d={`${d} L${x(s.values.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill="url(#fill0)" />
                </>
              )}
              <motion.path d={d} fill="none" stroke={c} strokeWidth={2.2} strokeLinecap="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: EASE }} />
              {s.values.map((v, i) => (hx === i ? <circle key={i} cx={x(i)} cy={y(v)} r={4} fill={c} /> : null))}
            </g>
          );
        })}
        {hx != null && <line x1={x(hx)} x2={x(hx)} y1={P / 2} y2={height - P} stroke="var(--hair-strong)" />}
        {xLabel && (
          <text x={W / 2} y={height - 6} fontSize={10.5} textAnchor="middle" fill="var(--muted)">
            {xLabel}
          </text>
        )}
      </svg>
      {hx != null && (
        <div className="surface pointer-events-none absolute right-3 top-2 px-3 py-2 text-[12.5px]">
          <p className="t-eyebrow mb-1 !text-[10.5px]">Point {hx}</p>
          {series.map((s, k) =>
            s.values[hx] != null ? (
              <p key={s.name} className="flex items-center gap-2">
                <span className="size-2 rounded-full" style={{ background: s.color ?? PALETTE[k % PALETTE.length] }} />
                <span className="text-ink-2">{s.name}</span>
                <b className="ml-auto pl-3 text-ink">{format(s.values[hx])}</b>
              </p>
            ) : null,
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {series.map((s, k) => (
          <span key={s.name} className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-2">
            <span className="size-2.5 rounded-full" style={{ background: s.color ?? PALETTE[k % PALETTE.length] }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Rounded-top bar pairs for comparing two configurations. */
export function BarCompare({ rows, labels, format = (v: number) => v.toFixed(2) }: { rows: { name: string; a: number | null; b: number | null }[]; labels: [string, string]; format?: (v: number) => string }) {
  const max = Math.max(...rows.flatMap((r) => [r.a ?? 0, r.b ?? 0]), 1e-9);
  return (
    <div>
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0,1fr))` }}>
        {rows.map((r) => (
          <div key={r.name} className="flex flex-col items-center">
            <div className="flex h-40 w-full items-end justify-center gap-1.5">
              {[r.a, r.b].map((v, i) => (
                <motion.div
                  key={i}
                  title={`${labels[i]}: ${v == null ? "–" : format(v)}`}
                  initial={{ height: 0 }}
                  whileInView={{ height: `${((v ?? 0) / max) * 100}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.9, ease: EASE, delay: i * 0.08 }}
                  className="relative w-[38%] max-w-9 rounded-t-lg"
                  style={{ background: i === 0 ? "var(--accent)" : "color-mix(in oklab, var(--accent) 28%, var(--paper-3))" }}
                >
                  <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-[11px] font-semibold text-ink">{v == null ? "–" : format(v)}</span>
                </motion.div>
              ))}
            </div>
            <p className="mt-2 text-center text-[12px] leading-tight text-ink-2">{r.name}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 flex gap-4 text-[12.5px] text-ink-2">
        {labels.map((l, i) => (
          <span key={l} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: i === 0 ? "var(--accent)" : "color-mix(in oklab, var(--accent) 28%, var(--paper-3))" }} />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}
