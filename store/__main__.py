"""Entry point: `python -m store`."""

from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import Application

from store.bot import create_application
from store.config import load_config


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Головне меню"),
            BotCommand("catalog", "Переглянути телефони"),
            BotCommand("cart", "Переглянути кошик"),
            BotCommand("help", "Як користуватися ботом"),
        ]
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = load_config()
    app = create_application(config)
    app.post_init = _set_commands

    logging.getLogger(__name__).info(
        "PhoneStore bot is starting... Press Ctrl+C to stop."
    )
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
