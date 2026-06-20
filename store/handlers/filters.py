"""Filter screen shown after tapping «Каталог».

Lets the user pick a category, subcategory, currency (UAH/USD) and price range,
then renders the matching products as a catalog list.
"""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.keyboards import (
    catalog_results_keyboard,
    filter_keyboard,
    group_variants_keyboard,
)
from store.services.catalog_filter import (
    PRICE_RANGES,
    filter_products,
    filter_summary,
    get_filter,
)
from store.services.grouping import build_groups, find_group
from store.utils.tg import edit_or_resend

_FILTER_TITLE = "🔍 *Фільтр товарів*"


def _filter_text(flt: dict) -> str:
    return f"{_FILTER_TITLE}\n\n{filter_summary(flt)}\n\nОберіть параметри та натисніть «Показати товари»."


async def open_filter_for_catalog(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await _send_filter(update, get_filter(context))


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
    """Handle flt:cat/sub/cur/price toggles and re-render."""
    query = update.callback_query
    _, field, value = query.data.split(":", 2)
    flt = get_filter(context)

    if field == "cat":
        flt["category"] = value
        flt["subcategory"] = "all"
    elif field == "sub":
        flt["subcategory"] = value
    elif field == "cur":
        flt["currency"] = value
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

    groups = build_groups(products)
    text = f"🛍 *Знайдено моделей: {len(groups)}*\n\nОберіть модель, щоб переглянути деталі:"
    keyboard = catalog_results_keyboard(groups, currency)

    await query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )


async def show_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Expand a multi-variant model into its variant list."""
    query = update.callback_query
    flt = get_filter(context)
    currency = flt.get("currency", "UAH")
    key = query.data.split(":", 1)[1]
    group = find_group(key, filter_products(flt))

    if group is None:
        await show_results(update, context)
        return

    text = f"📦 *{group.label}*\n\nОберіть варіант:"
    await edit_or_resend(
        update, context, text, group_variants_keyboard(group, currency)
    )
