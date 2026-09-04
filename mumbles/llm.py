"""Optional LLM rewriting for modes that ask for it.

Kept dependency-free on purpose: plain urllib against either the Anthropic
API or a local Ollama server. A mode with llm="none" never touches this
module, so the default install is fully offline.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("content-type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise LLMError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"could not reach {url}: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"bad response from {url}: {exc}") from exc


def anthropic_key() -> Optional[str]:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def rewrite_anthropic(text: str, prompt: str, model: str,
                      temperature: float = 0.2, timeout: float = 30.0) -> str:
    key = anthropic_key()
    if not key:
        raise LLMError(
            "ANTHROPIC_API_KEY is not set. Export it, or switch to a mode with "
            "llm=\"none\" (mumbles mode clean) to stay fully offline."
        )
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": prompt,
        "messages": [{"role": "user", "content": text}],
    }
    result = _post_json(
        ANTHROPIC_URL,
        payload,
        {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
        timeout,
    )
    blocks = result.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    joined = "".join(parts).strip()
    if not joined:
        raise LLMError("the model returned no text")
    return joined


def rewrite_ollama(text: str, prompt: str, model: str, host: str,
                   temperature: float = 0.2, timeout: float = 30.0) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
    }
    result = _post_json(host.rstrip("/") + "/api/chat", payload, {}, timeout)
    content = ((result.get("message") or {}).get("content") or "").strip()
    if not content:
        raise LLMError("ollama returned no text")
    return content


def rewrite(text: str, mode, cfg) -> str:
    """Apply a mode's LLM step. Returns the input unchanged if it has none."""
    if not text.strip() or not mode.uses_llm or not mode.prompt:
        return text
    if mode.llm == "anthropic":
        return rewrite_anthropic(
            text, mode.prompt, mode.model or cfg.anthropic_model,
            mode.temperature, cfg.llm_timeout,
        )
    if mode.llm == "ollama":
        return rewrite_ollama(
            text, mode.prompt, mode.model or cfg.ollama_model, cfg.ollama_host,
            mode.temperature, cfg.llm_timeout,
        )
    raise LLMError(f"unknown llm provider {mode.llm!r}")
