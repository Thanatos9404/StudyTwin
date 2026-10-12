"""RAG evaluation on the team-built test set (eval/testset.json).

Runs the real tutor pipeline for every question in two configurations (LLMSlim context budgeting ON
and OFF) and reports:

* RAGAS (v0.4) LLM-judged metrics: faithfulness, answer relevancy, context precision (with reference),
  context recall. Judge = a different model family than the tutor (see config.judge_model), on Nebius.
* Source-location metrics against the gold page / slide / timestamp: hit@k, MRR, ID-based context
  precision and recall, citation accuracy, quote verification.
* Refusal behaviour: off-material questions declined, in-scope questions wrongly declined.
* Cost: evidence tokens (LLMSlim estimate) and provider-reported prompt tokens; latency.

    python -m studytwin.eval.rag_eval            # full run (uses Nebius credits, cached afterwards)
    python -m studytwin.eval.rag_eval --no-ragas # source-location + refusal metrics only
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import types
from pathlib import Path
from typing import Any

from .. import llm, store, tutor
from ..config import ROOT, settings

TESTSET = ROOT / "eval" / "testset.json"
OUT = ROOT / "eval" / "results"


def _short_titles() -> dict[str, str]:
    return {s["id"]: (s.get("meta") or {}).get("short_title", s["title"]) for s in store.many("SELECT id, title, meta FROM sources")}


def unit_matches(unit: dict[str, Any], gold: list[dict[str, Any]], titles: dict[str, str]) -> int | None:
    """Index of the gold location this unit matches, or None."""
    st = titles.get(unit["source_id"], "")
    loc = unit.get("loc") or {}
    for gi, g in enumerate(gold):
        if g["source"] != st:
            continue
        if "pages" in g and loc.get("page_label") in g["pages"]:
            return gi
        if "slides" in g and loc.get("slide") in g["slides"]:
            return gi
        if "time" in g and loc.get("start") is not None:
            a, b = g["time"]
            if loc["start"] < b and loc.get("end", loc["start"]) > a:
                return gi
    return None


def run_config(questions: list[dict[str, Any]], use_llmslim: bool) -> list[dict[str, Any]]:
    titles = _short_titles()
    rows = []
    for q in questions:
        r = tutor.answer(q["question"], use_llmslim=use_llmslim, record=False)
        units = [store.one("SELECT * FROM units WHERE id=?", (uid,)) for uid in r["retrieved"]]
        gold = q.get("gold") or []
        match = [unit_matches(u, gold, titles) for u in units] if gold else []
        cited = [c for c in r.get("citations", [])]
        cite_match = [unit_matches(store.one("SELECT * FROM units WHERE id=?", (c["unit_id"],)), gold, titles) for c in cited] if gold else []
        rows.append({
            "id": q["id"], "question": q["question"], "off_material": bool(q.get("off_material")), "modality": q.get("modality", ""),
            "status": r["status"], "answer": r.get("answer", ""), "reference": q.get("reference", ""),
            "contexts": r.get("contexts", []), "retrieved": r["retrieved"], "support": r["support"],
            "gold_match": match, "cite_match": cite_match,
            "quote_status": [c.get("quote_status", "") for c in cited],
            "context_tokens": (r.get("context_stats") or {}).get("tokens_after"),
            "context_tokens_before": (r.get("context_stats") or {}).get("tokens_before"),
            "prompt_tokens": (r.get("usage") or {}).get("prompt_tokens"),
            "latency": r.get("latency_s"), "uncited": r.get("uncited_sentences"),
            "cached": bool((r.get("usage") or {}).get("cached")),
        })
        print(f"  {q['id']:6s} {r['status']:12s} support={r['support']:.2f} hit={any(m is not None for m in match)} "
              f"cited_gold={any(m is not None for m in cite_match)} {r.get('latency_s')}s", flush=True)
    return rows


def location_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ins = [r for r in rows if not r["off_material"]]
    off = [r for r in rows if r["off_material"]]
    answered = [r for r in ins if r["status"] != "not_covered"]

    def mean(xs: list[float]) -> float | None:
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 4) if xs else None

    hit = [1.0 if any(m is not None for m in r["gold_match"]) else 0.0 for r in ins]
    mrr = []
    for r in ins:
        ranks = [i for i, m in enumerate(r["gold_match"]) if m is not None]
        mrr.append(1.0 / (ranks[0] + 1) if ranks else 0.0)
    id_prec = [sum(m is not None for m in r["gold_match"]) / len(r["gold_match"]) if r["gold_match"] else 0.0 for r in ins]
    q_gold = {q["id"]: len(q.get("gold") or []) for q in json.loads(TESTSET.read_text(encoding="utf-8"))["questions"]}
    id_rec = [len({m for m in r["gold_match"] if m is not None}) / max(1, q_gold.get(r["id"], 1)) for r in ins]
    cite_acc = [1.0 if any(m is not None for m in r["cite_match"]) else 0.0 for r in answered]
    cite_prec = [sum(m is not None for m in r["cite_match"]) / len(r["cite_match"]) for r in answered if r["cite_match"]]
    qs = [s for r in answered for s in r["quote_status"] if s]
    lat = sorted(r["latency"] for r in rows if r["latency"] is not None and not r.get("cached"))
    return {
        "n_in_scope": len(ins), "n_off": len(off),
        "hit_at_k": mean(hit), "mrr": mean(mrr), "id_context_precision": mean(id_prec), "id_context_recall": mean(id_rec),
        "citation_accuracy": mean(cite_acc), "citation_precision": mean(cite_prec),
        "quote_verified": round(sum(s in ("exact", "approx") for s in qs) / len(qs), 4) if qs else None,
        "quote_exact": round(sum(s == "exact" for s in qs) / len(qs), 4) if qs else None,
        "refusal_rate": mean([1.0 if r["status"] == "not_covered" else 0.0 for r in off]),
        "false_refusal_rate": mean([1.0 if r["status"] == "not_covered" else 0.0 for r in ins]),
        "context_tokens": mean([r["context_tokens"] for r in ins]),
        "context_tokens_before": mean([r["context_tokens_before"] for r in ins]),
        "prompt_tokens": mean([r["prompt_tokens"] for r in ins]),
        "latency_p50": round(statistics.median(lat), 2) if lat else None,
        "uncited_sentences_mean": mean([r["uncited"] for r in answered]),
    }


def _ragas_imports():
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # no telemetry
    # ragas 0.4.3 imports a VertexAI class that newer langchain-community removed; we never use it.
    name = "langchain_community.chat_models.vertexai"
    if name not in sys.modules:
        try:
            __import__(name)
        except Exception:  # noqa: BLE001
            m = types.ModuleType(name)
            m.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules[name] = m
    from langchain_core.embeddings import Embeddings
    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy

    from ..embed import get_embedder

    class LocalEmb(Embeddings):
        def embed_documents(self, texts):  # type: ignore[override]
            return get_embedder().encode(list(texts)).tolist()

        def embed_query(self, text):  # type: ignore[override]
            return get_embedder().encode([text])[0].tolist()

    judge = ChatOpenAI(model=settings.judge_model.id, base_url=settings.nebius_base_url, api_key=settings.nebius_api_key,
                       temperature=0, max_tokens=8192, timeout=300, max_retries=3)
    return dict(EvaluationDataset=EvaluationDataset, RunConfig=RunConfig, evaluate=evaluate,
                llm=LangchainLLMWrapper(judge), emb=LangchainEmbeddingsWrapper(LocalEmb()),
                metrics=[Faithfulness(), ResponseRelevancy(strictness=1), LLMContextPrecisionWithReference(), LLMContextRecall()])


def ragas_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    R = _ragas_imports()
    ins = [r for r in rows if not r["off_material"] and r["status"] != "not_covered" and r["contexts"]]
    ds = R["EvaluationDataset"].from_list([
        {"user_input": r["question"], "response": r["answer"], "retrieved_contexts": r["contexts"], "reference": r["reference"]}
        for r in ins
    ])
    t0 = time.time()
    res = R["evaluate"](ds, metrics=R["metrics"], llm=R["llm"], embeddings=R["emb"], show_progress=False,
                        run_config=R["RunConfig"](max_workers=8, timeout=300, max_retries=3), raise_exceptions=False)
    df = res.to_pandas()
    cols = {"faithfulness": "faithfulness", "answer_relevancy": "answer_relevancy",
            "llm_context_precision_with_reference": "context_precision", "context_recall": "context_recall"}
    out: dict[str, Any] = {"ragas_seconds": round(time.time() - t0, 1), "ragas_n": len(df)}
    per_q = {}
    for src, dst in cols.items():
        if src in df:
            vals = [float(v) for v in df[src].tolist() if v == v]  # drop NaN (judge parse failures)
            out[dst] = round(sum(vals) / len(vals), 4) if vals else None
            out[f"{dst}_n"] = len(vals)
            for r, v in zip(ins, df[src].tolist()):
                per_q.setdefault(r["id"], {})[dst] = None if v != v else round(float(v), 3)
    out["per_question"] = per_q
    return out


def main(argv: list[str]) -> None:
    data = json.loads(TESTSET.read_text(encoding="utf-8"))
    questions = data["questions"]
    if "--quick" in argv:
        questions = questions[:6] + [q for q in questions if q.get("off_material")][:2]
    OUT.mkdir(parents=True, exist_ok=True)
    configs = {
        "llmslim": (True, f"LLMSlim context budgeting ON (top-{settings.top_k} units compressed to ~{settings.context_budget} tokens, citations re-attached after compression)"),
        "no_compression": (False, f"Baseline: same top-{settings.top_k} retrieved units sent in full"),
    }
    if "--only-llmslim" in argv:
        configs.pop("no_compression")
    result: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "testset": str(TESTSET.relative_to(ROOT)),
        "n_questions": len(questions), "models": {"tutor": settings.tutor_model.id, "judge": settings.judge_model.id,
                                                    "embedder": settings.embedder},
        "configs": {},
    }
    for name, (use, desc) in configs.items():
        print(f"== {name}", flush=True)
        rows = run_config(questions, use)
        metrics = location_metrics(rows)
        if "--no-ragas" not in argv and llm.available():
            try:
                rm = ragas_metrics(rows)
                metrics.update({k: v for k, v in rm.items() if k != "per_question"})
                for r in rows:
                    r["ragas"] = rm["per_question"].get(r["id"])
            except Exception as e:  # noqa: BLE001
                metrics["ragas_error"] = str(e)[:300]
        result["configs"][name] = {"description": desc, "metrics": metrics, "rows": rows}
        print(json.dumps(metrics, indent=1), flush=True)
    result["notes"] = [
        "Test set: 34 in-scope questions with known source locations (13 textbook, 14 slides, 7 lecture video; 7 need a figure/diagram) and 10 off-material questions; written by the team (AI-assisted) and checked against the extracted text.",
        f"RAGAS {'0.4.3'} metrics use {settings.judge_model.id} as the judge (a different model from the tutor, {settings.tutor_model.id}). Questions the tutor declined are excluded from RAGAS and counted in the false-refusal rate.",
        "ID-based context precision/recall count a retrieved unit as relevant only if it is at a gold location, so precision is a conservative lower bound (other pages can also be relevant).",
        "Evidence tokens are LLMSlim's character-based estimate; prompt tokens are reported by the provider and include the system prompt.",
        "Single run, temperature 0.1; small test set, so differences of a few points between configurations are within noise.",
    ]
    (OUT / "rag_eval.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT / 'rag_eval.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
