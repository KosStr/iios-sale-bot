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


def _floor_display(value: int) -> int:
    """Round value down so only the first 2 digits are significant.

    Examples: 343 → 340, 3 430 → 3 400, 41 500 → 41 000.
    Values below 10 are returned unchanged.
    """
    if value < 10:
        return value
    digits = len(str(value))
    step = 10 ** (digits - 2)
    return (value // step) * step


def _fmt_split(value: int, currency: str) -> str:
    """Format the display value for a price split label."""
    display = _floor_display(value)
    if currency == "UAH":
        return f"{display:,} ₴".replace(",", "\u00a0")
    return f"${display:,}"


def has_price_filter(flt: dict) -> bool:
    """True when the current category/subcategory has 5+ products."""
    category = flt.get("category", "all")
    subcategory = flt.get("subcategory", "all")
    return len(_products_in_category(category, subcategory)) >= 5


def dynamic_price_ranges(
    flt: dict, currency: str
) -> list[tuple[str, str, float, float]]:
    """Return 3 price options: all / up-to-median / median+.

    The split point is the median effective price of the products currently
    visible in the selected category/subcategory.  Falls back to a single
    "any" option when fewer than 2 products are available.
    Labels use a rounded display value; filter bounds stay exact.
    """
    category = flt.get("category", "all")
    subcategory = flt.get("subcategory", "all")
    products = _products_in_category(category, subcategory)

    if len(products) < 2:
        return [("any", "Будь-яка ціна", 0, math.inf)]

    prices = sorted(convert(effective_price(p), currency) for p in products)
    median = prices[len(prices) // 2]
    median_fmt = _fmt_split(median, currency)

    return [
        ("any", "Будь-яка ціна", 0, math.inf),
        ("low", f"До {median_fmt}", 0, median + 1),
        ("high", f"{median_fmt}+", median, math.inf),
    ]


def format_price(amount_usd: int, currency: str) -> str:
    value = convert(amount_usd, currency)
    if currency == "UAH":
        return f"{value:,} ₴".replace(",", " ")
    return f"${value:,}"


def button_price(product: Product, currency: str) -> str:
    """Short price label for catalog list buttons."""
    label = format_price(effective_price(product), currency)
    if is_on_sale(product):
        return f"🔥 {label}"
    return label


def filter_products(flt: dict) -> list[Product]:
    category = flt.get("category", "all")
    subcategory = flt.get("subcategory", "all")
    currency = flt.get("currency", "UAH")
    price_key = flt.get("price", "any")

    ranges = dynamic_price_ranges(flt, currency)
    lo, hi = next(
        ((rlo, rhi) for k, _, rlo, rhi in ranges if k == price_key),
        (0, math.inf),
    )

    result: list[Product] = []
    for product in _products_in_category(category, subcategory):
        price = convert(effective_price(product), currency)
        if lo <= price < hi:
            result.append(product)
    return result


def filter_summary(flt: dict) -> str:
    cat_key = flt.get("category", "all")
    lines = [f"Категорія: *{CATEGORY_LABELS.get(cat_key, 'Усі категорії')}*"]

    sub_key = flt.get("subcategory", "all")
    if category_has_subcategories(cat_key) and sub_key != "all":
        sub_label = SUBCATEGORY_LABELS[cat_key].get(sub_key, sub_key)
        lines.append(f"Підкатегорія: *{sub_label}*")

    currency = flt.get("currency", "UAH")
    price_key = flt.get("price", "any")
    price_label = next(
        (label for k, label, _, _ in dynamic_price_ranges(flt, currency) if k == price_key),
        "Будь-яка ціна",
    )
    lines.extend([f"Валюта: *{currency}*", f"Ціна: *{price_label}*"])
    return "\n".join(lines)
