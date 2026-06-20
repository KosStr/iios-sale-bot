"""Admin-only flow to add a product with an optional photo (/add)."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from store.data.products import Product
from store.db import products_repo
from store.services.catalog_filter import (
    CATEGORIES,
    CATEGORY_LABELS,
    SUBCATEGORIES,
    format_price,
    subcategory_options,
)
from store.services.images import r2_write_enabled, upload_image
from store.utils.admin import is_admin

logger = logging.getLogger(__name__)

NAME, PRICE, CATEGORY, SUBCATEGORY, STOCK, PHOTO, CONFIRM = range(7)

_CANCEL = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")]]
)


def _draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("admin_add", {})


def _clear_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_add", None)


def _category_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for key, label in CATEGORIES:
        if key == "all":
            continue
        row.append(InlineKeyboardButton(label, callback_data=f"adm:cat:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")])
    return InlineKeyboardMarkup(rows)


def _subcategory_keyboard(category: str) -> InlineKeyboardMarkup:
    options = [
        (key, label)
        for key, label in subcategory_options(category)
        if key != "all"
    ]
    rows = [
        [InlineKeyboardButton(label, callback_data=f"adm:sub:{key}")]
        for key, label in options
    ]
    rows.append([InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")])
    return InlineKeyboardMarkup(rows)


def _preview(draft: dict) -> str:
    cat = CATEGORY_LABELS.get(draft.get("category", ""), draft.get("category", "?"))
    sub = draft.get("subcategory") or "—"
    photo = "так" if draft.get("image") else "ні"
    return "\n".join(
        [
            "📋 *Перевірте товар:*",
            "",
            f"Назва: *{draft['name']}*",
            f"ID: `{draft['id']}`",
            f"Ціна: *{format_price(draft['price'], 'USD')}*",
            f"Категорія: {cat}",
            f"Підкатегорія: {sub}",
            f"На складі: {draft['stock']}",
            f"Фото: {photo}",
        ]
    )


def _build_product(draft: dict) -> Product:
    return Product(
        id=draft["id"],
        brand=draft.get("brand", "—"),
        name=draft["name"],
        price=draft["price"],
        storage="—",
        color="—",
        stock=draft["stock"],
        description=draft["name"],
        category=draft["category"],
        subcategory=draft.get("subcategory", ""),
        image=draft.get("image", ""),
    )


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update, context):
        await update.message.reply_text("Ця команда лише для адміністраторів.")
        return ConversationHandler.END

    _clear_draft(context)
    await update.message.reply_text(
        "➕ *Додати товар*\n\nНадішліть *назву* товару.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Назва занадто коротка. Спробуйте ще раз.")
        return NAME

    draft = _draft(context)
    draft["name"] = name
    draft["id"] = products_repo.make_unique_id(name)
    draft["brand"] = name.split()[0] if name.split() else "—"

    await update.message.reply_text(
        f"Ціна в *USD* (лише число, напр. `49` або `999`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return PRICE


async def collect_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip().replace(",", ".")
    try:
        price = int(float(raw))
    except ValueError:
        await update.message.reply_text("Введіть число, наприклад: 49")
        return PRICE

    if price <= 0:
        await update.message.reply_text("Ціна має бути більше нуля.")
        return PRICE

    _draft(context)["price"] = price
    await update.message.reply_text(
        "Оберіть *категорію*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_category_keyboard(),
    )
    return CATEGORY


async def pick_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.split(":", 2)[2]
    draft = _draft(context)
    draft["category"] = category
    draft["subcategory"] = ""

    if category in SUBCATEGORIES:
        await query.edit_message_text(
            "Оберіть *підкатегорію*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_subcategory_keyboard(category),
        )
        return SUBCATEGORY

    await query.edit_message_text(
        "Скільки одиниць *на складі*? (число)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return STOCK


async def pick_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _draft(context)["subcategory"] = query.data.split(":", 2)[2]
    await query.edit_message_text(
        "Скільки одиниць *на складі*? (число)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return STOCK


async def collect_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text("Введіть ціле число, наприклад: 5")
        return STOCK

    stock = int(raw)
    if stock < 0:
        await update.message.reply_text("Кількість не може бути від'ємною.")
        return STOCK

    _draft(context)["stock"] = stock
    hint = (
        "Надішліть *фото* товару"
        if r2_write_enabled()
        else "Надішліть *фото* (потрібні R2 ключі для завантаження) або /skip"
    )
    await update.message.reply_text(
        f"{hint}\n\nАбо /skip — без фото.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return PHOTO


async def collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _draft(context)
    photo = update.message.photo[-1]
    image_key = f"{draft['id']}.jpg"

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception:  # noqa: BLE001
        logger.exception("Failed to download photo from Telegram")
        await update.message.reply_text(
            "Не вдалося завантажити фото. Спробуйте ще раз або /skip."
        )
        return PHOTO

    if upload_image(image_key, image_bytes):
        draft["image"] = image_key
    else:
        await update.message.reply_text(
            "⚠️ Фото не завантажено в R2 (перевірте R2_* secrets). "
            "Товар можна зберегти без фото — /skip"
        )
        return PHOTO

    await _show_confirm(update, context)
    return CONFIRM


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _show_confirm(update, context)
    return CONFIRM


async def _show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    draft = _draft(context)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Зберегти", callback_data="adm:save")],
            [InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")],
        ]
    )
    await update.message.reply_text(
        _preview(draft),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def save_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    draft = _draft(context)
    product = _build_product(draft)

    try:
        products_repo.insert(product)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to insert product %s", product.id)
        await query.edit_message_text("❌ Не вдалося зберегти товар у базу.")
        _clear_draft(context)
        return ConversationHandler.END

    _clear_draft(context)
    await query.edit_message_text(
        "\n".join(
            [
                "✅ *Товар додано!*",
                "",
                f"*{product.name}*",
                f"ID: `{product.id}`",
                f"Ціна: {format_price(product.price, 'USD')}",
                "",
                "Вже видно в каталозі для покупців.",
            ]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("Скасовано.")
        await query.edit_message_text("Додавання товару скасовано.")
    else:
        await update.message.reply_text("Додавання товару скасовано.")
    _clear_draft(context)
    return ConversationHandler.END


def build_admin_add_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("add", start_add)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_price)],
            CATEGORY: [CallbackQueryHandler(pick_category, pattern=r"^adm:cat:")],
            SUBCATEGORY: [CallbackQueryHandler(pick_subcategory, pattern=r"^adm:sub:")],
            STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_stock)],
            PHOTO: [
                MessageHandler(filters.PHOTO, collect_photo),
                CommandHandler("skip", skip_photo),
            ],
            CONFIRM: [
                CallbackQueryHandler(save_product, pattern=r"^adm:save$"),
                CallbackQueryHandler(cancel_add, pattern=r"^adm:cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add, pattern=r"^adm:cancel$"),
            CommandHandler("cancel", cancel_add),
        ],
        allow_reentry=True,
    )
