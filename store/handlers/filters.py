"""Filter screen shown after tapping «Каталог» or «Забронювати».

Lets the user pick a category, currency (UAH/USD) and price range, then
renders the matching products as a catalog list or a booking list.
"""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.keyboards import (
    booking_results_keyboard,
    catalog_results_keyboard,
    filter_keyboard,
)
from store.services.catalog_filter import (
    PRICE_RANGES,
    filter_products,
    filter_summary,
    get_filter,
)

_FILTER_TITLE = "🔍 *Фільтр товарів*"


def _filter_text(flt: dict) -> str:
    return f"{_FILTER_TITLE}\n\n{filter_summary(flt)}\n\nОберіть параметри та натисніть «Показати товари»."


async def open_filter_for_catalog(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    flt = get_filter(context)
    flt["mode"] = "catalog"
    await _send_filter(update, flt)


async def open_filter_for_booking(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    flt = get_filter(context)
    flt["mode"] = "booking"
    await _send_filter(update, flt)


async def _send_filter(update: Update, flt: dict) -> None:
    text = _filter_text(flt)
    keyboard = filter_keyboard(flt)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


async def reopen_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_filter(update, get_filter(context))


async def set_filter_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle flt:cat:* / flt:cur:* / flt:price:* toggles and re-render."""
    query = update.callback_query
    _, field, value = query.data.split(":", 2)
    flt = get_filter(context)

    if field == "cat":
        flt["category"] = value
    elif field == "cur":
        flt["currency"] = value
        # Price-range keys are shared across currencies, but reset to be safe.
        valid_keys = {key for key, *_ in PRICE_RANGES[value]}
        if flt.get("price") not in valid_keys:
            flt["price"] = "any"
    elif field == "price":
        flt["price"] = value

    await query.answer()
    await query.edit_message_text(
        _filter_text(flt),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=filter_keyboard(flt),
    )


async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    flt = get_filter(context)
    products = filter_products(flt)
    currency = flt.get("currency", "UAH")

    if not products:
        await query.edit_message_text(
            "😕 За вашим фільтром нічого не знайдено.\nСпробуйте змінити параметри.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=filter_keyboard(flt),
        )
        return

    if flt.get("mode") == "booking":
        text = "📅 *Оберіть модель для бронювання:*"
        keyboard = booking_results_keyboard(products, currency)
    else:
        text = f"🛍 *Знайдено товарів: {len(products)}*\n\nОберіть товар, щоб переглянути деталі:"
        keyboard = catalog_results_keyboard(products, currency)

    await query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
