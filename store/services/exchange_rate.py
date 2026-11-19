"""USD→UAH rate set by admins with /rate, used by the website and Google feed.

Products priced only in dollars get a hryvnia price on the site (catalog.json,
hot.json) by this rate, because Google Shopping in Ukraine only accepts UAH.
A hryvnia price typed by an admin always wins over the converted one. The bot
itself keeps showing the prices exactly as they were entered.
"""

from __future__ import annotations

import logging
import re

from store.db import settings_repo
from store.models.product import Product, is_on_sale

logger = logging.getLogger(__name__)

_KEY = "usd_uah_rate"

# Anything outside this range is almost certainly a typo (4.15 or 4150).
MIN_RATE = 20.0
MAX_RATE = 100.0

# Converted prices are rounded to this many hryvnias (18 832 → 18 830).
ROUND_TO = 10


def get_rate() -> float | None:
    """The saved rate, or None when no admin has set one yet."""
    raw = settings_repo.get(_KEY)
    if raw is None:
        return None
    try:
        rate = float(raw)
    except ValueError:
        logger.warning("Ignoring unreadable %s setting: %r", _KEY, raw)
        return None
    return rate if MIN_RATE <= rate <= MAX_RATE else None


def set_rate(rate: float) -> None:
    settings_repo.set_value(_KEY, f"{rate:.4f}".rstrip("0").rstrip("."))


def parse_rate(text: str) -> float | None:
    """'41.5', '41,50', '41.5 грн' → 41.5; None when it is not a sane rate."""
    match = re.search(r"\d+(?:[.,]\d+)?", text or "")
    if not match:
        return None
    rate = float(match.group(0).replace(",", "."))
    return rate if MIN_RATE <= rate <= MAX_RATE else None


def format_rate(rate: float) -> str:
    """41.5 → '41,50' (Ukrainian decimal comma)."""
    return f"{rate:.2f}".replace(".", ",")


def to_uah(amount_usd: int | float, rate: float) -> int:
    return int(round(amount_usd * rate / ROUND_TO) * ROUND_TO)


def is_usd_only(product: Product) -> bool:
    return bool(product.price) and not product.price_uah


def site_prices(product: Product, rate: float | None) -> dict:
    """Price fields for catalog.json / hot.json.

    The hryvnia fields are filled from the dollar ones by ``rate`` when the
    admin entered no hryvnia price. ``converted`` tells the reader which.
    """
    on_sale = is_on_sale(product)
    price_uah = product.price_uah or None
    sale_uah = (product.sale_price_uah or None) if on_sale else None
    sale_usd = (product.sale_price or None) if on_sale else None
    converted = False
    if rate and is_usd_only(product):
        price_uah = to_uah(product.price, rate)
        sale_uah = to_uah(sale_usd, rate) if sale_usd else None
        converted = True
    return {
        "price_uah": price_uah,
        "price_usd": product.price or None,
        "sale_price_uah": sale_uah,
        "sale_price_usd": sale_usd,
        "price_uah_converted": converted,
    }
