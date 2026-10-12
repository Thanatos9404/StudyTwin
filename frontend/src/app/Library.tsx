import { motion } from "motion/react";
import { CheckCircle2, FileUp, Link2, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Panel } from "../kit";
import { cn } from "../kit/lib/cn";
import { EASE } from "../kit/lib/motion";
import { api, type Job, type Source } from "../lib/api";
import { CourseMap } from "./charts";
import { useApp } from "./StudyApp";
import { ErrorNote, KindIcon, Skeleton } from "./ui";

const unitName: Record<string, string> = { text: "passages", slide: "slides", figure: "figures", transcript: "timed segments" };

export function Library() {
  const { topics, refreshTopics } = useApp();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [err, setErr] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [kind, setKind] = useState("");
  const [yt, setYt] = useState("");
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setErr("");
    try {
      setSources(await api.sources());
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function poll(id: string) {
    for (;;) {
      const j = await api.job(id);
      setJob(j);
      if (j.status === "done" || j.status === "error") {
        if (j.status === "done") {
          await refreshTopics();
          await load();
        }
        return;
      }
      await new Promise((r) => setTimeout(r, 1200));
    }
  }
  async function upload(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("kind", kind);
    fd.append("title", f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
    setJob({ id: "", status: "queued", progress: 0, message: `Uploading ${f.name}` });
    try {
      poll((await api.upload(fd)).job_id);
    } catch (e) {
      setJob({ id: "", status: "error", progress: 0, message: (e as Error).message });
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-12">
        <Panel className="xl:col-span-5" title="Add course material" description="No manual preprocessing: the file type picks the pipeline, and every unit keeps its page, slide or timestamp.">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files[0];
              if (f) upload(f);
            }}
            className={cn("flex cursor-pointer flex-col items-center rounded-[20px] border-2 border-dashed px-6 py-9 text-center transition", drag ? "border-accent bg-accent-soft/50" : "border-hair hover:border-[var(--hair-strong)]")}
          >
            <span className="grid size-11 place-items-center rounded-full border border-hair bg-surface text-ink">
              <FileUp size={19} strokeWidth={1.6} />
            </span>
            <span className="mt-3 font-display text-[15px] font-semibold text-ink">Drop a file or browse</span>
            <span className="mt-1 text-[13px] text-muted">Textbook or slide PDF, PowerPoint, lecture video or audio (transcribed locally with Whisper), SRT/VTT captions</span>
            <input
              ref={fileRef}
              type="file"
              className="sr-only"
              accept=".pdf,.pptx,.mp4,.mkv,.webm,.mov,.mp3,.wav,.m4a,.srt,.vtt"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
                e.target.value = "";
              }}
            />
          </label>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
            PDF type:
            {[
              ["", "Auto-detect"],
              ["textbook", "Textbook"],
              ["slides", "Slides"],
            ].map(([v, l]) => (
              <button key={v} onClick={() => setKind(v)} className={cn("rounded-full border px-3 py-1 transition", kind === v ? "border-transparent bg-ink text-paper" : "border-hair hover:text-ink")}>
                {l}
              </button>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <label className="flex h-11 flex-1 items-center gap-2 rounded-full border border-hair bg-surface px-4 text-[14px]">
              <Link2 size={15} strokeWidth={1.7} className="text-muted" />
              <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="YouTube link (uses published captions)" className="w-full bg-transparent outline-none placeholder:text-muted" />
            </label>
            <Button
              disabled={!yt.trim()}
              onClick={async () => {
                try {
                  poll((await api.youtube(yt.trim())).job_id);
                  setYt("");
                } catch (e) {
                  setJob({ id: "", status: "error", progress: 0, message: (e as Error).message });
                }
              }}
            >
              Add
            </Button>
          </div>
          {job && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }} className="mt-5 rounded-2xl bg-paper-2 p-4">
              <div className="flex items-center gap-2 text-[14px]">
                {job.status === "done" ? <CheckCircle2 size={16} className="text-pos" /> : job.status === "error" ? <TriangleAlert size={16} className="text-neg" /> : <span className="size-2 animate-pulse rounded-full bg-accent" />}
                <span className="font-medium text-ink">{job.status === "done" ? "Ingested" : job.status === "error" ? "Could not ingest" : "Ingesting"}</span>
                <span className="ml-auto text-muted">{Math.round((job.progress || 0) * 100)}%</span>
              </div>
              <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-paper-3">
                <motion.div className="h-full rounded-full bg-accent" animate={{ width: `${(job.progress || 0) * 100}%` }} transition={{ duration: 0.5, ease: EASE }} />
              </div>
              <p className="mt-2 text-[13px] text-muted">{job.message}</p>
            </motion.div>
          )}
        </Panel>
        <Panel className="xl:col-span-7" title="Course flow map" description="Built by the LLM from a digest of every source; arrows point from prerequisite to topic.">
          {topics.length ? <CourseMap topics={topics} /> : <Skeleton className="h-64" />}
        </Panel>
      </div>

      <Panel title="Sources" description="Openly licensed demo course: MIT OCW 6.041 (Lecture 2 video, Lectures 1-3 slides) and OpenStax Introductory Statistics, Chapter 3.">
        {err && <ErrorNote message={err} onRetry={load} />}
        {!sources && !err && <Skeleton className="h-40" />}
        {sources && (
          <ul className="divide-y divide-[var(--hair)]">
            {sources.map((s) => {
              const meta = s.meta as { transcript?: string; model?: string; duration_s?: number };
              return (
                <li key={s.id} className="flex flex-wrap items-center gap-4 py-4">
                  <span className="grid size-10 shrink-0 place-items-center rounded-full border border-hair bg-paper-2 text-ink">
                    <KindIcon kind={s.kind} size={17} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[14.5px] font-medium text-ink">{s.title}</p>
                    <p className="text-[12.5px] text-muted">
                      {s.attribution}
                      {meta.transcript === "whisper" && ` · Whisper ${meta.model} transcript of ${Math.round((meta.duration_s ?? 0) / 60)} min`}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(s.unit_counts).map(([k, n]) => (
                      <Badge key={k}>
                        {n} {unitName[k] ?? k}
                      </Badge>
                    ))}
                    {s.license && <Badge tone="accent">{s.license}</Badge>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel title="Topics, subtopics and key concepts" description="Every unit is tagged to its closest subtopic and to the key concepts it mentions.">
        <div className="grid gap-3 md:grid-cols-2">
          {topics.map((t) => (
            <div key={t.id} className="rounded-2xl border border-hair p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="font-display text-[15px] font-semibold text-ink">
                  <span className="mr-1.5 font-mono text-[12px] text-muted">{t.id}</span>
                  {t.name}
                </p>
                <span className="shrink-0 text-[12px] text-muted">{Object.entries(t.coverage).map(([k, n]) => `${n} ${k}`).join(" · ")}</span>
              </div>
              <p className="mt-1 text-[13px] text-ink-2">{t.description}</p>
              {t.prerequisites.length > 0 && <p className="mt-1 text-[12.5px] text-muted">Needs: {t.prerequisites.join(", ")}</p>}
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {t.key_concepts.map((c) => (
                  <span key={c} className="rounded-full bg-paper-2 px-2.5 py-1 text-[12px] text-ink-2">
                    {c}
                  </span>
                ))}
              </div>
              <ul className="mt-3 space-y-1 border-t border-hair pt-3">
                {t.subtopics.map((s) => (
                  <li key={s.id} className="flex justify-between text-[13px]">
                    <span className="text-ink-2">
                      <span className="font-mono text-[11.5px] text-muted">{s.id}</span> {s.name}
                    </span>
                    <span className="text-muted">{s.units} units</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
