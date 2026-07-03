import base64
import json
import re
import time

import httpx
from openai import OpenAI

from app.config import get_providers

# Fail fast if a provider's host is unreachable (so fallback to the next
# provider doesn't stall), but allow a generous read timeout — local models
# (Ollama on CPU, especially for vision) can legitimately take a while to
# generate a response.
_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)

# Groq (and others) return 429s with a "Please try again in 4.2s" hint —
# usually well under a minute. Waiting that out and retrying the same
# provider once is far more useful than immediately giving up on it: two API
# keys from the *same* account still share one token-per-minute budget, so
# switching "provider" doesn't actually dodge the limit — waiting does.
_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)
_MAX_RATE_LIMIT_WAIT = 30.0


class NoProviderConfiguredError(Exception):
    pass


class AllProvidersFailedError(Exception):
    def __init__(self, attempts: list[tuple[str, str]]):
        self.attempts = attempts
        details = "; ".join(f"{name}: {err}" for name, err in attempts)
        super().__init__(f"Todos os provedores de IA configurados falharam — {details}")


def enabled_providers() -> list[dict]:
    providers = [p for p in get_providers() if p.get("enabled", True)]
    if not providers:
        raise NoProviderConfiguredError(
            "Nenhum provedor de IA configurado. Adicione um em Configurações (Groq, Ollama local, ou outro compatível com a API da OpenAI)."
        )
    return providers


def _client_for(provider: dict) -> OpenAI:
    api_key = provider.get("api_key") or "not-needed"
    return OpenAI(api_key=api_key, base_url=provider["base_url"], timeout=_REQUEST_TIMEOUT, max_retries=0)


def image_to_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError("A resposta do modelo não contém um objeto JSON.")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("A resposta do modelo continha um JSON incompleto.")


def _rate_limit_wait_seconds(error_text: str) -> float | None:
    match = _RETRY_AFTER_RE.search(error_text)
    if not match:
        return None
    seconds = float(match.group(1))
    return seconds if seconds <= _MAX_RATE_LIMIT_WAIT else None


def _chat_json(client: OpenAI, model: str, messages: list, max_tokens: int, temperature: float) -> dict:
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=messages,
        )
        return _extract_json(response.choices[0].message.content)
    except Exception as exc:
        if _rate_limit_wait_seconds(str(exc)) is not None:
            # A genuine rate-limit error — let it propagate so the caller's
            # backoff logic handles it, instead of silently burning a second
            # request against the same exhausted quota.
            raise
        # Otherwise, assume response_format json_object just isn't supported
        # by this provider/model (common with local Ollama models) — retry
        # in plain mode and best-effort extract the JSON from the raw text.
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
        )
        return _extract_json(response.choices[0].message.content)


def _call_provider(provider: dict, model_key: str, messages: list, max_tokens: int, temperature: float) -> dict:
    client = _client_for(provider)
    model = provider[model_key]
    for attempt in range(2):
        try:
            return _chat_json(client, model, messages, max_tokens, temperature)
        except Exception as exc:  # noqa: BLE001
            wait = _rate_limit_wait_seconds(str(exc))
            if wait is not None and attempt == 0:
                time.sleep(wait + 0.5)
                continue
            raise


def ask_vision(system_prompt: str, user_text: str, screenshot_bytes: bytes) -> tuple[dict, str]:
    """Tries each enabled provider in order (fallback priority) until one
    answers successfully — e.g. if Groq hits its token-per-minute cap, the
    next configured provider (Ollama, another key...) is used instead."""
    providers = enabled_providers()
    data_url = image_to_data_url(screenshot_bytes)
    attempts: list[tuple[str, str]] = []

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    for provider in providers:
        try:
            result = _call_provider(provider, "vision_model", messages, max_tokens=1024, temperature=0.2)
            return result, provider["name"]
        except Exception as exc:  # noqa: BLE001
            attempts.append((provider["name"], str(exc)))
            continue

    raise AllProvidersFailedError(attempts)


def ask_text(system_prompt: str, user_text: str) -> tuple[dict, str]:
    providers = enabled_providers()
    attempts: list[tuple[str, str]] = []
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    for provider in providers:
        try:
            result = _call_provider(provider, "text_model", messages, max_tokens=2048, temperature=0.3)
            return result, provider["name"]
        except Exception as exc:  # noqa: BLE001
            attempts.append((provider["name"], str(exc)))
            continue

    raise AllProvidersFailedError(attempts)
