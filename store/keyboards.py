"""Reply and inline keyboards.

Callback data is namespaced as "action:payload" and parsed centrally in
the bot router. Keep payloads short — Telegram limits callback data to 64 bytes.
"""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from store.data.products import Product
from store.services.cart import Cart
from store.services.catalog_filter import (
    CATEGORIES,
    CURRENCIES,
    button_price,
    category_has_subcategories,
    dynamic_price_ranges,
    format_price,
    has_price_filter,
    subcategory_options,
)
from store.services.grouping import Group

# Reply-keyboard button labels (also used as router patterns in bot.py)
BTN_CATALOG = "🛍 Каталог"
BTN_CART = "🛒 Кошик"
BTN_CONTACTS = "📞 Контакти"
BTN_LOCATION = "📍 Локація"
BTN_HELP = "ℹ️ Допомога"
BTN_ADMIN_ADD = "➕ Додати товар"
BTN_ADMIN_PRODUCTS = "📋 Товари"


def main_menu_keyboard(admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(BTN_CATALOG), KeyboardButton(BTN_CART)],
        [KeyboardButton(BTN_CONTACTS), KeyboardButton(BTN_LOCATION)],
        [KeyboardButton(BTN_HELP)],
    ]
    if admin:
        rows.append(
            [KeyboardButton(BTN_ADMIN_ADD), KeyboardButton(BTN_ADMIN_PRODUCTS)]
        )
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _check(selected: bool, label: str) -> str:
    return f"✅ {label}" if selected else label


def _rows_of_2(
    buttons: list[InlineKeyboardButton],
) -> list[list[InlineKeyboardButton]]:
    """Split a flat button list into two-column rows."""
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def filter_keyboard(flt: dict) -> InlineKeyboardMarkup:
    """Step-based filter dispatcher: cat → [sub →] price."""
    ui = flt.get("ui", "main")
    if ui == "price":
        return _price_filter_keyboard(flt)
    if ui == "sub" and category_has_subcategories(flt.get("category", "all")):
        return _subcategory_filter_keyboard(flt)
    return _category_keyboard(flt)


def _category_keyboard(flt: dict) -> InlineKeyboardMarkup:
    """Step 1: pick a category. Tapping any option auto-advances."""
    buttons = [
        InlineKeyboardButton(
            _check(flt.get("category") == key, label), callback_data=f"flt:cat:{key}"
        )
        for key, label in CATEGORIES
    ]
    return InlineKeyboardMarkup(_rows_of_2(buttons))


def _subcategory_filter_keyboard(flt: dict) -> InlineKeyboardMarkup:
    """Step 2 (optional): pick a subcategory, then proceed to price."""
    category = flt.get("category", "all")
    sub_buttons = [
        InlineKeyboardButton(
            _check(flt.get("subcategory", "all") == key, label),
            callback_data=f"flt:sub:{key}",
        )
        for key, label in subcategory_options(category)
    ]
    rows = _rows_of_2(sub_buttons)
    next_label = "Далі ➡️" if has_price_filter(flt) else "🔎 Показати товари"
    rows.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="flt:back"),
        InlineKeyboardButton(next_label, callback_data="flt:to_price"),
    ])
    return InlineKeyboardMarkup(rows)


def _price_filter_keyboard(flt: dict) -> InlineKeyboardMarkup:
    """Step 3: pick currency and price range, then show results."""
    currency = flt.get("currency", "UAH")
    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                _check(currency == code, f"{code} {symbol}"),
                callback_data=f"flt:cur:{code}",
            )
            for code, symbol in CURRENCIES.items()
        ]
    )

    for key, label, _lo, _hi in dynamic_price_ranges(flt, currency):
        rows.append(
            [
                InlineKeyboardButton(
                    _check(flt.get("price") == key, label),
                    callback_data=f"flt:price:{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="flt:back"),
            InlineKeyboardButton("🔎 Показати товари", callback_data="flt:show"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _group_row(group: Group, currency: str) -> list[InlineKeyboardButton]:
    """One list row for a model group.

    Single-variant groups open the product card; multi-variant groups expand
    to a variant list via the ``group:`` callback.
    """
    if group.is_single:
        product = group.only
        return [
            InlineKeyboardButton(
                f"{product.name} — {button_price(product, currency)}",
                callback_data=f"product:{product.id}",
            )
        ]
    fire = " 🔥" if group.on_sale else ""
    label = (
        f"{group.label} ({len(group.variants)}) — "
        f"від {format_price(group.min_price, currency)}{fire}"
    )
    return [InlineKeyboardButton(label, callback_data=f"group:{group.key}")]


def catalog_results_keyboard(
    groups: list[Group], currency: str
) -> InlineKeyboardMarkup:
    rows = [_group_row(group, currency) for group in groups]
    rows.append(
        [
            InlineKeyboardButton("🔍 Фільтр", callback_data="flt:open"),
            InlineKeyboardButton("🛒 Кошик", callback_data="cart:view"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def group_variants_keyboard(group: Group, currency: str) -> InlineKeyboardMarkup:
    """List the variants of a grouped model."""
    rows = [
        [
            InlineKeyboardButton(
                f"{variant.storage} • {variant.color} — {button_price(variant, currency)}",
                callback_data=f"product:{variant.id}",
            )
        ]
        for variant in group.variants
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="flt:show")])
    return InlineKeyboardMarkup(rows)


def product_keyboard(product: Product) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if product.stock > 0:
        rows.append(
            [InlineKeyboardButton("➕ Додати у кошик", callback_data=f"add:{product.id}")]
        )
    if product.channel_post_url:
        rows.append(
            [InlineKeyboardButton("📢 Пост у каналі", url=product.channel_post_url)]
        )
    rows.append(
        [
            InlineKeyboardButton("⬅️ Назад до каталогу", callback_data="catalog:view"),
            InlineKeyboardButton("🛒 Кошик", callback_data="cart:view"),
        ]
    )
    rows.append(
        [InlineKeyboardButton("📅 Забронювати", callback_data=f"book:{product.id}")]
    )
    return InlineKeyboardMarkup(rows)


def cart_keyboard(cart: Cart) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"❌ Прибрати {item.product.name}",
                callback_data=f"remove:{item.product.id}",
            )
        ]
        for item in cart.items
    ]
    if not cart.is_empty:
        rows.append(
            [InlineKeyboardButton("✅ Оформити замовлення", callback_data="checkout:start")]
        )
        rows.append([InlineKeyboardButton("🗑 Очистити кошик", callback_data="cart:clear")])
    rows.append(
        [InlineKeyboardButton("⬅️ Продовжити покупки", callback_data="catalog:view")]
    )
    return InlineKeyboardMarkup(rows)
