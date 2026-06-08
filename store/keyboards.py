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
    PRICE_RANGES,
    button_price,
)

# Reply-keyboard button labels (also used as router patterns in bot.py)
BTN_CATALOG = "🛍 Каталог"
BTN_CART = "🛒 Кошик"
BTN_BOOK = "📅 Забронювати"
BTN_CONTACTS = "📞 Контакти"
BTN_LOCATION = "📍 Локація"
BTN_HELP = "ℹ️ Допомога"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_CATALOG), KeyboardButton(BTN_CART)],
            [KeyboardButton(BTN_BOOK)],
            [KeyboardButton(BTN_CONTACTS), KeyboardButton(BTN_LOCATION)],
            [KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _check(selected: bool, label: str) -> str:
    return f"✅ {label}" if selected else label


def filter_keyboard(flt: dict) -> InlineKeyboardMarkup:
    """The filter screen: category, currency and price selectors."""
    currency = flt.get("currency", "UAH")
    rows: list[list[InlineKeyboardButton]] = []

    # Categories, two per row
    cat_buttons = [
        InlineKeyboardButton(
            _check(flt.get("category") == key, label), callback_data=f"flt:cat:{key}"
        )
        for key, label in CATEGORIES
    ]
    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    # Currency toggle
    rows.append(
        [
            InlineKeyboardButton(
                _check(currency == code, f"{code} {symbol}"),
                callback_data=f"flt:cur:{code}",
            )
            for code, symbol in CURRENCIES.items()
        ]
    )

    # Price ranges (depend on currency), one per row
    for key, label, _lo, _hi in PRICE_RANGES[currency]:
        rows.append(
            [
                InlineKeyboardButton(
                    _check(flt.get("price") == key, label),
                    callback_data=f"flt:price:{key}",
                )
            ]
        )

    rows.append([InlineKeyboardButton("🔎 Показати товари", callback_data="flt:show")])
    return InlineKeyboardMarkup(rows)


def catalog_results_keyboard(
    products: list[Product], currency: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{product.name} — {button_price(product, currency)}",
                callback_data=f"product:{product.id}",
            )
        ]
        for product in products
    ]
    rows.append(
        [
            InlineKeyboardButton("🔍 Фільтр", callback_data="flt:open"),
            InlineKeyboardButton("🛒 Кошик", callback_data="cart:view"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def booking_results_keyboard(
    products: list[Product], currency: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{product.name} — {button_price(product, currency)}",
                callback_data=f"book:{product.id}",
            )
        ]
        for product in products
    ]
    rows.append([InlineKeyboardButton("🔍 Фільтр", callback_data="flt:open")])
    return InlineKeyboardMarkup(rows)


def product_keyboard(product: Product) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if product.stock > 0:
        rows.append(
            [InlineKeyboardButton("➕ Додати у кошик", callback_data=f"add:{product.id}")]
        )
    rows.append(
        [InlineKeyboardButton("📅 Забронювати", callback_data=f"book:{product.id}")]
    )
    rows.append(
        [
            InlineKeyboardButton("⬅️ Назад до каталогу", callback_data="catalog:view"),
            InlineKeyboardButton("🛒 Кошик", callback_data="cart:view"),
        ]
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
