import { AudioLines, BadgeCheck, CircleSlash, Gauge, Quote, Scale, ScanSearch, Target, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, Panel, StatTile } from "../kit";
import { api, pct, type EvalResults } from "../lib/api";
import { BarCompare, LineChart } from "./charts";
import { ErrorNote, Skeleton } from "./ui";

const f2 = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));
const POLICY: Record<string, string> = {
  studytwin_adaptive: "StudyTwin adaptive",
  random_no_repeat: "Random, no repeats",
  random_with_repeats: "Random with repeats",
};

export function Evaluation() {
  const [r, setR] = useState<EvalResults | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    setErr("");
    try {
      setR(await api.evals());
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (err) return <ErrorNote message={err} onRetry={load} />;
  if (!r)
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[118px] rounded-[18px]" />
        ))}
        <Skeleton className="h-72 sm:col-span-4" />
      </div>
    );

  const rag = r.rag_eval;
  const on = rag?.configs?.llmslim?.metrics ?? {};
  const off = rag?.configs?.no_compression?.metrics ?? {};
  const sim = r.simulation;
  const bank = r.question_bank;
  const asr = r.asr;

  return (
    <div className="space-y-4">
      {rag && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile icon={<BadgeCheck />} label="Faithfulness" value={f2(on.faithfulness)} delta="RAGAS" hint={`LLM judge, ${on.faithfulness_n} scored answers`} />
            <StatTile icon={<Target />} label="Answer relevancy" value={f2(on.answer_relevancy)} delta="RAGAS" hint={`${on.answer_relevancy_n} answers`} />
            <StatTile icon={<ScanSearch />} label="Context precision" value={f2(on.context_precision)} delta="RAGAS" hint="LLM-judged, against the reference answer" />
            <StatTile icon={<Gauge />} label="Context recall" value={f2(on.context_recall)} delta="RAGAS" hint="reference claims found in the retrieved evidence" />
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <Panel className="xl:col-span-7" title="Grounding on the team-built test set" description={`${on.n_in_scope} questions with known page / slide / timestamp, plus ${on.n_off} off-material questions. Tutor: ${rag.models?.tutor}; judge: ${rag.models?.judge}.`}>
              <table className="w-full text-[14px]">
                <thead>
                  <tr className="text-left text-[12.5px] text-muted">
                    <th className="pb-2 font-medium">Metric</th>
                    <th className="pb-2 text-right font-medium">LLMSlim on</th>
                    <th className="pb-2 text-right font-medium">Full context</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hair)]">
                  {[
                    ["Gold source retrieved in top 8", pct(on.hit_at_k), pct(off.hit_at_k)],
                    ["Mean reciprocal rank of gold source", f2(on.mrr), f2(off.mrr)],
                    ["Answers citing a gold location", pct(on.citation_accuracy), pct(off.citation_accuracy)],
                    ["Quotes found in the cited source", pct(on.quote_verified), pct(off.quote_verified)],
                    ["Off-material questions declined", pct(on.refusal_rate), pct(off.refusal_rate)],
                    ["In-scope questions wrongly declined", pct(on.false_refusal_rate, 1), pct(off.false_refusal_rate, 1)],
                    ["Evidence tokens per question (est.)", Math.round(on.context_tokens ?? 0).toLocaleString(), Math.round(off.context_tokens ?? 0).toLocaleString()],
                    ["Prompt tokens per question (provider)", Math.round(on.prompt_tokens ?? 0).toLocaleString(), Math.round(off.prompt_tokens ?? 0).toLocaleString()],
                    ["Median latency", `${f2(on.latency_p50)} s`, `${f2(off.latency_p50)} s`],
                  ].map(([k, a, b]) => (
                    <tr key={k}>
                      <td className="py-2.5 text-ink-2">{k}</td>
                      <td className="py-2.5 text-right font-semibold text-ink">{a}</td>
                      <td className="py-2.5 text-right text-ink-2">{b}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
            <Panel className="xl:col-span-5" title="RAGAS with and without LLMSlim" description="Same questions, same retrieval; only the evidence budget changes.">
              <BarCompare
                labels={["LLMSlim on", "Full context"]}
                rows={[
                  { name: "Faithful.", a: on.faithfulness, b: off.faithfulness },
                  { name: "Relevancy", a: on.answer_relevancy, b: off.answer_relevancy },
                  { name: "Ctx prec.", a: on.context_precision, b: off.context_precision },
                  { name: "Ctx recall", a: on.context_recall, b: off.context_recall },
                ]}
              />
              <div className="mt-5 grid grid-cols-2 gap-3">
                <Mini icon={<Zap size={15} />} k="Evidence tokens" v={`−${Math.round((1 - on.context_tokens / off.context_tokens) * 100)}%`} />
                <Mini icon={<Scale size={15} />} k="Prompt tokens" v={`−${Math.round((1 - on.prompt_tokens / off.prompt_tokens) * 100)}%`} />
              </div>
            </Panel>
          </div>
        </>
      )}

      {sim && (
        <div className="grid gap-4 xl:grid-cols-12">
          <Panel className="xl:col-span-7" title="Personalization with simulated students" description={sim.description}>
            <LineChart
              series={Object.entries(sim.curve as Record<string, number[]>).map(([k, v], i) => ({ name: POLICY[k] ?? k, values: v, color: i === 0 ? "var(--accent)" : i === 1 ? "#7A6F6A" : "#C9B9A8" }))}
              xLabel="session (0 = before the first session)"
            />
            <p className="mt-3 text-[12.5px] text-muted">{sim.caveat}</p>
          </Panel>
          <Panel className="xl:col-span-5" title="Per profile" description="True mastery gain over 6 sessions, BKT estimate error, repeated questions.">
            <ul className="divide-y divide-[var(--hair)] text-[13.5px]">
              {(sim.rows as { profile: string; policy: string; gain: number; bkt_mae_first: number; bkt_mae_last: number; repeat_rate: number }[])
                .filter((x) => x.policy !== "random_with_repeats" || true)
                .map((x) => (
                  <li key={x.profile + x.policy} className="grid grid-cols-[1fr_auto] gap-x-3 py-2">
                    <span className="text-ink">
                      {x.profile.replace("_", " ")} <span className="text-muted">· {POLICY[x.policy]}</span>
                    </span>
                    <b className={x.policy === "studytwin_adaptive" ? "text-accent" : "text-ink-2"}>+{pct(x.gain)}</b>
                    <span className="col-span-2 text-[12px] text-muted">
                      BKT error {f2(x.bkt_mae_first)} → {f2(x.bkt_mae_last)} · repeats {pct(x.repeat_rate)}
                    </span>
                  </li>
                ))}
            </ul>
          </Panel>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {bank && <StatTile icon={<BadgeCheck />} label="Questions verified" value={`${bank.verified}/${bank.generated}`} delta={pct(bank.verified_rate)} tone="pos" hint={`blind-solved by ${bank.verifier}`} />}
        {bank && <StatTile icon={<CircleSlash />} label="Near-duplicates blocked" value={bank.duplicates ?? "–"} hint="cosine ≥ 0.90, logged top-up run" />}
        {asr && <StatTile icon={<AudioLines />} label="Transcript word error" value={pct(asr.wer, 1)} hint={`${asr.model} vs official OCW captions`} />}
        {asr && <StatTile icon={<Quote />} label="Transcription speed" value={`${asr.realtime_factor}×`} hint={`${Math.round(asr.duration_s / 60)} min lecture in ${Math.round(asr.wall_time_s / 60)} min on a laptop CPU`} />}
      </div>

      {rag?.notes && (
        <Panel title="How to read these numbers">
          <ul className="space-y-2 text-[13.5px] text-ink-2">
            {(rag.notes as string[]).map((n) => (
              <li key={n} className="flex gap-2.5">
                <Badge>i</Badge>
                <span>{n}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Mini({ icon, k, v }: { icon: React.ReactNode; k: string; v: string }) {
  return (
    <div className="rounded-2xl bg-paper-2 p-3.5">
      <p className="flex items-center gap-1.5 text-[12.5px] text-muted">
        {icon}
        {k}
      </p>
      <p className="t-num mt-1 text-[22px] text-ink">{v}</p>
    </div>
  );
}
