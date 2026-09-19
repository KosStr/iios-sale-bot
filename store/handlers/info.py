"""Store info: contacts and location.

All values are read from environment variables (see .env). The defaults below
are mock data so the bot works out of the box; override them in .env.

Rendered with HTML parse mode so values containing characters like "_"
(e.g. Telegram handles) don't break entity parsing.
"""

from __future__ import annotations

import os
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _instagram_links() -> str:
    """Return HTML links for the store's Instagram accounts, or ''."""
    handles = [
        _env("STORE_INSTAGRAM", "@iios_cv"),
        _env("STORE_INSTAGRAM2", "@iios_tehnika"),
    ]
    links = []
    for handle in handles:
        if not handle:
            continue
        user = handle.lstrip("@")
        links.append(
            f'<a href="https://instagram.com/{escape(user)}">@{escape(user)}</a>'
        )
    return " · ".join(links)


def _contacts_text() -> str:
    lines = ["📞 <b>Контакти</b>", ""]
    name = _env("STORE_NAME", "IIOS Store")
    phone = _env("STORE_PHONE", "+380 95 340 77 54")
    telegram = _env("STORE_TELEGRAM", "@iios_cv")
    instagram = _instagram_links()
    website = _env("STORE_WEBSITE", "https://iios.store")

    if name:
        lines.append(f"🏪 {escape(name)}")
    if phone:
        lines.append(f"☎️ Телефон: {escape(phone)}")
    if telegram:
        lines.append(f"💬 Telegram: {escape(telegram)}")
    if instagram:
        lines.append(f"📸 Instagram: {instagram}")
    if website:
        lines.append(f'🌐 Сайт: <a href="{escape(website)}">{escape(website)}</a>')
    return "\n".join(lines)


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        _contacts_text(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def show_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    address = _env("STORE_ADDRESS", "м. Чернівці, вул. Заньковецької")
    map_url = _env("STORE_MAP_URL", "https://maps.app.goo.gl/8AZcqV7XxU1495Ns6")

    lines = ["📍 <b>Локація</b>", "", escape(address)]
    if map_url:
        lines.append(f'🗺 <a href="{escape(map_url)}">Відкрити на мапі</a>')
    lines += ["", "Ми поряд — заходьте!"]

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )
