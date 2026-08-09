"""Catalog filtering: categories, currency (UAH/USD) and price ranges.

Per-user filter state is stored in ``context.user_data["filter"]``.
Product prices are kept in USD and converted to UAH for display/filtering.
"""

from __future__ import annotations

import math
import os

from store.data.products import (
    Product,
    effective_price,
    get_all_products,
    is_on_sale,
)

# USD -> UAH conversion rate (edit to taste / wire to a live rate later).
UAH_RATE = 41.5

# Category keys paired with their Ukrainian labels (order = menu order).
CATEGORIES: list[tuple[str, str]] = [
    ("all", "🧩 Усі категорії"),
    ("phone", "📱 iPhone"),
    ("ipad", "📲 iPad"),
    ("watch", "⌚ Годинники"),
    ("headphones", "🎧 Навушники"),
    ("laptop", "💻 MacBook"),
    ("accessories", "🔌 Аксесуари"),
]
CATEGORY_LABELS: dict[str, str] = dict(CATEGORIES)

# Subcategories per parent category (first entry is always "all").
SUBCATEGORIES: dict[str, list[tuple[str, str]]] = {
    "phone": [
        ("all", "🧩 Усі"),
        ("iphone_17", "iPhone 17"),
        ("iphone_16", "iPhone 16"),
        ("iphone_15", "iPhone 15"),
    ],
    "ipad": [
        ("all", "🧩 Усі"),
        ("ipad_pro", "iPad Pro"),
        ("ipad_air", "iPad Air"),
        ("ipad_mini", "iPad mini"),
        ("ipad_base", "iPad"),
    ],
    "laptop": [
        ("all", "🧩 Усі"),
        ("macbook_m", "MacBook M"),
        ("macbook_intel", "MacBook Intel"),
    ],
    "accessories": [
        ("all", "🧩 Усі"),
        ("powerbank", "🔋 Powerbank"),
        ("case", "📱 Чохли"),
        ("cable", "🔌 Кабелі"),
        ("screen_guard", "🛡 Захист екрану"),
        ("charger", "⚡ Зарядки"),
    ],
}
SUBCATEGORY_LABELS: dict[str, dict[str, str]] = {
    category: dict(items) for category, items in SUBCATEGORIES.items()
}

# Currency code -> symbol.
CURRENCIES: dict[str, str] = {"UAH": "₴", "USD": "$"}

_default_currency = os.getenv("CURRENCY", "UAH").strip().upper() or "UAH"
if _default_currency not in CURRENCIES:
    _default_currency = "UAH"

DEFAULT_FILTER: dict[str, str] = {
    "category": "all",
    "subcategory": "all",
    "currency": _default_currency,
    "price": "any",
}


def _normalize_filter(flt: dict) -> dict:
    category = flt.get("category", "all")
    valid_subs = {key for key, _ in subcategory_options(category)}
    if flt.get("subcategory", "all") not in valid_subs:
        flt["subcategory"] = "all"

    currency = flt.get("currency", DEFAULT_FILTER["currency"])
    if currency not in CURRENCIES:
        flt["currency"] = "UAH"
    return flt


def category_has_subcategories(category: str) -> bool:
    return category in SUBCATEGORIES


def subcategory_options(category: str) -> list[tuple[str, str]]:
    return SUBCATEGORIES.get(category, [])


def get_filter(context) -> dict:
    """Return (and lazily create) the current user's filter state."""
    flt = context.user_data.setdefault("filter", dict(DEFAULT_FILTER))
    return _normalize_filter(flt)


def convert(amount_usd: int, currency: str) -> int:
    if currency == "UAH":
        return round(amount_usd * UAH_RATE)
    return amount_usd


def _products_in_category(category: str, subcategory: str) -> list[Product]:
    """All products matching category/subcategory, ignoring price."""
    return [
        p for p in get_all_products()
        if (category == "all" or p.category == category)
        and (
            not category_has_subcategories(category)
            or subcategory == "all"
            or p.subcategory == subcategory
        )
    ]


def _products_for(flt: dict) -> list[Product]:
    """Products matching the filter's category/subcategory, ignoring price."""
    return _products_in_category(
        flt.get("category", "all"), flt.get("subcategory", "all")
    )


def _fmt_amount(value: int, currency: str) -> str:
    """Format an amount already converted to `currency`."""
    if currency == "UAH":
        return f"{value:,} ₴".replace(",", " ")
    return f"${value:,}"


def format_price(amount_usd: int, currency: str) -> str:
    """Format a USD amount for display in `currency`."""
    return _fmt_amount(convert(amount_usd, currency), currency)


# Unrestricted option, also the fallback when a stored price key no longer exists.
ANY_PRICE: tuple[str, str, float, float] = ("any", "Будь-яка ціна", 0, math.inf)


def _price_ranges(
    products: list[Product], currency: str
) -> list[tuple[str, str, float, float]]:
    """Price options for `products`: any / below-average / above-average.

    The split point is the average (mean) effective price, shown as its exact
    value. The two halves are only offered when products fall on both sides,
    so choosing one can never lead to an empty result.
    """
    if len(products) < 2:
        return [ANY_PRICE]

    prices = [convert(effective_price(p), currency) for p in products]
    average = round(sum(prices) / len(prices))
    if min(prices) >= average:  # every product sits at/above the average
        return [ANY_PRICE]

    label = _fmt_amount(average, currency)
    return [
        ANY_PRICE,
        ("low", f"Менше {label}", 0, average),
        ("high", f"Більше {label}", average, math.inf),
    ]


def dynamic_price_ranges(
    flt: dict, currency: str
) -> list[tuple[str, str, float, float]]:
    """Price options for the category/subcategory selected in `flt`."""
    return _price_ranges(_products_for(flt), currency)


def has_price_filter(flt: dict) -> bool:
    """True when the current category/subcategory has 5+ products."""
    return len(_products_for(flt)) >= 5


def button_price(product: Product, currency: str) -> str:
    """Short price label for catalog list buttons."""
    label = format_price(effective_price(product), currency)
    if is_on_sale(product):
        return f"🔥 {label}"
    return label


def _selected_range(
    ranges: list[tuple[str, str, float, float]], price_key: str
) -> tuple[str, float, float]:
    """Label and bounds of the chosen option, falling back to 'any'."""
    for key, label, lo, hi in ranges:
        if key == price_key:
            return label, lo, hi
    return ANY_PRICE[1], ANY_PRICE[2], ANY_PRICE[3]


def filter_products(flt: dict) -> list[Product]:
    """Products matching the full filter: category, subcategory and price."""
    currency = flt.get("currency", "UAH")
    products = _products_for(flt)
    _, lo, hi = _selected_range(
        _price_ranges(products, currency), flt.get("price", "any")
    )
    return [
        product
        for product in products
        if lo <= convert(effective_price(product), currency) < hi
    ]


def filter_summary(flt: dict) -> str:
    cat_key = flt.get("category", "all")
    lines = [f"Категорія: *{CATEGORY_LABELS.get(cat_key, 'Усі категорії')}*"]

    sub_key = flt.get("subcategory", "all")
    if category_has_subcategories(cat_key) and sub_key != "all":
        sub_label = SUBCATEGORY_LABELS[cat_key].get(sub_key, sub_key)
        lines.append(f"Підкатегорія: *{sub_label}*")

    currency = flt.get("currency", "UAH")
    price_label, _lo, _hi = _selected_range(
        dynamic_price_ranges(flt, currency), flt.get("price", "any")
    )
    lines.extend([f"Валюта: *{currency}*", f"Ціна: *{price_label}*"])
    return "\n".join(lines)
