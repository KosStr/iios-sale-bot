"""/rate — the USD→UAH rate for the website and Google Shopping.

``/rate`` shows the current rate; ``/rate 41.5`` saves a new one. Products
priced only in dollars appear on i-ios.store and in the Google feed in
hryvnias by this rate. The bot keeps showing prices as they were entered.
"""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

from store.db import products_repo
from store.handlers.admin.products import admin_only
from store.services import exchange_rate
from store.services.hot_deals import publish_hot_deals
from store.services.site_catalog import request_catalog_refresh

_USAGE = "Щоб змінити, надішліть, наприклад: <code>/rate 41.5</code>"


def _usd_only_count() -> int:
    return sum(
        1 for p in products_repo.fetch_all() if p.stock > 0 and exchange_rate.is_usd_only(p)
    )


@admin_only
async def cmd_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args or [])
    if not text:
        rate = exchange_rate.get_rate()
        count = _usd_only_count()
        if rate is None:
            current = "💱 Курс долара ще не задано."
            effect = (
                f"Товари лише з ціною в $ ({count}) показуються на сайті в доларах "
                "і не потрапляють у Google Покупки."
            )
        else:
            current = f"💱 Курс: <b>1 $ = {exchange_rate.format_rate(rate)} грн</b>"
            effect = (
                f"За ним на сайті й у Google Покупках рахуються ціни {count} "
                "товар(-ів), у яких ціна лише в $."
            )
        await update.message.reply_text(
            f"{current}\n{effect}\n\n{_USAGE}", parse_mode=ParseMode.HTML
        )
        return

    rate = exchange_rate.parse_rate(text)
    if rate is None:
        await update.message.reply_text(
            "Не схоже на курс долара. Надішліть число від "
            f"{exchange_rate.MIN_RATE:.0f} до {exchange_rate.MAX_RATE:.0f}, "
            "наприклад: <code>/rate 41.5</code>",
            parse_mode=ParseMode.HTML,
        )
        return

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


def build_admin_rate_handlers() -> list:
    return [CommandHandler("rate", cmd_rate)]
