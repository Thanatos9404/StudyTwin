import {
  ArrowRight,
  AudioLines,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  CircleSlash,
  Clapperboard,
  FileSearch,
  GraduationCap,
  Highlighter,
  Lightbulb,
  ListChecks,
  MessageSquareText,
  Network,
  Presentation,
  Quote,
  ShieldCheck,
  Timer,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Badge,
  Bento,
  BentoCard,
  Button,
  CTASection,
  FeatureSplit,
  FooterCard,
  Hero,
  Marquee,
  Nav,
  ScrollWords,
  SectionHeader,
  SmoothScroll,
  StatTile,
  Wordmark,
} from "../kit";
import { AnswerCard } from "../app/AnswerCard";
import { CourseMap } from "../app/charts";
import radar from "../fixtures/radar_answer.json";
import question from "../fixtures/question.json";
import topicsFixture from "../fixtures/topics.json";
import { api, pct, type ChatAnswer, type EvalResults, type Source, type Topic } from "../lib/api";
import { Rich } from "../lib/rich";

const GITHUB = "https://github.com/Thanatos9404/StudyTwin";
const toApp = () => {
  location.hash = "#app";
};

export function Landing() {
  const [evals, setEvals] = useState<EvalResults | null>(null);
  const [sources, setSources] = useState<Source[] | null>(null);
  useEffect(() => {
    api.evals().then(setEvals).catch(() => setEvals(null));
    api.sources().then(setSources).catch(() => setSources(null));
  }, []);

  return (
    <SmoothScroll>
      <Nav
        brand={<Wordmark name="STUDYTWIN" />}
        links={[
          { label: "How it works", href: "#how" },
          { label: "Features", href: "#features" },
          { label: "Results", href: "#results" },
          { label: "Source", href: GITHUB },
        ]}
        cta={{ label: "Open the app", href: "#app" }}
      />
      <Hero
        eyebrow={
          <>
            <GraduationCap size={14} strokeWidth={1.8} className="text-accent" /> Track D · Multimodal AI Hackathon 2026 · IIT Mandi
          </>
        }
        title="A tutor that shows its *sources.*"
        subtitle="StudyTwin turns lecture videos, slides and a textbook into one cited knowledge base, then quizzes you where your mastery is weakest."
        primary={{ label: "Open the app", href: "#app" }}
        secondary={{ label: "How it works", href: "#how" }}
        product={<HeroProduct />}
      />

      <section className="section-y !pb-0">
        <div className="container-x">
          <p className="t-eyebrow mb-6 text-center">Built with</p>
          <Marquee
            items={[
              "Nebius Token Factory",
              "gpt-oss-120b",
              "DeepSeek V4 Flash",
              "GLM-5.3 Flash vision",
              "faster-whisper",
              "BGE-small embeddings",
              "LLMSlim",
              "RAGAS",
              "FastAPI",
              "MIT OpenCourseWare 6.041",
              "OpenStax Introductory Statistics",
            ]}
          />
        </div>
      </section>

      <section className="section-y">
        <div className="container-x">
          <ScrollWords text="General chatbots answer *anything.* A study companion should answer from your course, show you exactly where, and know what you have not learned yet." />
        </div>
      </section>

      <section id="features" className="section-y !pt-0">
        <div className="container-x space-y-28">
          <FeatureSplit
            eyebrow="Grounded tutor"
            title={
              <>
                Every claim opens its <span className="t-serif">source.</span>
              </>
            }
            body="Answers carry numbered citations. Each one opens the textbook page with the quote highlighted, the exact slide, or the lecture at the right second. If your material does not cover a question, StudyTwin says so."
            bullets={[
              { icon: <Highlighter size={16} />, label: "Page highlights" },
              { icon: <Presentation size={16} />, label: "Slide crops" },
              { icon: <Clapperboard size={16} />, label: "Video timestamps" },
              { icon: <Quote size={16} />, label: "Verbatim quotes" },
            ]}
            visual={<SourcePreview />}
          />
          <FeatureSplit
            flip
            eyebrow="Adaptive practice"
            title={
              <>
                Quizzes aimed at what you <span className="t-serif">don't know.</span>
              </>
            }
            body="Multiple-choice, numerical and short-answer questions are written from your material, solved blind by a second model family, and served where your mastery is lowest. Each wrong option names the misconception behind it."
            action={
              <Button href="#app/practice" icon={<ArrowRight size={16} />}>
                Try a diagnostic
              </Button>
            }
            visual={<QuestionPreview />}
          />
          <FeatureSplit
            eyebrow="Learner model"
            title={
              <>
                Mastery that follows the <span className="t-serif">prerequisites.</span>
              </>
            }
            body="Bayesian Knowledge Tracing updates every topic after each answer and each tutor conversation. A forgetting curve schedules reviews, and practice starts with the prerequisites you are missing."
            bullets={[
              { icon: <BrainCircuit size={16} />, label: "BKT per topic" },
              { icon: <Timer size={16} />, label: "Spaced review" },
              { icon: <Network size={16} />, label: "Prerequisite map" },
              { icon: <ListChecks size={16} />, label: "Cold-start diagnostic" },
            ]}
            visual={
              <div className="surface p-4">
                <p className="mb-2 px-1 font-display text-[14px] font-semibold text-ink">Course flow map, built from the demo course</p>
                <CourseMap topics={topicsFixture as unknown as Topic[]} />
              </div>
            }
          />
        </div>
      </section>

      <section id="how" className="section-y bg-paper !pt-0">
        <div className="container-x">
          <SectionHeader eyebrow="How it works" title="From raw lectures to a cited tutor" lead="Five stages, all running on a laptop CPU except the model calls, which go to Nebius Token Factory." />
          <Bento className="mt-14">
            <BentoCard
              span={7}
              icon={<FileSearch size={18} />}
              title="Ingest without preprocessing"
              body="PDF pages become passages and cropped figures; handout pages are split into single slides; Whisper transcribes the lecture into one-minute segments; a vision model describes every diagram, numbers included."
              visual={<IngestStrip sources={sources} />}
            />
            <BentoCard span={5} icon={<Network size={18} />} title="One topic map" body="An LLM reads a digest of every source and proposes topics, subtopics, key concepts and prerequisites. Every unit is then tagged to its closest subtopic." />
            <BentoCard span={4} icon={<ShieldCheck size={18} />} title="Two-stage refusal" body="Weak retrieval support is declined before any model call; the model must cite every claim, and its quotes are checked against the original text." />
            <BentoCard span={4} icon={<Zap size={18} />} title="LLMSlim context budget" body="Retrieved evidence is compressed to a token budget with extractive, query-aware selection. Citation markers are re-attached after compression, so they cannot be lost." />
            <BentoCard span={4} icon={<BadgeCheck size={18} />} title="Cross-model verification" body="DeepSeek writes each question; gpt-oss solves it without the key. Only agreeing questions enter the bank, and near-duplicates are blocked." />
          </Bento>
        </div>
      </section>

      <section id="results" className="section-y !pt-0">
        <div className="container-x">
          <SectionHeader eyebrow="Results" title="Measured on our own test set" lead="34 questions with known page, slide or timestamp, plus 10 off-material questions. Numbers load from the evaluation files in the repository." align="left" />
          <Results evals={evals} />
        </div>
      </section>

      <CTASection
        title={
          <>
            Study from sources you can <span className="t-serif">check.</span>
          </>
        }
        lead="Open the app, create a student, take the diagnostic, then ask the tutor about the radar example."
        action={
          <Button href="#app" size="lg" icon={<ArrowRight size={17} />}>
            Open the app
          </Button>
        }
      />
      <FooterCard
        brand={<Wordmark name="STUDYTWIN" />}
        blurb="A source-grounded, adaptive study companion. Built for Track D (Personalized Tutoring & Adaptive Learning) of the Multimodal AI Hackathon 2026 by KamandPrompt, IIT Mandi."
        columns={[
          {
            title: "Product",
            links: [
              { label: "Open the app", href: "#app" },
              { label: "How it works", href: "#how" },
              { label: "Results", href: "#results" },
            ],
          },
          {
            title: "Project",
            links: [
              { label: "Source code (MIT)", href: GITHUB },
              { label: "Data and licences", href: `${GITHUB}/blob/main/DATA.md` },
              { label: "LLMSlim", href: "https://pypi.org/project/llmslim/" },
            ],
          },
        ]}
        legal={
          <span>
            Code MIT. Demo course: MIT OpenCourseWare 6.041 Fall 2010 (CC BY-NC-SA) and OpenStax Introductory Statistics, Chapter 3 (CC BY 4.0). Fonts OFL. No stock imagery. Built by Yashvardhan Thanvi with AI assistance (see the README).
          </span>
        }
      />
    </SmoothScroll>
  );
}

function HeroProduct() {
  const a = radar as unknown as ChatAnswer;
  return (
    <div className="grid text-left md:grid-cols-[200px_1fr]">
      <div className="hidden border-r border-hair bg-paper-2/60 p-4 md:block">
        <Wordmark name="STUDYTWIN" />
        <div className="mt-6 space-y-1">
          {[
            [MessageSquareText, "Tutor"],
            [ListChecks, "Practice"],
            [BrainCircuit, "Progress"],
            [BookOpen, "Library"],
          ].map(([Icon, l], i) => {
            const I = Icon as typeof BookOpen;
            return (
              <div key={l as string} className={`flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] ${i === 0 ? "bg-paper-3 text-ink" : "text-ink-2"}`}>
                <I size={15} strokeWidth={1.6} />
                {l as string}
              </div>
            );
          })}
        </div>
      </div>
      <div className="max-h-[560px] overflow-hidden bg-paper p-4 md:p-6">
        <div className="mb-4 flex justify-end">
          <p className="max-w-[80%] rounded-[18px] rounded-br-md bg-ink px-4 py-2.5 text-[14px] text-paper">{a.question}</p>
        </div>
        <AnswerCard a={a} onCite={toApp} compact />
      </div>
    </div>
  );
}

function SourcePreview() {
  return (
    <div className="surface overflow-hidden text-left">
      <div className="flex items-center justify-between border-b border-hair px-5 py-3.5">
        <div>
          <p className="font-display text-[14.5px] font-semibold text-ink">6.041 L2 slides · slide 5</p>
          <p className="text-[12px] text-muted">MIT 6.041 Lecture 2 slides · CC BY-NC-SA</p>
        </div>
        <Badge tone="accent">Slide 5</Badge>
      </div>
      <img src="/demo/radar-slide.png" alt="Lecture slide with the radar probability tree" className="mx-auto max-h-[300px] w-auto p-4" />
      <div className="mx-4 mb-4 rounded-2xl border-l-2 border-accent bg-accent-soft/60 px-4 py-3 text-[13px] text-ink">
        <span className="t-eyebrow mb-1 block !text-[10.5px]">Diagram described by the vision model</span>
        Tree: P(A)=0.05 and P(Aᶜ)=0.95; P(B | A)=0.99, P(B | Aᶜ)=0.10.
      </div>
    </div>
  );
}

function QuestionPreview() {
  const q = question as { stem: string; options: string[]; answer: string; misconceptions: Record<string, string>; sources: string[]; difficulty: number };
  const wrong = Object.keys(q.misconceptions)[0] ?? "A";
  return (
    <div className="surface p-5 text-left">
      <div className="flex flex-wrap gap-2">
        <Badge tone="accent">Conditional probability</Badge>
        <Badge>Multiple choice</Badge>
        <Badge>Verified by a second model</Badge>
      </div>
      <Rich text={q.stem} className="mt-4 !text-[14.5px]" />
      <div className="mt-4 grid gap-2">
        {q.options.map((o, i) => {
          const L = "ABCD"[i];
          const right = L === q.answer;
          const isWrong = L === wrong;
          return (
            <div
              key={L}
              className={`flex items-center gap-3 rounded-xl border px-3.5 py-2 text-[13.5px] ${right ? "border-[color-mix(in_oklab,var(--pos)_45%,transparent)] bg-[color-mix(in_oklab,var(--pos)_8%,transparent)]" : isWrong ? "border-[color-mix(in_oklab,var(--neg)_45%,transparent)] bg-[color-mix(in_oklab,var(--neg)_7%,transparent)]" : "border-hair"}`}
            >
              <span className="grid size-5 place-items-center rounded-full bg-paper-3 text-[11px] font-semibold">{L}</span>
              {o}
            </div>
          );
        })}
      </div>
      <p className="mt-4 flex gap-2 text-[13.5px] text-ink">
        <Lightbulb size={16} strokeWidth={1.7} className="mt-0.5 shrink-0 text-accent" />
        <span>
          <b>If you chose {wrong}:</b> {q.misconceptions[wrong]}
        </span>
      </p>
      <p className="mt-2 text-[12px] text-muted">Source: {q.sources.join(", ")}</p>
    </div>
  );
}

function IngestStrip({ sources }: { sources: Source[] | null }) {
  const count = (kind: string, unit: string) => sources?.filter((s) => s.kind === kind).reduce((a, s) => a + (s.unit_counts[unit] ?? 0), 0);
  const items = [
    { icon: <BookOpen size={15} />, k: "Textbook", v: sources ? `${count("textbook", "text")} passages · ${count("textbook", "figure")} figures` : "…" },
    { icon: <Presentation size={15} />, k: "Slides", v: sources ? `${count("slides", "slide")} slides · ${count("slides", "figure")} diagrams` : "…" },
    { icon: <AudioLines size={15} />, k: "Lecture", v: sources ? `${count("video", "transcript")} one-minute segments` : "…" },
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {items.map((i) => (
        <div key={i.k} className="rounded-2xl bg-surface p-3.5 shadow-[var(--shadow-soft)]">
          <p className="flex items-center gap-1.5 text-[12.5px] text-muted">
            {i.icon}
            {i.k}
          </p>
          <p className="mt-1 font-display text-[14px] font-semibold text-ink">{i.v}</p>
        </div>
      ))}
    </div>
  );
}

function Results({ evals }: { evals: EvalResults | null }) {
  if (!evals?.rag_eval) {
    return <p className="mt-10 text-[15px] text-muted">Start the backend to load the measured results (eval/results/*.json).</p>;
  }
  const on = evals.rag_eval.configs.llmslim.metrics;
  const off = evals.rag_eval.configs.no_compression.metrics;
  const sim = evals.simulation?.summary;
  const asr = evals.asr;
  const bank = evals.question_bank;
  return (
    <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatTile icon={<Quote />} label="Answers citing a gold location" value={pct(on.citation_accuracy)} hint={`of ${on.n_in_scope - Math.round(on.false_refusal_rate * on.n_in_scope)} answered in-scope questions; page, slide or timestamp`} />
      <StatTile icon={<CircleSlash />} label="Off-material questions declined" value={pct(on.refusal_rate)} delta={`${on.n_off}/${on.n_off}`} tone="pos" hint={`in-scope wrongly declined: ${pct(on.false_refusal_rate, 1)}`} />
      <StatTile icon={<ShieldCheck />} label="Faithfulness (RAGAS)" value={on.faithfulness?.toFixed(2)} hint={`judge ${evals.rag_eval.models.judge}, n=${on.faithfulness_n}`} />
      <StatTile icon={<Zap />} label="Prompt tokens with LLMSlim" value={`−${Math.round((1 - on.prompt_tokens / off.prompt_tokens) * 100)}%`} tone="pos" hint={`${Math.round(on.prompt_tokens)} vs ${Math.round(off.prompt_tokens)} provider-reported tokens per question`} />
      {sim && (
        <StatTile
          icon={<BrainCircuit />}
          label="Mastery gain, simulated students"
          value={`+${Math.round(sim.studytwin_adaptive.gain * 100)} pts`}
          delta={`random: +${Math.round(sim.random_no_repeat.gain * 100)}`}
          tone="pos"
          hint="4 profiles x 40 students x 6 sessions; 0% repeated questions"
        />
      )}
      {asr && <StatTile icon={<AudioLines />} label="Lecture transcript word error" value={pct(asr.wer, 1)} hint={`${asr.model}, vs official MIT OCW captions; ${bank ? `${bank.verified}/${bank.generated} questions passed verification` : ""}`} />}
    </div>
  );
}
