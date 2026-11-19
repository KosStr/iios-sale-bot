"""/rate — the USD→UAH rate for the website and Google Shopping.

``/rate 41.5`` saves a new rate in one message. ``/rate`` alone shows the
current rate and then waits up to RATE_WAIT_SECONDS for the number as the
next message (``41.5``, ``41,50``, ``41.5 грн``); ``/cancel`` stops waiting.
Only number-like messages are taken while waiting, so menu buttons and
other text keep working. Products priced only in dollars appear on
i-ios.store and in the Google feed in hryvnias by this rate. The bot keeps
showing prices as they were entered.
"""

from __future__ import annotations

import re
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from store.db import products_repo
from store.handlers.admin.products import admin_only
from store.services import exchange_rate
from store.services.hot_deals import publish_hot_deals
from store.services.site_catalog import request_catalog_refresh

WAIT_RATE = 0

# The bot has no job queue (so no conversation_timeout): a number sent
# later than this after /rate is not taken as the rate.
RATE_WAIT_SECONDS = 600

_WAIT_KEY = "rate_wait_started"

# "41.5", "41,50", "41.5 грн", "₴41.5"; anything else falls through to the
# bot's other handlers.
_NUMBER_RE = re.compile(r"^\s*₴?\s*\d{1,3}(?:[.,]\d{1,4})?\s*(?:грн\.?|uah|₴)?\s*$", re.IGNORECASE)

_ASK = "Надішліть новий курс числом, наприклад <code>41.5</code> (або /cancel)."


def _usd_only_count() -> int:
    return sum(
        1 for p in products_repo.fetch_all() if p.stock > 0 and exchange_rate.is_usd_only(p)
    )


def _status_text() -> str:
    rate = exchange_rate.get_rate()
    count = _usd_only_count()
    if rate is None:
        return (
            "💱 Курс долара ще не задано.\n"
            f"Товари лише з ціною в $ ({count}) показуються на сайті в доларах "
            "і не потрапляють у Google Покупки."
        )
    return (
        f"💱 Курс: <b>1 $ = {exchange_rate.format_rate(rate)} грн</b>\n"
        f"За ним на сайті й у Google Покупках рахуються ціни {count} "
        "товар(-ів), у яких ціна лише в $."
    )


def _invalid_text() -> str:
    return (
        "Не схоже на курс долара. Надішліть число від "
        f"{exchange_rate.MIN_RATE:.0f} до {exchange_rate.MAX_RATE:.0f}, "
        "наприклад <code>41.5</code> (або /cancel)."
    )


async def _save(update: Update, rate: float) -> None:
    exchange_rate.set_rate(rate)
    request_catalog_refresh()
    landing_ok = await publish_hot_deals()
    count = _usd_only_count()
    lines = [
        f"✅ Курс збережено: <b>1 $ = {exchange_rate.format_rate(rate)} грн</b>",
        f"Ціни {count} товар(-ів), у яких ціна лише в $, перераховано "
        f"(округлення до {exchange_rate.ROUND_TO} грн).",
        "Сайт і Google-фід оновляться протягом ~10 хвилин. "
        "Ціни в боті не змінюються.",
    ]
    if not landing_ok:
        lines.append("⚠️ Не вдалося оновити гарячі пропозиції на лендінгу (R2).")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@admin_only
async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = " ".join(context.args or [])
    if text:
        rate = exchange_rate.parse_rate(text)
        if rate is None:
            await update.message.reply_text(_invalid_text(), parse_mode=ParseMode.HTML)
            context.user_data[_WAIT_KEY] = time.monotonic()
            return WAIT_RATE
        await _save(update, rate)
        context.user_data.pop(_WAIT_KEY, None)
        return ConversationHandler.END

    await update.message.reply_text(
        f"{_status_text()}\n\n{_ASK}", parse_mode=ParseMode.HTML
    )
    context.user_data[_WAIT_KEY] = time.monotonic()
    return WAIT_RATE


@admin_only
async def receive_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    started = context.user_data.pop(_WAIT_KEY, None)
    if started is None or time.monotonic() - started > RATE_WAIT_SECONDS:
        await update.message.reply_text(
            "Щоб змінити курс, надішліть <code>/rate 41.5</code> "
            "(або /rate, а потім число).",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    rate = exchange_rate.parse_rate(update.message.text)
    if rate is None:
        await update.message.reply_text(_invalid_text(), parse_mode=ParseMode.HTML)
        context.user_data[_WAIT_KEY] = started
        return WAIT_RATE
    await _save(update, rate)
    return ConversationHandler.END


async def cancel_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_WAIT_KEY, None)
    await update.message.reply_text("Курс не змінено.")
    return ConversationHandler.END


def build_admin_rate_handlers() -> list:
    return [
        ConversationHandler(
            entry_points=[CommandHandler("rate", cmd_rate)],
            states={
                WAIT_RATE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND & filters.Regex(_NUMBER_RE),
                        receive_rate,
                    ),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_rate)],
            allow_reentry=True,
        )
    ]
