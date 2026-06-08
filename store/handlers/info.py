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


def _instagram_link() -> str:
    """Return an HTML link for the Instagram handle, or ''."""
    handle = _env("STORE_INSTAGRAM", "@iios.store")
    if not handle:
        return ""
    user = handle.lstrip("@")
    return f'<a href="https://instagram.com/{escape(user)}">@{escape(user)}</a>'


def _contacts_text() -> str:
    lines = ["📞 <b>Контакти</b>", ""]
    name = _env("STORE_NAME", "IIOS Store")
    phone = _env("STORE_PHONE", "+380 99 123 45 67")
    phone2 = _env("STORE_PHONE2", "+380 73 987 65 43")
    email = _env("STORE_EMAIL", "info@iios.store")
    telegram = _env("STORE_TELEGRAM", "@iios_cv")
    instagram = _instagram_link()
    website = _env("STORE_WEBSITE", "https://iios.store")
    hours = _env("STORE_HOURS", "Пн–Нд, 10:00–20:00")

    if name:
        lines.append(f"🏪 {escape(name)}")
    if phone:
        lines.append(f"☎️ Телефон: {escape(phone)}")
    if phone2:
        lines.append(f"📱 Додатковий: {escape(phone2)}")
    if email:
        lines.append(f"✉️ Email: {escape(email)}")
    if telegram:
        lines.append(f"💬 Telegram: {escape(telegram)}")
    if instagram:
        lines.append(f"📸 Instagram: {instagram}")
    if website:
        lines.append(f'🌐 Сайт: <a href="{escape(website)}">{escape(website)}</a>')
    if hours:
        lines.append(f"🕙 Графік роботи: {escape(hours)}")
    return "\n".join(lines)


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        _contacts_text(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def show_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    address = _env("STORE_ADDRESS", "м. Чернівці, вул. Головна, 1")
    latitude = float(_env("STORE_LATITUDE", "48.291839"))
    longitude = float(_env("STORE_LONGITUDE", "25.935355"))

    await update.message.reply_text(
        f"📍 <b>Локація</b>\n\n{escape(address)}\nМи поряд — заходьте!",
        parse_mode=ParseMode.HTML,
    )
    await update.message.reply_location(latitude=latitude, longitude=longitude)
