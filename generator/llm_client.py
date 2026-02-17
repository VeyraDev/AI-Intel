"""
LLM API client. API key must come from environment variables only.
Provider-specific env var names: MOONSHOT_API_KEY, DASHSCOPE_API_KEY, DEEPSEEK_API_KEY, QIANFAN_API_KEY.
429 Too Many Requests 时自动重试（指数退避）。
"""
import logging
import os
import time
from typing import Any

logger = logging.getLogger("ai_intel")

# 429/503 时重试：次数与基础等待秒数
LLM_RETRY_COUNT = 3
LLM_RETRY_BASE_SECONDS = 5

ENV_KEYS = {
    "moonshot": "MOONSHOT_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qianfan": "QIANFAN_API_KEY",
}


def get_api_key(provider: str) -> str | None:
    """Get API key from environment. Never read from config/file."""
    name = ENV_KEYS.get((provider or "").lower())
    if not name:
        return None
    return os.environ.get(name)


def chat_completion(
    provider: str,
    model_name: str,
    api_base: str,
    api_key: str | None,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> str:
    """Call OpenAI-compatible chat completion; return assistant text."""
    if not api_key:
        logger.warning("No API key in env for provider %s; skip LLM call", provider)
        return ""
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; skip LLM call")
        return ""

    url = f"{api_base.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error: Exception | None = None
    for attempt in range(LLM_RETRY_COUNT + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code in (429, 503):
                if attempt < LLM_RETRY_COUNT:
                    wait_sec = LLM_RETRY_BASE_SECONDS * (2 ** attempt)
                    logger.warning(
                        "LLM rate limit (%s), retry in %ds (%d/%d)",
                        r.status_code, wait_sec, attempt + 1, LLM_RETRY_COUNT,
                    )
                    time.sleep(wait_sec)
                    continue
                r.raise_for_status()
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                return (msg.get("content") or "").strip()
            return ""
        except requests.exceptions.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code in (429, 503) and attempt < LLM_RETRY_COUNT:
                wait_sec = LLM_RETRY_BASE_SECONDS * (2 ** attempt)
                logger.warning("LLM rate limit (%s), retry in %ds", e.response.status_code, wait_sec)
                time.sleep(wait_sec)
                continue
            logger.exception("LLM request failed: %s", e)
            return ""
        except Exception as e:
            last_error = e
            break
    logger.exception("LLM request failed: %s", last_error)
    return ""
