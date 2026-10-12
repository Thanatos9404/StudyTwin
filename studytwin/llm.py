"""Nebius Token Factory client (OpenAI-compatible API) with a disk cache and a usage meter.

* Every call is cached by (model, messages, params) so evaluation re-runs are reproducible
  and do not spend credits twice.
* Usage (tokens, estimated USD) is recorded per role for the UI and the README.
* When no key is configured (or STUDYTWIN_OFFLINE=1), ``available()`` is False and callers
  use their deterministic offline fallbacks instead.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ModelSpec, settings


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0


@dataclass
class Meter:
    by_model: dict[str, Usage] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, spec: ModelSpec, pt: int, ct: int, secs: float, cached: bool) -> None:
        with self.lock:
            u = self.by_model.setdefault(spec.id, Usage())
            if cached:
                u.cached += 1
                return
            u.calls += 1
            u.prompt_tokens += pt
            u.completion_tokens += ct
            u.cost_usd += spec.cost(pt, ct)
            u.seconds += secs

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                k: {
                    "calls": v.calls,
                    "cached": v.cached,
                    "prompt_tokens": v.prompt_tokens,
                    "completion_tokens": v.completion_tokens,
                    "cost_usd": round(v.cost_usd, 5),
                    "seconds": round(v.seconds, 1),
                }
                for k, v in self.by_model.items()
            }


meter = Meter()
_last = threading.local()


def last_usage() -> dict[str, Any]:
    """Usage of the most recent chat() call on this thread (cached calls report stored usage)."""
    return dict(getattr(_last, "u", {}) or {})

_THINK = re.compile(r"<think>.*?</think>", re.S)


def strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str) -> Any:
    """Return the first well-formed JSON object/array in a model reply."""
    text = strip_reasoning(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = ([fence.group(1)] if fence else []) + [text]
    for cand in candidates:
        cand = cand.strip()
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            while start != -1:
                depth, in_str, esc = 0, False, False
                for i in range(start, len(cand)):
                    ch = cand[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == opener:
                        depth += 1
                    elif ch == closer:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(cand[start : i + 1])
                            except json.JSONDecodeError:
                                break
                start = cand.find(opener, start + 1)
    raise LLMError("model reply did not contain valid JSON")


class _Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, pt INT, ct INT, ts REAL)")
        self.conn.commit()
        self.lock = threading.Lock()

    def get(self, k: str) -> tuple[str, int, int] | None:
        with self.lock:
            row = self.conn.execute("SELECT v, pt, ct FROM cache WHERE k=?", (k,)).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def put(self, k: str, v: str, pt: int, ct: int) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?)", (k, v, pt, ct, time.time()))
            self.conn.commit()


_client = None
_cache: _Cache | None = None
_init_lock = threading.Lock()


def available() -> bool:
    return settings.has_llm


def _get():
    global _client, _cache
    with _init_lock:
        if _client is None:
            if not available():
                raise LLMError("No LLM configured (set NEBIUS_API_KEY or STUDYTWIN_ENV_FILE; or run offline).")
            from openai import OpenAI

            _client = OpenAI(api_key=settings.nebius_api_key, base_url=settings.nebius_base_url, timeout=120, max_retries=2)
            _cache = _Cache(settings.cache_dir / "llm_cache.sqlite")
    return _client, _cache


def chat(
    spec: ModelSpec,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    json_mode: bool = False,
    use_cache: bool = True,
    cache_salt: str = "",
) -> str:
    """One chat completion. Returns the text content (reasoning stripped)."""
    client, cache = _get()
    key_src = json.dumps([spec.id, messages, max_tokens, temperature, json_mode, cache_salt], sort_keys=True, ensure_ascii=False)
    key = hashlib.sha256(key_src.encode()).hexdigest()
    if use_cache and cache is not None:
        hit = cache.get(key)
        if hit:
            meter.add(spec, hit[1], hit[2], 0.0, cached=True)
            _last.u = {"model": spec.id, "prompt_tokens": hit[1], "completion_tokens": hit[2], "cached": True}
            return hit[0]
    kwargs: dict[str, Any] = dict(model=spec.id, messages=messages, max_tokens=max_tokens, temperature=temperature)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    delay = 2.0
    last: Exception | None = None
    for attempt in range(4):
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(**kwargs)
            break
        except Exception as e:  # noqa: BLE001 - surface provider errors uniformly
            last = e
            msg = str(e).lower()
            if json_mode and "response_format" in msg and "response_format" in kwargs:
                kwargs.pop("response_format")
                continue
            if "429" in msg or "rate" in msg or "timeout" in msg or "502" in msg or "503" in msg:
                time.sleep(delay)
                delay *= 2
                continue
            raise LLMError(f"{spec.id}: {e}") from e
    else:
        raise LLMError(f"{spec.id}: {last}")
    secs = time.perf_counter() - t0
    msg = resp.choices[0].message
    content = msg.content or getattr(msg, "reasoning_content", None) or ""
    content = strip_reasoning(content)
    pt = resp.usage.prompt_tokens if resp.usage else 0
    ct = resp.usage.completion_tokens if resp.usage else 0
    meter.add(spec, pt, ct, secs, cached=False)
    _last.u = {"model": spec.id, "prompt_tokens": pt, "completion_tokens": ct, "cached": False, "seconds": round(secs, 2)}
    if use_cache and cache is not None and content:
        cache.put(key, content, pt, ct)
    return content


def chat_json(
    spec: ModelSpec,
    system: str,
    user: str | list[dict[str, Any]],
    *,
    max_tokens: int = 1500,
    temperature: float = 0.2,
    cache_salt: str = "",
) -> Any:
    """Chat expecting a JSON object; retries once with a repair instruction."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    text = chat(spec, messages, max_tokens=max_tokens, temperature=temperature, json_mode=True, cache_salt=cache_salt)
    try:
        return extract_json(text)
    except LLMError:
        messages += [
            {"role": "assistant", "content": text[-3000:]},
            {"role": "user", "content": "That was not valid JSON. Reply with only the JSON object."},
        ]
        text = chat(spec, messages, max_tokens=max_tokens, temperature=0.0, json_mode=True, cache_salt=cache_salt)
        return extract_json(text)


def image_part(path: Path) -> dict[str, Any]:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
