import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
REPORTS_DIR = DATA_DIR / "reports"
RUNS_DIR = DATA_DIR / "runs"
CONFIG_FILE = DATA_DIR / "config.json"

for directory in (DATA_DIR, SCREENSHOTS_DIR, REPORTS_DIR, RUNS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Presets shown in the "add provider" UI. Any OpenAI-compatible endpoint
# works here — these are just convenient starting points; the user can also
# pick "custom" and point at anything else (LM Studio, OpenRouter, vLLM...).
PROVIDER_PRESETS = {
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "vision_model": "qwen/qwen3.6-27b",
        "text_model": "openai/gpt-oss-120b",
        "needs_api_key": True,
    },
    "ollama": {
        "name": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "vision_model": "llama3.2-vision",
        "text_model": "llama3.1",
        "needs_api_key": False,
    },
    "custom": {
        "name": "Personalizado",
        "base_url": "",
        "vision_model": "",
        "text_model": "",
        "needs_api_key": True,
    },
}


def _read_config_file() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write_config_file(data: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _migrate_legacy_config(data: dict) -> dict:
    """Earlier versions stored a single Groq key/model pair directly in
    config.json (or only in the GROQ_API_KEY env var). Fold that into the
    new multi-provider list once, so existing setups keep working."""
    if "providers" in data:
        return data

    legacy_key = data.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")
    providers = []
    if legacy_key:
        providers.append(
            {
                "id": "groq",
                "name": "Groq",
                "base_url": PROVIDER_PRESETS["groq"]["base_url"],
                "api_key": legacy_key,
                "vision_model": data.get("vision_model") or os.getenv("GROQ_VISION_MODEL", PROVIDER_PRESETS["groq"]["vision_model"]),
                "text_model": data.get("text_model") or os.getenv("GROQ_TEXT_MODEL", PROVIDER_PRESETS["groq"]["text_model"]),
                "enabled": True,
            }
        )
    data = {"providers": providers}
    _write_config_file(data)
    return data


def get_providers() -> list[dict]:
    data = _migrate_legacy_config(_read_config_file())
    return data.get("providers", [])


def save_providers(providers: list[dict]) -> None:
    data = _read_config_file()
    data["providers"] = providers
    _write_config_file(data)


def create_provider(provider: dict) -> list[dict]:
    providers = get_providers()
    provider = dict(provider)
    provider["id"] = uuid.uuid4().hex[:8]
    provider.setdefault("api_key", "")
    provider.setdefault("enabled", True)
    providers.append(provider)
    save_providers(providers)
    return providers


def patch_provider(provider_id: str, patch: dict) -> list[dict]:
    providers = get_providers()
    for p in providers:
        if p["id"] == provider_id:
            p.update(patch)
            break
    save_providers(providers)
    return providers


def delete_provider(provider_id: str) -> list[dict]:
    providers = [p for p in get_providers() if p["id"] != provider_id]
    save_providers(providers)
    return providers


def reorder_providers(order: list[str]) -> list[dict]:
    providers = get_providers()
    by_id = {p["id"]: p for p in providers}
    reordered = [by_id[pid] for pid in order if pid in by_id]
    remaining = [p for p in providers if p["id"] not in order]
    reordered.extend(remaining)
    save_providers(reordered)
    return reordered


def is_configured() -> bool:
    return any(p.get("enabled", True) for p in get_providers())


DEFAULT_SMTP = {
    "host": "",
    "port": 587,
    "encryption": "starttls",  # starttls | ssl | none
    "username": "",
    "password": "",
    "from_email": "",
    "from_name": "QA Agent",
}


def get_smtp_settings() -> dict:
    data = _read_config_file()
    return {**DEFAULT_SMTP, **data.get("smtp", {})}


def save_smtp_settings(patch: dict) -> dict:
    data = _read_config_file()
    current = {**DEFAULT_SMTP, **data.get("smtp", {})}
    current.update(patch)
    data["smtp"] = current
    _write_config_file(data)
    return current


def is_smtp_configured() -> bool:
    smtp = get_smtp_settings()
    return bool(smtp.get("host") and smtp.get("from_email"))
