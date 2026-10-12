# Data sources and licences

StudyTwin's demo course uses only openly licensed material. The code is MIT-licensed; the material below
keeps its own licence, and so do the files derived from it.

## Course material

| File | Source | Licence | Notes |
|---|---|---|---|
| `data/demo/openstax_introstats_ch3_probability_topics.pdf` | Barbara Illowsky, Susan Dean, *Introductory Statistics*, OpenStax, Rice University. https://openstax.org/details/books/introductory-statistics | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Unmodified extract of PDF pages 183-221 (Chapter 3 "Probability Topics", printed pages 175-213), made by `scripts/fetch_demo_data.py` from the full book PDF. "Download for free at https://openstax.org/details/books/introductory-statistics". |
| `data/demo/MIT6_041F10_L01.pdf`, `L02.pdf`, `L03.pdf` | John Tsitsiklis, *6.041 Probabilistic Systems Analysis and Applied Probability*, Fall 2010, MIT OpenCourseWare. https://ocw.mit.edu/courses/6-041-probabilistic-systems-analysis-and-applied-probability-fall-2010/ | [CC BY-NC-SA](https://ocw.mit.edu/terms/) (OCW lists CC BY-NC-SA 4.0) | Lecture slide handouts for Lectures 1-3, unmodified. |
| Lecture 2 video `MIT6_041F11_lec02_300k.mp4` (not committed; 118 MB) | Same course, "Lecture 2: Conditioning and Bayes' Rule", via the MIT OCW mirror on the Internet Archive: https://archive.org/details/MIT6.041F10 | CC BY-NC-SA (archive.org metadata: CC BY-NC-SA 3.0) | Downloaded by `scripts/fetch_demo_data.py`. Transcribed locally with faster-whisper. |
| `data/demo/upload_examples/MIT6_041F11_lec03_300k.srt` | Official captions for Lecture 3 "Independence" (Internet Archive / OCW) | CC BY-NC-SA | Not pre-ingested; a small file for demonstrating a live upload in the Library. |
| `data/demo/MIT6_041F11_lec02_300k.srt` | Official captions for Lecture 2 (Internet Archive / OCW) | CC BY-NC-SA | Used as the reference for the transcription word error rate, and as a fallback transcript (`seed_demo.py --captions`). |

Attribution for the MIT material: *MIT OpenCourseWare, https://ocw.mit.edu, 6.041 Probabilistic Systems
Analysis and Applied Probability, Fall 2010, John Tsitsiklis. License: Creative Commons BY-NC-SA.*

This is a non-commercial hackathon project, which the NC term permits. Anyone reusing the demo material must
follow its licence (attribution; non-commercial and share-alike for the MIT material).

## Derived files

| File | Derived from | Licence |
|---|---|---|
| `data/workspace/` (created at runtime, not committed): rendered page and slide images, figure crops, Whisper transcript, vision-model descriptions, SQLite knowledge base | All sources above | Same as the source each item comes from |
| `frontend/public/demo/radar-slide.png` | Crop of 6.041 Lecture 2 slides, slide 5 | CC BY-NC-SA |
| `frontend/public/demo/kitten-tree.png` | Crop of the tree-diagram figure on OpenStax *Introductory Statistics* p. 204 | CC BY 4.0 |
| `frontend/src/fixtures/*.json` | A recorded tutor answer, the topic map and one generated question; they quote short excerpts of the sources | Same as the quoted sources |
| `eval/testset.json` | Questions and reference answers written by the StudyTwin team about the sources | MIT (the facts belong to the sources) |

## Other assets

* Fonts (Open Runde, Inter, Instrument Serif, Fragment Mono, Silkscreen): SIL Open Font License, self-hosted
  via Fontsource. KaTeX fonts: MIT/OFL, bundled.
* Icons: Lucide (ISC).
* No stock photography; clouds and gradients are generated in SVG/CSS.
* Models are used through Nebius Token Factory (gpt-oss-120b, DeepSeek-V4-Flash-0731, GLM-5.3-Flash) or run
  locally (BAAI/bge-small-en-v1.5, MIT; faster-whisper `small`, MIT, OpenAI Whisper weights under MIT).
