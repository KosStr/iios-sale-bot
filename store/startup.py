"""Startup checks — fail fast with readable logs before Fly restart-loops."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from telegram import Bot
from telegram.error import InvalidToken, TelegramError

from store.config import Config

logger = logging.getLogger(__name__)


def log_runtime_config(config: Config) -> None:
    webhook = config.webhook
    logger.info("Runtime configuration:")
    logger.info("  mode=%s", "webhook" if webhook.enabled else "polling")
    logger.info("  database_path=%s", config.database_path)
    logger.info("  currency=%s", config.currency)
    logger.info("  bot_token=%s", "set" if config.bot_token else "MISSING")
    if webhook.enabled:
        logger.info("  webhook_url=%s", webhook.url)
        logger.info("  webhook_port=%s", webhook.port)
        logger.info("  webhook_secret=%s", "set" if webhook.secret else "not set")
    logger.info("  fly_app=%s", os.getenv("FLY_APP_NAME", "(not set)"))
    logger.info("  fly_region=%s", os.getenv("FLY_REGION", "(not set)"))


def validate_bot_token(token: str) -> None:
    """Verify the token with Telegram before starting the webhook server."""

    async def _check() -> None:
        bot = Bot(token)
        try:
            me = await bot.get_me()
            logger.info("Telegram bot OK: @%s (%s)", me.username, me.id)
        except InvalidToken as err:
            raise RuntimeError(
                "BOT_TOKEN is invalid. Set a correct token: fly secrets set BOT_TOKEN=..."
            ) from err
        except TelegramError as err:
            raise RuntimeError(f"Could not reach Telegram API: {err}") from err
        finally:
            await bot.shutdown()

    asyncio.run(_check())


def validate_database_path(path: str) -> None:
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        raise RuntimeError(
            f"Database directory {parent!r} does not exist. "
            "On Fly.io create a volume in the same region as the app and mount it at /data. "
            "Example: fly volumes create store_data --size 1 --region fra"
        )
    if not os.access(parent, os.W_OK):
        raise RuntimeError(
            f"Database directory {parent!r} is not writable. "
            "Check the Fly volume mount (fly.toml [[mounts]] destination = '/data')."
        )


def fatal_startup(message: str, exc: BaseException | None = None) -> None:
    logger.error("STARTUP FAILED: %s", message)
    if exc:
        logger.exception(exc)
    sys.exit(1)
