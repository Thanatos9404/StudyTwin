# Demo video script (target 6:30, limit 3-10 min)

The Devpost video must show the project running, the source-upload workflow, grounded chat, the assessment
pipeline and the technical architecture, with English audio or subtitles. Upload to YouTube as **Unlisted**.

## Before recording (15 minutes)

1. Start the app: `.venv\Scripts\activate` then `uvicorn studytwin.api:app --port 8765`.
   Open http://localhost:8765, wait until the sidebar says **Live · Nebius Token Factory**.
2. Warm up: open the app and ask any one question that is NOT in the script (the first answer after a restart
   loads the embedding model and is slow). Do not pre-ask the scripted questions; real answers take 2-15 s, so
   cut the waiting in editing and put a small "sped up" label on those cuts.
3. Browser: a clean window at about 1440x900, zoom 100%, bookmarks bar hidden, notifications off.
   Have `data/demo/upload_examples/MIT6_041F11_lec03_300k.srt` ready in a file-explorer window.
4. If you want a fresh learner: create the new student live (step 4). The existing "Demo Student" is a test
   account; you can ignore it.
5. Record the screen at 1080p with your microphone. Speak slowly; the narration below is about 900 words.

## Script

| Time | On screen | Say (roughly) |
|---|---|---|
| **0:00-0:20** | Landing page hero at the top. Let the headline and the tilted product frame animate in. | "Hi, I'm Yashvardhan. This is StudyTwin, my Track D project: a study companion that turns lecture videos, slides and a textbook into one knowledge base, answers only from that material, shows exactly where every answer comes from, and adapts quizzes to what you don't know yet." |
| **0:20-0:40** | Scroll slowly through "General chatbots answer anything", then the three feature sections. | "General chatbots answer anything, with no link back to your course and no memory of what you know. StudyTwin is built around three ideas: every claim opens its source, quizzes aim at your weak topics, and a learner model tracks mastery per topic." |
| **0:40-1:30** | Click **Open the app** -> **Library**. Point at the five sources: the 51-minute lecture video, three slide decks, the textbook chapter. Point at the unit counts and licences. Scroll to the course flow map and one topic card. | "Here's the demo course: MIT OpenCourseWare 6.041 lecture 2 on conditioning and Bayes' rule, the lecture 1 to 3 slides, and the probability chapter of OpenStax Introductory Statistics, all openly licensed. Nothing was preprocessed by hand. Whisper transcribed the video on my laptop CPU into one-minute segments with timestamps. The slide PDFs are four slides per page, so StudyTwin detects the slide frames and splits them. A vision model describes every diagram. Then an LLM built this topic map: seven topics with prerequisites, and every unit is tagged to a subtopic." |
| **1:30-1:50** | Drag `MIT6_041F11_lec03_300k.srt` onto the drop zone. Show the progress bar reach "Ingested". | "Adding material is one drag and drop. Here are the captions of lecture 3; any PDF, PowerPoint, video, audio file or YouTube link works the same way, and the new units are tagged to the existing topics automatically." |
| **1:50-2:45** | **Tutor**. Click the suggestion "In the radar example, what is P(airplane present given radar registers)?". When the answer appears, point at the status badge, the numbered citations and the LLMSlim line. Click the slide citation: the sheet shows slide 5 with the tree. Close. Click a lecture citation: the video starts at that minute. Close. | "Let me ask about the radar example. The probabilities only exist in a tree diagram on a slide, but the vision model read them, so the answer works through Bayes' rule step by step, and every line is cited. This one opens slide 5, the exact slide. This one opens the lecture at the moment the professor explains it. Each citation has a quote that's checked word for word against the source. Down here: LLMSlim compressed the evidence by about 40 percent before it went to the model, and all eight citations survived." |
| **2:45-3:15** | Type: "So independent events are the same as mutually exclusive events, right?" Show the correction and the mastery line ("Independence ... misconception"). | "Conversations update the learner model too. I'll state a common misconception. The tutor corrects me with textbook citations, and notice the bottom line: it detected the misconception and lowered my mastery of independence." |
| **3:15-3:45** | Type: "Explain the central limit theorem." Show "Not in your course material". Then tick **Allow general knowledge** and ask "What is a p-value?". Show the separate grey "Outside your course material" box. | "Ask something the course doesn't cover, and it says so instead of guessing. If I allow general knowledge, it still refuses to mix it in: the outside answer is shown separately and clearly labelled." |
| **3:45-4:00** | Switch the language to **हिन्दी** and ask "What does Bayes' rule compute? Use the radar example." | "For Hindi-medium learners, the same grounded answer can come back in Hindi, with the same citations." |
| **4:00-5:00** | Click **New student**, type your name, rate two topics, **Save and take the diagnostic**. Answer the first question correctly, then choose a wrong option on the next and show the feedback: correct answer, "Likely misconception", cited explanation, mastery before -> after. Answer the remaining ones quickly (cut in editing), then show the report: weak topics, misconceptions, "What to review next". Click **Practice this topic**, answer one numerical question. | "A new student starts cold. The intake sets starting estimates, and the diagnostic asks one question per topic. Every question was written from the material by one model and solved blind by a different model before it entered the bank. When I pick a wrong option, I get the misconception behind it, a worked solution with clickable sources, and my Bayesian Knowledge Tracing estimate updates. The report lists weak topics and what to read next, and Practice this topic starts an adaptive quiz that targets my weakest topics at about seventy percent difficulty, with no repeated questions." |
| **5:00-5:30** | **Progress**: stat tiles, mastery bars, the course map coloured by mastery, the mastery-over-time chart. Click **Make my plan**, then **Make cards** and flip one card. | "Progress shows mastery per topic, with retention from a forgetting curve, the prerequisite map coloured by mastery, and how my estimates moved. It can plan study days until the exam and make flashcards for weak topics, each linked to its source." |
| **5:30-6:15** | **Evaluation**: RAGAS tiles, the comparison table, the simulated-students chart. Then switch to the README on GitHub and scroll to the architecture diagram. | "We evaluated it properly. On our own test set of 34 questions with known pages, slides and timestamps plus 10 off-material questions, RAGAS faithfulness is 0.97 and context recall 0.96, every answered question cited a correct location, and all off-material questions were declined. LLMSlim cut prompt tokens by 30 percent with no measured loss. In simulation, the adaptive policy produced the largest mastery gains for every student profile. The architecture: ingestion into citable units, hybrid retrieval, LLMSlim budgeting, a cited answer that is validated, and a verified question bank feeding the learner model. Models run on Nebius Token Factory; embeddings and Whisper run locally." |
| **6:15-6:35** | Back to the landing page footer. | "Limitations: one demo course, simulated rather than real students, and BKT parameters set by hand. Code is MIT-licensed on GitHub, and I built it with Claude Code as my AI pair programmer, disclosed in the README. Thanks for watching." |

## Shot list for the Devpost gallery

Screenshots are in `docs/screenshots/` (landing and app at 1440px and 375px). Add 2-3 frames from the video:
the radar answer with the slide open, a quiz feedback card with a misconception, and the Evaluation page.

## If something goes wrong while recording

* An answer takes long: keep talking over it or cut it; the Nebius call is usually 2-10 s.
* "Not in your course material" on an in-scope question: rephrase with words from the slides (the tutor declines
  rather than guesses; this happened on 1 of 34 test questions).
* Video citation shows no player: the lecture video was not downloaded; run `python scripts/fetch_demo_data.py`
  and restart (`seed_demo.py` links the local file), or the viewer falls back to streaming from archive.org.
