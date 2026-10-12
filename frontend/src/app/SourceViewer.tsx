import { ExternalLink } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Badge } from "../kit";
import { api, fmtTs, type UnitView } from "../lib/api";
import { ErrorNote, KindBadge, Sheet, Skeleton } from "./ui";

type Ctx = { open: (unitId: string, quote?: string) => void };
const SourceCtx = createContext<Ctx>({ open: () => undefined });
export const useSource = () => useContext(SourceCtx);

/** Opens any knowledge unit at its exact location: highlighted textbook page, slide, or video timestamp. */
export function SourceProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<{ id: string; quote: string } | null>(null);
  const [data, setData] = useState<UnitView | null>(null);
  const [err, setErr] = useState("");
  const open = useCallback((id: string, quote = "") => setTarget({ id, quote }), []);

  const load = useCallback(async () => {
    if (!target) return;
    setData(null);
    setErr("");
    try {
      setData(await api.unit(target.id, target.quote));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [target]);
  useEffect(() => {
    load();
  }, [load]);

  const title = data ? data.unit.label : "Opening source";
  const subtitle = data ? (
    <span className="inline-flex flex-wrap items-center gap-2">
      <KindBadge kind={data.source.kind} />
      <span>{data.source.title}</span>
      {data.source.license && <span className="text-muted">· {data.source.license}</span>}
    </span>
  ) : null;

  return (
    <SourceCtx.Provider value={{ open }}>
      {children}
      <Sheet open={!!target} onClose={() => setTarget(null)} title={title} subtitle={subtitle}>
        {err && <ErrorNote message={err} onRetry={load} />}
        {!data && !err && (
          <div className="space-y-3">
            <Skeleton className="h-[420px]" />
            <Skeleton className="h-20" />
          </div>
        )}
        {data && <UnitBody data={data} quote={target?.quote ?? ""} />}
      </Sheet>
    </SourceCtx.Provider>
  );
}

function UnitBody({ data, quote }: { data: UnitView; quote: string }) {
  const { unit, view } = data;
  return (
    <div className="space-y-4">
      {view.type === "textbook" && view.page_image && <PageWithHighlights src={view.page_image} rects={view.highlights || []} size={view.page_size || [612, 792]} />}
      {view.type === "slides" && (view.image || view.page_image) && (
        <img src={view.image || view.page_image || ""} alt={`Slide ${view.slide}`} className="w-full rounded-2xl border border-hair" />
      )}
      {view.type === "video" && <Video view={view} />}
      <div className="flex flex-wrap items-center gap-2">
        {view.type === "textbook" && <Badge tone="accent">Page {view.page_label}</Badge>}
        {view.type === "slides" && <Badge tone="accent">Slide {view.slide}</Badge>}
        {view.type === "video" && (
          <Badge tone="accent">
            {fmtTs(view.start)}–{fmtTs(view.end)}
          </Badge>
        )}
        {unit.kind === "figure" && <Badge>Figure · described by a vision model</Badge>}
        {unit.section && view.type !== "video" && <Badge>{unit.section}</Badge>}
        {view.pdf_url && (
          <a
            href={view.pdf_url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex h-9 items-center gap-2 rounded-full px-4 font-display text-[13.5px] font-semibold text-ink transition hover:bg-[var(--hair)]"
          >
            Open the PDF here <ExternalLink size={14} strokeWidth={1.7} />
          </a>
        )}
      </div>
      {unit.kind === "figure" && unit.image && view.type === "textbook" && (
        <img src={`/media/${unit.image}`} alt="Figure" className="max-h-72 rounded-2xl border border-hair bg-surface object-contain p-2" />
      )}
      {quote && (
        <blockquote className="rounded-2xl border-l-2 border-accent bg-accent-soft/60 px-4 py-3 text-[14px] text-ink">
          <span className="t-eyebrow mb-1 block !text-[11px]">Quoted in the answer</span>“{quote}”
        </blockquote>
      )}
      <div>
        <p className="t-eyebrow mb-2 !text-[11px]">Extracted text</p>
        <p className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-2xl bg-paper-2 p-4 text-[13.5px] leading-relaxed text-ink-2">{unit.text}</p>
      </div>
    </div>
  );
}

function PageWithHighlights({ src, rects, size }: { src: string; rects: number[][]; size: number[] }) {
  const ref = useRef<HTMLImageElement>(null);
  const [scale, setScale] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / size[0]);
    const ro = new ResizeObserver(update);
    ro.observe(el);
    if (el.complete) update();
    return () => ro.disconnect();
  }, [size]);
  useEffect(() => {
    if (scale && rects.length) {
      document.getElementById("hl-0")?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [scale, rects]);
  return (
    <div className="relative overflow-hidden rounded-2xl border border-hair">
      <img ref={ref} src={src} alt="Textbook page" className="w-full" onLoad={() => ref.current && setScale(ref.current.clientWidth / size[0])} />
      {scale > 0 &&
        rects.map((r, i) => (
          <div key={i} id={`hl-${i}`} className="hl-box" style={{ left: r[0] * scale - 2, top: r[1] * scale - 2, width: r[2] * scale + 4, height: r[3] * scale + 4 }} />
        ))}
    </div>
  );
}

function Video({ view }: { view: UnitView["view"] }) {
  const ref = useRef<HTMLVideoElement>(null);
  if (view.youtube_id) {
    return (
      <iframe
        title="Lecture video"
        className="aspect-video w-full rounded-2xl border border-hair"
        src={`https://www.youtube-nocookie.com/embed/${view.youtube_id}?start=${Math.floor(view.start || 0)}&autoplay=1`}
        allow="autoplay; encrypted-media"
        allowFullScreen
      />
    );
  }
  if (!view.video_url) return <p className="text-[14px] text-muted">Video file not available locally; the transcript excerpt is below.</p>;
  return (
    <video
      ref={ref}
      controls
      preload="metadata"
      className="aspect-video w-full rounded-2xl border border-hair bg-black"
      src={view.video_url}
      onLoadedMetadata={() => {
        if (ref.current) {
          ref.current.currentTime = view.start || 0;
          ref.current.play().catch(() => undefined);
        }
      }}
    />
  );
}
