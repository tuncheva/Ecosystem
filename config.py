from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv
import os


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str


def _normalize_base_url(raw: str) -> str:
    """Normalize gateway base URL.

    Common failure mode: `.env` contains something like:
      https://chat.velocity.online/?model=...

    The OpenAI SDK expects an API root (scheme+host[+path]) without query params.
    We strip query/fragment and keep scheme+netloc+path.

    NOTE: Some gateways want `/v1` in the base URL, others auto-append.
    We keep the path provided and leave the `/v1` decision to runtime diagnostics.
    """
    parsed = urlparse(raw.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"VELOCITY_BASE_URL must be a full URL, got: {raw!r}")

    path = parsed.path or ""
    # Drop trailing slash for consistency.
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
    return normalized


def load_settings() -> Settings:
    load_dotenv(override=False)

    api_key = os.getenv("VELOCITY_API_KEY", "").strip()
    base_url_raw = os.getenv("VELOCITY_BASE_URL", "").strip()
    model = os.getenv("VELOCITY_MODEL", "").strip() or "gpt-5.2"

    if not api_key:
        raise RuntimeError("Missing VELOCITY_API_KEY in environment/.env")

    if not base_url_raw:
        raise RuntimeError("Missing VELOCITY_BASE_URL in environment/.env")

    base_url = _normalize_base_url(base_url_raw)

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
