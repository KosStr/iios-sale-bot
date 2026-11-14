"""Admin-only flow to add a product with an optional photo (/add)."""

from __future__ import annotations

import asyncio
import logging
import re
from html import escape

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

from store.models.product import Product
from store.db import products_repo
from store.handlers.keyboards import BTN_ADMIN_ADD
from store.services.catalog_filter import (
    CATEGORIES,
    CATEGORY_LABELS,
    SUBCATEGORIES,
    subcategory_options,
)
from store.services.channel_sync import post_product
from store.services.grouping import fits_group_key
from store.services.images import r2_write_enabled, upload_image
from store.utils.admin import is_admin
from store.utils.tg import photo_file_id

logger = logging.getLogger(__name__)

# ── State constants (order = wizard step order) ──────────────────────────────
CATEGORY, SUBCATEGORY, NAME, PRODUCT_ID, GROUP, DESCRIPTION, PRICE_USD, PRICE_UAH, WARRANTY, BRAND, STORAGE, COLOR, STOCK, CHANNEL, PHOTO, CONFIRM = range(16)

# Existing models offered as buttons on the GROUP step.
_GROUP_CHOICE_LIMIT = 8

_CANCEL = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")]]
)


def _skip_keyboard(label: str, callback_data: str) -> InlineKeyboardMarkup:
    """A step's skip button above the shared cancel button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=callback_data)], *_CANCEL.inline_keyboard]
    )

_PHOTO_KEYBOARD = _skip_keyboard("⏭ Пропустити (без фото)", "adm:skip_photo")

_ID_SKIP = _skip_keyboard("🎲 Згенерувати автоматично", "adm:gen_id")

_STORAGE_SKIP = _skip_keyboard("⏭ Пропустити (—)", "adm:skip_storage")

_CHANNEL_SKIP = _skip_keyboard("⏭ Пропустити (без посилання)", "adm:skip_channel")

_DESCRIPTION_SKIP = _skip_keyboard("⏭ Пропустити", "adm:skip_desc")

_BRAND_SKIP = _skip_keyboard("⏭ Пропустити (—)", "adm:skip_brand")

_COLOR_SKIP = _skip_keyboard("⏭ Пропустити (—)", "adm:skip_color")

_STOCK_SKIP = _skip_keyboard("⏭ Пропустити (0)", "adm:skip_stock")

_PRICE_USD_SKIP = _skip_keyboard("⏭ Без ціни в USD", "adm:skip_price_usd")

_PRICE_UAH_SKIP = _skip_keyboard("⏭ Без ціни в UAH", "adm:skip_price_uah")

_WARRANTY_SKIP = _skip_keyboard("⏭ Пропустити (без гарантії)", "adm:skip_warranty")

_CHANNEL_URL_RE = re.compile(
    r"^https?://(?:t\.me|telegram\.me)/[\w+/.-]+$",
    re.IGNORECASE,
)


def _draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("admin_add", {})


def _clear_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_add", None)


async def _prompt(update: Update, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Show the next wizard step: edit the message after a button tap, else reply."""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


def _category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"adm:cat:{key}")
        for key, label in CATEGORIES if key != "all"
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
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
    rows.append(
        [InlineKeyboardButton("📦 Без підкатегорії", callback_data="adm:sub_none")]
    )
    rows.append([InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")])
    return InlineKeyboardMarkup(rows)


def _group_keyboard(draft: dict) -> InlineKeyboardMarkup:
    """Offer existing models to join, or a new one named after this product."""
    rows = [
        [InlineKeyboardButton(f"📦 {label}", callback_data=f"adm:grp:{index}")]
        for index, label in enumerate(draft.get("group_choices", []))
    ]
    rows.append(
        [
            InlineKeyboardButton(
                f"🆕 Окрема модель «{draft['name'][:24]}»",
                callback_data="adm:grp_new",
            )
        ]
    )
    rows.append([InlineKeyboardButton("✖️ Скасувати", callback_data="adm:cancel")])
    return InlineKeyboardMarkup(rows)


def _storage_hint(category: str) -> str:
    """Return a category-appropriate label/hint for the storage field."""
    hints = {
        "phone": "Обсяг пам'яті (напр. `128GB`, `256GB`)",
        "ipad": "Обсяг пам'яті (напр. `128GB`, `256GB`)",
        "laptop": "Конфігурація (напр. `16GB / 256GB`)",
        "watch": "Розмір корпусу (напр. `45mm`, `49mm`)",
        "headphones": "Характеристика (напр. `ANC`)",
        "accessories": "Специфікація (напр. `20 000 mAh`)",
    }
    return hints.get(category, "Специфікація")


def _price_preview(draft: dict) -> str:
    usd = draft.get("price", 0)
    uah = draft.get("price_uah")
    if usd and uah:
        return f"{uah} грн / ${usd}"
    if uah:
        return f"{uah} грн"
    if usd:
        return f"${usd}"
    return "—"


def _preview(draft: dict) -> str:
    cat = CATEGORY_LABELS.get(draft.get("category", ""), draft.get("category", "?"))
    sub = draft.get("subcategory") or "—"
    photo = "так" if draft.get("image") else "ні"
    channel = draft.get("channel_post_url") or "—"
    return "\n".join(
        [
            "📋 <b>Перевірте товар:</b>",
            "",
            f"Назва: <b>{escape(draft['name'])}</b>",
            f"ID: <code>{escape(draft['id'])}</code>",
            f"Модель: {escape(draft.get('group') or '—')}",
            f"Опис: {escape(draft.get('description', '—'))}",
            f"Стан: {escape(draft.get('brand', '—'))}",
            f"Специфікація: {escape(draft.get('storage', '—'))}",
            f"Колір: {escape(draft.get('color', '—'))}",
            f"Ціна: <b>{escape(_price_preview(draft))}</b>",
            f"Гарантія: {draft['warranty_days']} дн." if draft.get('warranty_days') else "Гарантія: —",
            f"Категорія: {escape(cat)}",
            f"Підкатегорія: {escape(str(sub))}",
            f"На складі: {draft.get('stock', 0)}",
            f"Пост у каналі: {escape(channel)}",
            f"Фото: {photo}",
        ]
    )


def _build_product(draft: dict) -> Product:
    return Product(
        id=draft["id"],
        brand=draft.get("brand", ""),
        name=draft["name"],
        price=draft.get("price", 0),
        storage=draft.get("storage", ""),
        color=draft.get("color", ""),
        stock=draft.get("stock", 0),
        description=draft.get("description", draft["name"]),
        category=draft["category"],
        subcategory=draft.get("subcategory", ""),
        image=draft.get("image", ""),
        group=draft.get("group", ""),
        channel_post_url=draft.get("channel_post_url", ""),
        price_uah=draft.get("price_uah"),
        warranty_days=draft.get("warranty_days"),
    )


# ── Step 1: entry → category ──────────────────────────────────────────────────

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update, context):
        await update.message.reply_text("Ця команда лише для адміністраторів.")
        return ConversationHandler.END

    _clear_draft(context)
    await update.message.reply_text(
        "➕ *Додати товар*\n\nОберіть *категорію*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_category_keyboard(),
    )
    return CATEGORY


# ── Step 2: category (→ subcategory if needed, else → name) ───────────────────

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
        "Надішліть *назву* товару:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return NAME


# ── Step 3 (optional): subcategory → name ─────────────────────────────────────

async def pick_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _draft(context)["subcategory"] = query.data.split(":", 2)[2]
    await query.edit_message_text(
        "Надішліть *назву* товару:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return NAME


async def skip_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin chose 'no subcategory'."""
    query = update.callback_query
    await query.answer()
    _draft(context)["subcategory"] = ""
    await query.edit_message_text(
        "Надішліть *назву* товару:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL,
    )
    return NAME


# ── Step 4: name → model group ────────────────────────────────────────────────

async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Назва занадто коротка. Спробуйте ще раз.")
        return NAME

    _draft(context)["name"] = name
    return await _ask_product_id(update, context)


# ── Step 4b: product ID (manual, or auto-generated on skip) ───────────────────

async def _ask_product_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    suggestion = products_repo.make_unique_id(_draft(context)["name"])
    prompt = (
        "Надішліть *ID товару* (латиниця, цифри, дефіс) — він використовується "
        "у посиланнях і назві фото.\n\n"
        f"Пропозиція: `{suggestion}`\n\n"
        "Або натисніть «Згенерувати автоматично»."
    )
    await _prompt(update, prompt, _ID_SKIP)
    return PRODUCT_ID


async def collect_product_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin typed a custom id: normalize it, reject empties/duplicates."""
    product_id = products_repo.normalize_id(update.message.text)
    if not product_id:
        await update.message.reply_text(
            "Некоректний ID. Використайте латиницю, цифри та дефіс (напр. `iphone-15-pro`), "
            "або натисніть «Згенерувати автоматично».",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_ID_SKIP,
        )
        return PRODUCT_ID
    if products_repo.exists(product_id):
        await update.message.reply_text(
            f"ID `{product_id}` вже зайнятий. Введіть інший або натисніть «Згенерувати автоматично».",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_ID_SKIP,
        )
        return PRODUCT_ID

    _draft(context)["id"] = product_id
    return await _after_id(update, context)


async def skip_product_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin skipped: derive a unique id from the name automatically."""
    await update.callback_query.answer()
    draft = _draft(context)
    draft["id"] = products_repo.make_unique_id(draft["name"])
    return await _after_id(update, context)


async def _after_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Id is set: offer to join an existing model, else go to description."""
    draft = _draft(context)
    name = draft["name"]

    # Variants of one model share a group and are shown as a single catalog row.
    choices = products_repo.distinct_groups(draft.get("category", ""))
    if not choices:
        draft["group"] = name if fits_group_key(name) else ""
        return await _ask_description(update, context)

    draft["group_choices"] = choices[:_GROUP_CHOICE_LIMIT]
    text = (
        "Це варіант існуючої *моделі*?\n"
        "Варіанти однієї моделі покупець бачить одним рядком у каталозі."
    )
    keyboard = _group_keyboard(draft)
    await _prompt(update, text, keyboard)
    return GROUP


# ── Step 5: model group → description ─────────────────────────────────────────

async def _ask_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    prompt = (
        "Надішліть *характеристики* товару — кожна з нового рядка стане окремим пунктом у каналі.\n\n"
        "Приклад:\n"
        "`Фізична SIM + E-Sim`\n"
        "`Стан: Ідеальний`\n"
        "`АКБ 100% (2 цикла)`\n"
        "`Комплект: гарантія | кабель | рідна коробка`"
    )
    await _prompt(update, prompt, _DESCRIPTION_SKIP)
    return DESCRIPTION


async def pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Join the model picked from the list of existing ones."""
    await update.callback_query.answer()
    draft = _draft(context)
    choices = draft.get("group_choices", [])
    index = int(update.callback_query.data.rsplit(":", 1)[1])
    draft["group"] = choices[index] if 0 <= index < len(choices) else draft["name"]
    return await _ask_description(update, context)


async def new_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start a new model named after this product."""
    await update.callback_query.answer()
    draft = _draft(context)
    name = draft["name"]
    draft["group"] = name if fits_group_key(name) else ""
    return await _ask_description(update, context)


async def collect_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin typed a model name instead of picking one from the list."""
    name = update.message.text.strip()
    if not fits_group_key(name):
        await update.message.reply_text(
            "Назва моделі занадто довга. Скоротіть її та надішліть ще раз.",
            reply_markup=_group_keyboard(_draft(context)),
        )
        return GROUP

    _draft(context)["group"] = name
    return await _ask_description(update, context)


# ── Step 6: description → price USD ───────────────────────────────────────────

async def _ask_price_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Ціна в *USD* (напр. `460`). Якщо ціна лише в гривнях — пропустіть:"
    await _prompt(update, prompt, _PRICE_USD_SKIP)
    return PRICE_USD


async def collect_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text.strip()
    if len(description) < 2:
        await update.message.reply_text("Опис занадто короткий. Спробуйте ще раз.")
        return DESCRIPTION

    _draft(context)["description"] = description
    return await _ask_price_usd(update, context)


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context).pop("description", None)
    return await _ask_price_usd(update, context)


# ── Step 6b: price USD → price UAH ────────────────────────────────────────────

async def _ask_price_uah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Ціна в *UAH* (напр. `20700`). Якщо ціна лише в доларах — пропустіть:"
    await _prompt(update, prompt, _PRICE_UAH_SKIP)
    return PRICE_UAH


async def collect_price_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip().replace(",", ".")
    try:
        price = int(float(raw))
    except ValueError:
        await update.message.reply_text("Введіть ціле число, наприклад: 460")
        return PRICE_USD

    if price <= 0:
        await update.message.reply_text("Ціна має бути більше нуля.")
        return PRICE_USD

    _draft(context)["price"] = price
    return await _ask_price_uah(update, context)


async def skip_price_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["price"] = 0
    return await _ask_price_uah(update, context)


# ── Step 6c: price UAH → warranty ─────────────────────────────────────────────

async def collect_price_uah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip().replace(",", ".")
    try:
        price = int(float(raw))
    except ValueError:
        await update.message.reply_text("Введіть ціле число, наприклад: 20700")
        return PRICE_UAH

    if price <= 0:
        await update.message.reply_text("Ціна має бути більше нуля.")
        return PRICE_UAH

    _draft(context)["price_uah"] = price
    return await _ask_warranty(update, context)


async def skip_price_uah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    draft = _draft(context)
    draft["price_uah"] = None
    if not draft.get("price"):
        # Neither price was given — require at least one.
        await update.callback_query.edit_message_text(
            "⚠️ Потрібна хоча б одна ціна. Введіть *ціну в USD*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_PRICE_USD_SKIP,
        )
        return PRICE_USD
    return await _ask_warranty(update, context)


# ── Step 6d: warranty days → condition (brand) ────────────────────────────────

async def _ask_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Кількість *днів гарантії* (напр. `90`). Якщо немає — пропустіть:"
    await _prompt(update, prompt, _WARRANTY_SKIP)
    return WARRANTY


async def collect_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text("Введіть ціле число, наприклад: 90")
        return WARRANTY

    days = int(raw)
    if days <= 0:
        await update.message.reply_text("Кількість днів має бути більше нуля.")
        return WARRANTY

    _draft(context)["warranty_days"] = days
    return await _ask_brand(update, context)


async def skip_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["warranty_days"] = None
    return await _ask_brand(update, context)


async def _ask_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Надішліть *стан* товару (напр. `Вживаний`, `Новий`, `Новий запечатаний`):"
    await _prompt(update, prompt, _BRAND_SKIP)
    return BRAND


# ── Step 7: condition (brand) → storage ───────────────────────────────────────

async def _ask_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    hint = _storage_hint(_draft(context).get("category", ""))
    prompt = f"{hint}:"
    await _prompt(update, prompt, _STORAGE_SKIP)
    return STORAGE


async def collect_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    brand = update.message.text.strip()
    if not brand:
        await update.message.reply_text("Введіть стан. Спробуйте ще раз.")
        return BRAND

    _draft(context)["brand"] = brand
    return await _ask_storage(update, context)


async def skip_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["brand"] = ""
    return await _ask_storage(update, context)


# ── Step 8: storage → color ───────────────────────────────────────────────────

async def _ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Надішліть *колір* товару (напр. `Black`, `Starlight`, `Natural Titanium`):"
    await _prompt(update, prompt, _COLOR_SKIP)
    return COLOR


async def collect_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = update.message.text.strip()
    if not storage:
        await update.message.reply_text("Введіть значення або натисніть «Пропустити».")
        return STORAGE

    _draft(context)["storage"] = storage
    return await _ask_color(update, context)


async def skip_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["storage"] = ""
    return await _ask_color(update, context)


# ── Step 9: color → stock ─────────────────────────────────────────────────────

async def _ask_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prompt = "Скільки одиниць *на складі*? (число)"
    await _prompt(update, prompt, _STOCK_SKIP)
    return STOCK


async def collect_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    color = update.message.text.strip()
    if not color:
        await update.message.reply_text("Введіть колір. Спробуйте ще раз.")
        return COLOR

    _draft(context)["color"] = color
    return await _ask_stock(update, context)


async def skip_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["color"] = ""
    return await _ask_stock(update, context)


# ── Step 10: stock → channel (or photo when CHANNEL_ID is configured) ─────────

async def _after_stock(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Advance from stock to channel or photo."""
    if context.bot_data.get("channel_id"):
        _draft(context)["channel_post_url"] = ""
        return await _ask_photo(update, context)

    prompt = (
        "Посилання на *пост у каналі* (напр. `https://t.me/iios_cv/42`)\n"
        "або натисніть «Пропустити»:"
    )
    await _prompt(update, prompt, _CHANNEL_SKIP)
    return CHANNEL


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
    return await _after_stock(update, context)


async def skip_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["stock"] = 0
    return await _after_stock(update, context)


# ── Step 11: channel → photo ──────────────────────────────────────────────────

def _normalize_channel_url(raw: str) -> str | None:
    url = raw.strip()
    if url.startswith("t.me/") or url.startswith("telegram.me/"):
        url = "https://" + url
    if not _CHANNEL_URL_RE.match(url):
        return None
    return url


async def _ask_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if r2_write_enabled():
        hint = "Надішліть *фото* товару або натисніть «Пропустити»."
    else:
        hint = (
            "⚠️ R2 не налаштовано — фото зберегти неможливо.\n"
            "Натисніть «Пропустити», щоб продовжити."
        )
    await _prompt(update, hint, _PHOTO_KEYBOARD)
    return PHOTO


async def collect_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = _normalize_channel_url(update.message.text)
    if not url:
        await update.message.reply_text(
            "Некоректне посилання. Очікую формат:\n"
            "`https://t.me/iios_cv/42`\n"
            "або натисніть «Пропустити».",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_CHANNEL_SKIP,
        )
        return CHANNEL

    _draft(context)["channel_post_url"] = url
    return await _ask_photo(update, context)


async def skip_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _draft(context)["channel_post_url"] = ""
    return await _ask_photo(update, context)


# ── Step 12: photo → confirm ──────────────────────────────────────────────────

async def collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _draft(context)
    file_id = photo_file_id(update.message)
    if not file_id:
        await update.message.reply_text(
            "Надішліть *фото* (не файл). Або натисніть «Пропустити».",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_PHOTO_KEYBOARD,
        )
        return PHOTO

    image_key = f"{draft['id']}.jpg"

    try:
        tg_file = await context.bot.get_file(file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception:  # noqa: BLE001
        logger.exception("Failed to download photo from Telegram")
        await update.message.reply_text(
            "Не вдалося завантажити фото. Спробуйте ще раз або натисніть «Пропустити».",
            reply_markup=_PHOTO_KEYBOARD,
        )
        return PHOTO

    if await asyncio.to_thread(upload_image, image_key, image_bytes):
        draft["image"] = image_key
    else:
        await update.message.reply_text(
            "⚠️ Фото не завантажено в R2 (перевірте R2_* secrets).\n"
            "Натисніть «Пропустити», щоб зберегти товар без фото.",
            reply_markup=_PHOTO_KEYBOARD,
        )
        return PHOTO

    await _show_confirm(update, context)
    return CONFIRM


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
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
    await update.effective_message.reply_text(
        _preview(draft),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


# ── Step 13: confirm → save ───────────────────────────────────────────────────

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

    # Auto-post to the configured channel and save the returned URL.
    channel_id: str = context.bot_data.get("channel_id", "")
    post_url = await post_product(context.bot, channel_id, product)
    if post_url:
        products_repo.update(product.id, channel_post_url=post_url)

    _clear_draft(context)
    channel_note = f"\n📢 Пост у каналі: {post_url}" if post_url else ""
    price_parts = []
    if product.price_uah:
        price_parts.append(f"{product.price_uah} грн")
    if product.price:
        price_parts.append(f"${product.price}")
    price_str = " / ".join(price_parts) if price_parts else "—"
    await query.edit_message_text(
        "\n".join(
            [
                "✅ *Товар додано!*",
                "",
                f"*{product.name}*",
                f"ID: `{product.id}`",
                f"Ціна: {price_str}",
                "",
                "Вже видно в каталозі для покупців.",
            ]
        ) + channel_note,
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
        entry_points=[
            CommandHandler("add", start_add),
            MessageHandler(filters.Regex(rf"^{re.escape(BTN_ADMIN_ADD)}$"), start_add),
        ],
        states={
            CATEGORY: [CallbackQueryHandler(pick_category, pattern=r"^adm:cat:")],
            SUBCATEGORY: [
                CallbackQueryHandler(skip_subcategory, pattern=r"^adm:sub_none$"),
                CallbackQueryHandler(pick_subcategory, pattern=r"^adm:sub:"),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PRODUCT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_product_id),
                CallbackQueryHandler(skip_product_id, pattern=r"^adm:gen_id$"),
            ],
            GROUP: [
                CallbackQueryHandler(pick_group, pattern=r"^adm:grp:\d+$"),
                CallbackQueryHandler(new_group, pattern=r"^adm:grp_new$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_group),
            ],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_description),
                CallbackQueryHandler(skip_description, pattern=r"^adm:skip_desc$"),
            ],
            PRICE_USD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_price_usd),
                CallbackQueryHandler(skip_price_usd, pattern=r"^adm:skip_price_usd$"),
            ],
            PRICE_UAH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_price_uah),
                CallbackQueryHandler(skip_price_uah, pattern=r"^adm:skip_price_uah$"),
            ],
            WARRANTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_warranty),
                CallbackQueryHandler(skip_warranty, pattern=r"^adm:skip_warranty$"),
            ],
            BRAND: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_brand),
                CallbackQueryHandler(skip_brand, pattern=r"^adm:skip_brand$"),
            ],
            STORAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_storage),
                CallbackQueryHandler(skip_storage, pattern=r"^adm:skip_storage$"),
            ],
            COLOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_color),
                CallbackQueryHandler(skip_color, pattern=r"^adm:skip_color$"),
            ],
            STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_stock),
                CallbackQueryHandler(skip_stock, pattern=r"^adm:skip_stock$"),
            ],
            CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_channel),
                CallbackQueryHandler(skip_channel, pattern=r"^adm:skip_channel$"),
            ],
            PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, collect_photo),
                CallbackQueryHandler(skip_photo, pattern=r"^adm:skip_photo$"),
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
