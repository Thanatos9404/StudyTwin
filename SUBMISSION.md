# Devpost submission: StudyTwin

Copy each section into the matching Devpost field. Numbers are from `eval/results/` (see the README for how
each was measured). Replace the two links marked TODO before submitting.

---

## Project name

StudyTwin

## Tagline (one line)

A tutor that shows its sources: lecture videos, slides and a textbook become one cited knowledge base that answers, quizzes, and adapts to what you have not learned yet.

## Track

Track D: Personalized Tutoring & Adaptive Learning

## Links

* GitHub (public): https://github.com/Thanatos9404/StudyTwin  (TODO: create the public repo and push)
* Demo video (YouTube, unlisted is fine): TODO

---

## Inspiration

Before an exam I study from a recorded lecture, the professor's slides and a textbook chapter, all in different
places. General chatbots will happily answer any question, but they do not tell me where the answer is in my
course, they never say "your material does not cover this", and they have no idea which topics I am weak in.
I wanted a study companion I could trust the way I trust a good teaching assistant: it points at the exact page,
slide or minute of the lecture, it admits when something is outside the course, and it keeps track of what I
actually know.

I also build LLMSlim, an open-source context layer for AI agents, and a tutor is a perfect test for it: the
evidence has to be compressed to fit a token budget without ever losing a citation.

## What it does

StudyTwin ingests a course with no manual preprocessing and turns it into citable knowledge units:

* **Textbook PDFs** become page-linked passages plus cropped figures; **slide PDFs** become one unit per slide
  (2x2 handout pages are split automatically); **PowerPoint** works too.
* **Lecture videos or audio** are transcribed locally with Whisper into one-minute, timestamped segments;
  caption files and YouTube links also work.
* A **vision model** describes every diagram and transcribes every equation, so a question like "what is
  P(plane | blip) in the radar example?" can be answered from a probability tree that exists only as a drawing.
* An LLM builds a **topic map** (topics, subtopics, key concepts, prerequisites), and every unit is tagged to it.

Then it teaches:

* **Grounded tutor.** Every claim carries a citation that opens the textbook page with the quote highlighted,
  the slide, or the lecture video at the right second. Off-material questions are declined; optional general
  knowledge is shown separately with a warning. Answers can be in Hindi with the same citations, read aloud,
  and questions can be asked by voice.
* **Adaptive assessment.** Multiple-choice, numerical and short-answer questions, written from the material by
  one model and solved blind by a second model family before they enter the bank. Quizzes, mock exams and a
  cold-start diagnostic; no question is repeated while unseen ones remain. Each answer gets cited feedback and
  the misconception behind a wrong option; each assessment ends with a report of weak topics, misconceptions
  and what to review.
* **Learner model.** Bayesian Knowledge Tracing per topic, updated after every answer and every tutor
  conversation (a stated misconception lowers mastery, a correct explanation raises it), a forgetting curve for
  spaced review, prerequisite-aware quiz targeting, a study plan to exam day, and flashcards for weak topics.

## How we built it

* **Backend:** Python, FastAPI, SQLite. PDFs with pypdfium2 (text, page renders, slide-frame detection, figure
  crops, highlight boxes), python-pptx, faster-whisper `small` on CPU, youtube-transcript-api.
* **Models on Nebius Token Factory:** gpt-oss-120b (tutor, grading, verification), DeepSeek V4 Flash (topic
  map, question writing, RAGAS judge), GLM-5.3 Flash (vision). Embeddings: BAAI bge-small-en-v1.5 locally.
* **Retrieval and grounding:** BM25 + dense retrieval fused with reciprocal rank fusion, a retrieval-support
  gate, then **LLMSlim** compresses the top 8 units to a ~1,000-token budget. Citation markers are attached after
  compression, so they cannot be dropped, and LLMSlim's extractive mode keeps sentences verbatim, so every
  quote can be checked against the source.
* **Learner model:** BKT with difficulty-dependent slip and type-dependent guess, partial credit, soft evidence
  from conversations, memory half-lives, and a policy that targets the three weakest unmastered topics at the
  difficulty with a ~70% predicted success rate.
* **Evaluation:** RAGAS 0.4 with a different model as judge, plus source-location metrics on a team-built test
  set; a simulated-student study; Whisper word error rate against official captions.
* **Frontend:** React 18 + TypeScript + Tailwind v4 + Motion, a landing page and the study app, served by FastAPI.
* **Content:** MIT OpenCourseWare 6.041 (Lecture 2 video, Lecture 1-3 slides, CC BY-NC-SA) and OpenStax
  *Introductory Statistics* Chapter 3 (CC BY 4.0).
* **AI assistance:** built with Claude Code (Claude Opus 5.5) as a pair programmer; details in the README.

## Challenges we ran into

* **Slides printed four to a page.** The OCW slides are 2x2 handouts, so "slide 5" did not exist as a page. We
  detect the slide frames in the PDF drawing commands and split each page into real slides.
* **Diagrams carry the numbers.** The radar example's probabilities live in a tree drawing whose PDF text is
  scrambled. Sending every slide to a vision model, and storing its description as its own citable unit, fixed
  both retrieval and answers.
* **Citations in the wild.** Models wrote `【S1】`, `[S1, S2]`, `[ S5 ]` and even markers wrapped in zero-width
  spaces. A normaliser handles all of them; we found the last one only because our evaluation flagged an
  answer with no citations.
* **Honest evaluation.** RAGAS needed a judge that is not the tutor; some judge outputs fail to parse, so we
  report n for every metric. A second full run moved some numbers by several points, so we report both.
* **A shared, busy laptop CPU.** Whisper transcribed a 51-minute lecture in about 9 minutes; everything else
  is light enough to run alongside it.

## Accomplishments that we're proud of

On our 44-question test set (34 with known page, slide or timestamp; 10 off-material):

* **100%** of answered in-scope questions cited a correct source location, and **98%** of quoted excerpts were
  found in the cited source.
* **10/10** off-material questions declined; 1 of 34 in-scope questions wrongly declined.
* RAGAS faithfulness **0.97**, answer relevancy **0.92**, context precision **0.84**, context recall **0.96**.
* LLMSlim cut the prompt by **30%** (provider-reported tokens) and the evidence by **38%** with no measured loss
  in grounding.
* **64 of 66** generated questions passed blind cross-model verification.
* In simulation, the adaptive policy raised true mastery by **+32 points** over six sessions versus +27 for
  random practice without repeats and +24 with repeats, for every student profile, with **0%** repeated questions.
* Whisper `small` on CPU: **4.6%** word error rate against the official lecture captions.

## What we learned

* Grounding is mostly plumbing: keeping the location attached to every unit through chunking, compression and
  generation matters more than the prompt.
* Compression and citation are compatible if the markers live outside the compressed text and the compressor
  never rewrites sentences.
* A second model solving each question blind is a cheap, effective filter, but two models agreeing is not proof,
  so the bank still needs human spot checks.
* Simulated students are useful for testing a policy, but they share the tutor's assumptions; real learners are
  the next test.

## What's next

* A pilot with classmates on a real course, to fit the BKT parameters and measure learning gains with people.
* Frame analysis for lecture videos (board work), not just the transcript.
* Skill-level (subtopic) mastery and item-response calibration of question difficulty from answer data.
* Better Hindi and Hinglish support end to end, including Hindi lecture audio.
* A hosted multi-user version with accounts and instructor dashboards.

## Built with

Python, FastAPI, SQLite, React, TypeScript, Tailwind CSS, Motion, Vite, Nebius Token Factory, gpt-oss-120b,
DeepSeek V4 Flash, GLM-5.3 Flash, sentence-transformers (BGE-small), faster-whisper, pypdfium2, python-pptx,
LLMSlim, RAGAS, LangChain (judge client), KaTeX, marked, MIT OpenCourseWare, OpenStax, Claude Code (AI coding
assistant)

## Team

Yashvardhan Thanvi (solo), BCA, BIT Mesra Jaipur
