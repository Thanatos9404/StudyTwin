"""Runtime configuration.

Secrets are never stored in this repository. ``NEBIUS_API_KEY`` is read from the process
environment, from ``.env`` in the project root, or from the file named by
``STUDYTWIN_ENV_FILE`` (only that one key is read from it).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)


def _nebius_key() -> str:
    key = os.getenv("NEBIUS_API_KEY", "").strip()
    if key:
        return key
    extra = os.getenv("STUDYTWIN_ENV_FILE", "").strip()
    if extra and Path(extra).is_file():
        return (dotenv_values(extra).get("NEBIUS_API_KEY") or "").strip()
    return ""


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelSpec:
    id: str
    input_price: float  # USD per 1M input tokens (Nebius Token Factory public catalog, Oct 2026)
    output_price: float

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.input_price + completion_tokens * self.output_price) / 1e6


PRICES = {
    "Qwen/Qwen3-235B-A22B-Instruct-2507": (0.2, 0.6),
    "Qwen/Qwen3-30B-A3B-Instruct-2507": (0.1, 0.3),
    "openai/gpt-oss-120b": (0.15, 0.6),
    "deepseek-ai/DeepSeek-V4-Flash-0731": (0.14, 0.28),
    "google/gemma-3-27b-it": (0.1, 0.3),
    "zai-org/GLM-5.3-Flash": (0.15, 0.5),
    "deepseek-ai/DeepSeek-V4.1-Flash": (0.3, 1.2),
    "moonshotai/Kimi-K2.6": (0.5, 2.0),
}


def model(env: str, default: str) -> ModelSpec:
    mid = os.getenv(env, default).strip()
    ip, op = PRICES.get(mid, (0.0, 0.0))
    return ModelSpec(mid, ip, op)


@dataclass
class Settings:
    root: Path = ROOT
    workspace: Path = field(default_factory=lambda: Path(os.getenv("STUDYTWIN_WORKSPACE", str(ROOT / "data" / "workspace"))))
    nebius_api_key: str = field(default_factory=_nebius_key)
    nebius_base_url: str = field(
        default_factory=lambda: os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    )
    offline: bool = field(default_factory=lambda: _flag("STUDYTWIN_OFFLINE"))
    # Model roles. Each role can be overridden with an environment variable.
    # Tutor answers, grading and conversation signals: fast open-weight reasoning model.
    tutor_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_TUTOR", "openai/gpt-oss-120b"))
    fast_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_FAST", "openai/gpt-oss-120b"))
    # Question generation and verification use different model families (cross-model validation).
    generator_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_GENERATOR", "deepseek-ai/DeepSeek-V4-Flash-0731"))
    verifier_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_VERIFIER", "openai/gpt-oss-120b"))
    vision_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_VISION", "zai-org/GLM-5.3-Flash"))
    judge_model: ModelSpec = field(default_factory=lambda: model("STUDYTWIN_MODEL_JUDGE", "deepseek-ai/DeepSeek-V4-Flash-0731"))
    embedder: str = field(default_factory=lambda: os.getenv("STUDYTWIN_EMBEDDER", "BAAI/bge-small-en-v1.5"))
    whisper_model: str = field(default_factory=lambda: os.getenv("STUDYTWIN_WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("STUDYTWIN_WHISPER_DEVICE", "cpu"))
    # Context budget for the tutor prompt (tokens of retrieved evidence after LLMSlim).
    context_budget: int = field(default_factory=lambda: int(os.getenv("STUDYTWIN_CONTEXT_BUDGET", "1000")))
    use_llmslim: bool = field(default_factory=lambda: _flag("STUDYTWIN_USE_LLMSLIM", "1"))
    top_k: int = field(default_factory=lambda: int(os.getenv("STUDYTWIN_TOP_K", "8")))

    @property
    def has_llm(self) -> bool:
        return bool(self.nebius_api_key) and not self.offline

    @property
    def db_path(self) -> Path:
        return self.workspace / "studytwin.sqlite"

    @property
    def media_dir(self) -> Path:
        return self.workspace / "media"

    @property
    def cache_dir(self) -> Path:
        return self.workspace / "cache"

    @property
    def uploads_dir(self) -> Path:
        return self.workspace / "uploads"

    def ensure_dirs(self) -> None:
        for d in (self.workspace, self.media_dir, self.cache_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
