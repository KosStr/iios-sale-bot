"""Entry point: `python -m store`."""

from __future__ import annotations

import logging
import sys

from telegram import BotCommand
from telegram.ext import Application

from store.bot import create_application
from store.config import Config, load_config
from store.db import close_pool, init_database
from store.startup import (
    fatal_startup,
    log_runtime_config,
    validate_bot_token,
    validate_database_path,
)

logger = logging.getLogger(__name__)

ALLOWED_UPDATES = ["message", "callback_query"]


async def _set_commands(app: Application) -> None:
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Головне меню"),
                BotCommand("catalog", "Переглянути телефони"),
                BotCommand("cart", "Переглянути кошик"),
                BotCommand("help", "Як користуватися ботом"),
            ]
        )
    except Exception as err:  # noqa: BLE001 - bot can still run without menu commands
        logger.error("Could not register bot commands (non-fatal): %s", err)


def _run_webhook(app: Application, config: Config) -> None:
    webhook = config.webhook
    url_path = webhook.path.lstrip("/")
    logger.info(
        "Starting webhook on %s:%s/%s -> %s",
        webhook.listen,
        webhook.port,
        url_path,
        webhook.url,
    )
    app.run_webhook(
        listen=webhook.listen,
        port=webhook.port,
        url_path=url_path,
        webhook_url=webhook.url,
        secret_token=webhook.secret,
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=True,
    )


def _run_polling(app: Application) -> None:
    logger.info("Starting long polling (local/dev mode)")
    app.run_polling(
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=False,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )

    try:
        config = load_config()
        log_runtime_config(config)
        validate_bot_token(config.bot_token)
        validate_database_path(config.database_path)
        init_database(config.database_path)

        app = create_application(config)
        app.post_init = _set_commands

        logger.info("PhoneStore bot is starting...")
        if config.webhook.enabled:
            _run_webhook(app, config)
        else:
            _run_polling(app)
    except RuntimeError as err:
        fatal_startup(str(err), err)
    except Exception as err:  # noqa: BLE001
        fatal_startup("Unexpected error during startup", err)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
