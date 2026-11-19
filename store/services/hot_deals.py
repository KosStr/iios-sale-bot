"""Publish hot deals to the landing page.

Products marked as hot (``is_hot``) are serialized to ``hot.json`` and
uploaded to the R2 bucket next to the product photos. The landing page
fetches that file and builds its carousel from it, so the bot's Fly machine
never has to wake up for site visitors.

Only in-stock products are published: a sold-out deal would just bounce the
visitor to "this offer has ended" in the bot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from store.models.product import Product
from store.db import products_repo
from store.services.exchange_rate import get_rate, site_prices
from store.services.images import r2_write_enabled, upload_object
from store.services.web_images import site_image_url
from store.utils.format import join_specs

logger = logging.getLogger(__name__)

# Short cache so admin changes reach the site within about a minute.
_CACHE_CONTROL = "public, max-age=60"


def hot_deals_key() -> str:
    return os.getenv("HOT_DEALS_KEY", "hot.json")


def _deal(product: Product, version: int, rate: float | None) -> dict:
    image = site_image_url(product, version)
    prices = site_prices(product, rate)
    prices.pop("price_uah_converted")
    return {
        "id": product.id,
        "name": product.name,
        # Small grey line under the name in the hero phone mockup (e.g. the colour).
        "subtitle": join_specs(product.color) or None,
        # Regular and sale prices (struck-through regular price + badge); the
        # landing shows UAH when set, otherwise USD. Same numbers as
        # catalog.json, so dollar-only products show UAH by the admin's /rate.
        **prices,
        "image": image,
    }


def build_payload(products: list[Product] | None = None) -> dict:
    version = int(time.time())
    if products is None:
        products = products_repo.fetch_hot()
    rate = get_rate()
    return {
        "updated_at": version,
        "deals": [_deal(p, version, rate) for p in products if p.is_hot and p.stock > 0],
    }


def publish_hot_deals_sync() -> bool:
    payload = build_payload()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ok = upload_object(
        hot_deals_key(), body, "application/json; charset=utf-8", _CACHE_CONTROL
    )
    if ok:
        logger.info("Published %d hot deal(s) to %s", len(payload["deals"]), hot_deals_key())
    return ok


async def publish_hot_deals() -> bool:
    """Regenerate and upload hot.json. Returns False if R2 is not writable."""
    if not r2_write_enabled():
        logger.warning("Hot deals not published: R2 credentials not configured.")
        return False
    try:
        return await asyncio.to_thread(publish_hot_deals_sync)
    except Exception:  # noqa: BLE001 - never break an admin action over the landing
        logger.exception("Failed to publish hot deals")
        return False


async def refresh_if_hot(*products: Product | None) -> None:
    """Republish when any of the given product states (before/after) is hot."""
    if any(p is not None and p.is_hot for p in products):
        await publish_hot_deals()
