"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urljoin

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_path(path: str) -> str:
    path = path.strip() or "/webhook"
    return path if path.startswith("/") else f"/{path}"


def _build_webhook_url(path: str) -> str | None:
    explicit = os.getenv("WEBHOOK_URL", "").strip()
    if explicit:
        return explicit

    fly_app = os.getenv("FLY_APP_NAME", "").strip()
    if fly_app:
        base = f"https://{fly_app}.fly.dev"
        return urljoin(base + "/", path.lstrip("/"))
    return None


@dataclass(frozen=True)
class WebhookConfig:
    enabled: bool
    url: str | None
    path: str
    secret: str | None
    port: int
    listen: str


@dataclass(frozen=True)
class Config:
    bot_token: str
    currency: str
    database_path: str
    webhook: WebhookConfig
    admin_chat_ids: list[str] = field(default_factory=list)


def _load_webhook_config() -> WebhookConfig:
    path = _normalize_path(os.getenv("WEBHOOK_PATH", "/webhook"))
    url = _build_webhook_url(path)
    enabled = _env_bool("USE_WEBHOOK", default=bool(url))

    if enabled and not url:
        raise RuntimeError(
            "Webhook mode enabled but WEBHOOK_URL is missing. "
            "Set WEBHOOK_URL or deploy on Fly.io (FLY_APP_NAME is set automatically)."
        )

    return WebhookConfig(
        enabled=enabled,
        url=url,
        path=path,
        secret=os.getenv("WEBHOOK_SECRET", "").strip() or None,
        port=int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080"))),
        listen=os.getenv("WEBHOOK_LISTEN", "0.0.0.0").strip() or "0.0.0.0",
    )


def load_config() -> Config:
    raw_admins = os.getenv("ADMIN_CHAT_IDS", "")
    admin_ids = [chat_id.strip() for chat_id in raw_admins.split(",") if chat_id.strip()]

    return Config(
        bot_token=_require("BOT_TOKEN"),
        currency=os.getenv("CURRENCY", "UAH"),
        database_path=os.getenv("DATABASE_PATH", "data/store.db"),
        webhook=_load_webhook_config(),
        admin_chat_ids=admin_ids,
    )
