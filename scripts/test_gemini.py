"""Send one small request to the configured Gemini 2.5 Flash model."""

import asyncio
import os
import sys
import time
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import litellm

from skyvern.config import settings
from skyvern.forge.sdk.api.llm.config_registry import LLMConfigRegistry


MODEL_KEY = settings.LLM_KEY

warnings.filterwarnings("ignore", category=UserWarning, message="Pydantic serializer warnings:.*")


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    if settings.GEMINI_API_KEY:
        message = message.replace(settings.GEMINI_API_KEY, "<redacted>")
    return f"{type(exc).__name__}: {message}"


async def main() -> int:
    if not settings.ENABLE_GEMINI:
        print("FAIL: ENABLE_GEMINI=false")
        return 2
    if not settings.GEMINI_API_KEY:
        print("FAIL: GEMINI_API_KEY is empty")
        return 2
    if not MODEL_KEY.startswith("GEMINI_"):
        print(f"FAIL: LLM_KEY must be a Gemini model, got {MODEL_KEY}")
        return 2
    if MODEL_KEY not in LLMConfigRegistry.get_model_names():
        print(f"FAIL: {MODEL_KEY} is not registered; check ENABLE_GEMINI")
        return 2

    config = LLMConfigRegistry.get_config(MODEL_KEY)
    started = time.perf_counter()
    try:
        response = await litellm.acompletion(
            model=config.model_name,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with OK only.",
                }
            ],
            max_completion_tokens=64,
            timeout=30,
            drop_params=True,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            print("FAIL: Gemini returned an empty response")
            return 1

        elapsed = time.perf_counter() - started
        print(f"OK: {MODEL_KEY} is available")
        print(f"model={config.model_name} elapsed={elapsed:.2f}s")
        print(f"response={content.strip()}")
        return 0
    except Exception as exc:
        print(f"FAIL: Gemini request failed: {_safe_error(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
