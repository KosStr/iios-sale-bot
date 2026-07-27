"""Static product catalog used as the store's data source.

For a production store, replace this module with a real data layer
(database, CMS, or external API) that exposes the same helper functions.

Prices are stored in USD; the bot converts them to UAH on the fly
(see store/services/catalog_filter.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Category keys used for filtering. Ukrainian labels live in the filter service.
CATEGORY_PHONE = "phone"
CATEGORY_WATCH = "watch"
CATEGORY_HEADPHONES = "headphones"
CATEGORY_LAPTOP = "laptop"
CATEGORY_IPAD = "ipad"
CATEGORY_ACCESSORIES = "accessories"

# Phone subcategory keys (iPhone models).
SUBCATEGORY_IPHONE_15 = "iphone_15"
SUBCATEGORY_IPHONE_16 = "iphone_16"
SUBCATEGORY_IPHONE_17 = "iphone_17"

# MacBook subcategory keys.
SUBCATEGORY_MACBOOK_M = "macbook_m"
SUBCATEGORY_MACBOOK_INTEL = "macbook_intel"

# iPad subcategory keys.
SUBCATEGORY_IPAD_PRO = "ipad_pro"
SUBCATEGORY_IPAD_AIR = "ipad_air"
SUBCATEGORY_IPAD_MINI = "ipad_mini"
SUBCATEGORY_IPAD_BASE = "ipad_base"

# Accessory subcategory keys (labels live in catalog_filter.SUBCATEGORIES).
SUBCATEGORY_POWERBANK = "powerbank"
SUBCATEGORY_CASE = "case"
SUBCATEGORY_CABLE = "cable"
SUBCATEGORY_SCREEN_GUARD = "screen_guard"
SUBCATEGORY_CHARGER = "charger"


@dataclass(frozen=True)
class Product:
    id: str
    brand: str
    name: str
    price: int  # regular price, in USD
    storage: str
    color: str
    stock: int
    description: str
    category: str = CATEGORY_PHONE
    subcategory: str = ""
    image: str = ""
    # Products sharing the same non-empty `group` are variants of one model
    # (e.g. "iPhone 13" in 128GB/256GB). Empty means a standalone product.
    group: str = ""
    # Time-limited discount: special price (USD) active until `sale_until`.
    sale_price: int | None = None
    sale_until: datetime | None = None
    # Optional link to a Telegram channel post (e.g. https://t.me/iios_cv/42).
    # When set, a "View in channel" button appears on the product card.
    channel_post_url: str = ""


PRODUCTS: list[Product] = [
    # intentionally empty — add products via the admin /add command
]


def get_all_products() -> list[Product]:
    from store.db.products_repo import fetch_all

    return fetch_all()


def get_product_by_id(product_id: str) -> Product | None:
    from store.db.products_repo import fetch_by_id

    return fetch_by_id(product_id)


def is_in_stock(product: Product | None) -> bool:
    return product is not None and product.stock > 0


def is_on_sale(product: Product, now: datetime | None = None) -> bool:
    """True if the product has an active, non-expired discount."""
    if product.sale_price is None or product.sale_until is None:
        return False
    now = now or datetime.now()
    return now < product.sale_until


def effective_price(product: Product, now: datetime | None = None) -> int:
    """Current price in USD: the sale price while active, otherwise regular."""
    if is_on_sale(product, now):
        return product.sale_price
    return product.price


def sale_time_left(product: Product, now: datetime | None = None) -> timedelta | None:
    """How long the discount is still valid, or None if not on sale."""
    if not is_on_sale(product, now):
        return None
    now = now or datetime.now()
    return product.sale_until - now

