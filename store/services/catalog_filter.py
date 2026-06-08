"""Catalog filtering: categories, currency (UAH/USD) and price ranges.

Per-user filter state is stored in ``context.user_data["filter"]``.
Product prices are kept in USD and converted to UAH for display/filtering.
"""

from __future__ import annotations

import math

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
    ("phone", "📱 Смартфони"),
    ("watch", "⌚ Годинники"),
    ("headphones", "🎧 Навушники"),
    ("laptop", "💻 Ноутбуки"),
    ("accessories", "🔌 Аксесуари"),
]
CATEGORY_LABELS: dict[str, str] = dict(CATEGORIES)

# Currency code -> symbol.
CURRENCIES: dict[str, str] = {"UAH": "₴", "USD": "$"}

# Price ranges per currency: key, label, low (incl.), high (excl.).
PRICE_RANGES: dict[str, list[tuple[str, str, float, float]]] = {
    "USD": [
        ("any", "Будь-яка ціна", 0, math.inf),
        ("r1", "До $300", 0, 300),
        ("r2", "$300 – $700", 300, 700),
        ("r3", "$700 – $1000", 700, 1000),
        ("r4", "Понад $1000", 1000, math.inf),
    ],
    "UAH": [
        ("any", "Будь-яка ціна", 0, math.inf),
        ("r1", "До 12 000 ₴", 0, 12000),
        ("r2", "12 000 – 29 000 ₴", 12000, 29000),
        ("r3", "29 000 – 41 000 ₴", 29000, 41000),
        ("r4", "Понад 41 000 ₴", 41000, math.inf),
    ],
}

DEFAULT_FILTER: dict[str, str] = {
    "category": "all",
    "currency": "UAH",
    "price": "any",
    "mode": "catalog",  # "catalog" or "booking"
}


def get_filter(context) -> dict:
    """Return (and lazily create) the current user's filter state."""
    return context.user_data.setdefault("filter", dict(DEFAULT_FILTER))


def convert(amount_usd: int, currency: str) -> int:
    if currency == "UAH":
        return round(amount_usd * UAH_RATE)
    return amount_usd


def format_price(amount_usd: int, currency: str) -> str:
    value = convert(amount_usd, currency)
    if currency == "UAH":
        return f"{value:,} ₴".replace(",", " ")
    return f"${value:,}"


def button_price(product: Product, currency: str) -> str:
    """Short price label for catalog/booking list buttons."""
    label = format_price(effective_price(product), currency)
    if is_on_sale(product):
        return f"🔥 {label}"
    return label


def price_range_label(currency: str, key: str) -> str:
    for k, label, _lo, _hi in PRICE_RANGES.get(currency, []):
        if k == key:
            return label
    return "Будь-яка ціна"


def _range_bounds(currency: str, key: str) -> tuple[float, float]:
    for k, _label, lo, hi in PRICE_RANGES.get(currency, []):
        if k == key:
            return lo, hi
    return 0, math.inf


def filter_products(flt: dict) -> list[Product]:
    category = flt.get("category", "all")
    currency = flt.get("currency", "UAH")
    lo, hi = _range_bounds(currency, flt.get("price", "any"))

    result: list[Product] = []
    for product in get_all_products():
        if category != "all" and product.category != category:
            continue
        price = convert(effective_price(product), currency)
        if lo <= price < hi:
            result.append(product)
    return result


def filter_summary(flt: dict) -> str:
    category = CATEGORY_LABELS.get(flt.get("category", "all"), "Усі категорії")
    currency = flt.get("currency", "UAH")
    price = price_range_label(currency, flt.get("price", "any"))
    return "\n".join(
        [
            f"Категорія: *{category}*",
            f"Валюта: *{currency}*",
            f"Ціна: *{price}*",
        ]
    )
