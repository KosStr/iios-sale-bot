"""Static store info: contacts and location.

Edit the constants below to match your real store details.
"""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# --- Store details (edit these) ----------------------------------------------
STORE_NAME = "IIOS Store"
STORE_PHONE = "+380 99 123 45 67"
STORE_EMAIL = "info@iios.store"
STORE_TELEGRAM = "@iios_cv"
STORE_HOURS = "Пн–Нд, 10:00–20:00"

STORE_ADDRESS = "м. Чернівці, вул. Головна, 1"
STORE_LATITUDE = 48.291839
STORE_LONGITUDE = 25.935355
# -----------------------------------------------------------------------------

_CONTACTS_TEXT = "\n".join(
    [
        "📞 *Контакти*",
        "",
        f"🏪 {STORE_NAME}",
        f"☎️ Телефон: {STORE_PHONE}",
        f"✉️ Email: {STORE_EMAIL}",
        f"💬 Telegram: {STORE_TELEGRAM}",
        f"🕙 Графік роботи: {STORE_HOURS}",
    ]
)


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_CONTACTS_TEXT, parse_mode=ParseMode.MARKDOWN)


async def show_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"📍 *Локація*\n\n{STORE_ADDRESS}\nМи поряд — заходьте!",
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_location(
        latitude=STORE_LATITUDE, longitude=STORE_LONGITUDE
    )
