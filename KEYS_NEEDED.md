# Keys needed

StudyTwin needs **one** key for its LLM features, and none to run in offline mode or to run the tests.

| Key | Needed for | Where to get it | Cost |
|---|---|---|---|
| `NEBIUS_API_KEY` | Tutor answers, vision descriptions of slides/figures, topic map, question generation and verification, short-answer grading, flashcards, RAGAS judging | Nebius Token Factory, https://tokenfactory.nebius.com (Project, API keys) | Pay-as-you-go open-weight models; the whole demo (ingestion + bank + evaluation) used well under US$5 of credits. Free/trial credits are enough. |

No other keys: embeddings (BGE-small) and speech-to-text (faster-whisper) run locally; YouTube captions are
fetched without a key; nothing calls OpenAI or Anthropic APIs.

## How to provide it

1. `cp .env.example .env`
2. Put the key in `.env`: `NEBIUS_API_KEY=...` (the file is git-ignored), **or** set
   `STUDYTWIN_ENV_FILE=/path/to/another/.env` and StudyTwin reads only `NEBIUS_API_KEY` from that file.
3. Restart the server. The sidebar shows "Live · Nebius Token Factory" when the key is picked up, or
   "Offline mode" without it.

## Without a key (offline mode)

Set `STUDYTWIN_OFFLINE=1` (or leave the key empty). Ingestion still works (no vision descriptions), topics come
from textbook section headings, tutor answers are extractive (LLMSlim selects the most relevant cited
sentences), questions are template cloze MCQs, and short answers are graded by keyword overlap. The test
suite always runs offline.

## For the hackathon submission

* Do not commit `.env`. Check with `git status` that it is not listed before pushing.
* If the key was ever pasted anywhere public, rotate it in the Token Factory console.
