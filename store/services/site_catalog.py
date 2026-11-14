"""Publish the in-stock catalog for the website's /catalog page.

All in-stock products are serialized to ``catalog.json`` in the R2 bucket. A
small Cloudflare Worker renders it as plain HTML at ``/catalog``, so search
engines and AI crawlers (which do not run JavaScript) can see every product
and price.

Products are edited from many admin handlers, so instead of hooking each one
a background loop rebuilds the payload every few minutes while the bot is
awake and uploads it only when it changed. Sale expiry (``sale_until``) is
picked up the same way.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time

from store.models.product import Product, is_on_sale
from store.db import products_repo
from store.services.catalog_filter import CATEGORY_LABELS, SUBCATEGORY_LABELS
from store.services.images import image_url, r2_write_enabled, upload_object
from store.utils.format import present_values

logger = logging.getLogger(__name__)

# The Worker caches the rendered page itself; this only covers direct reads.
_CACHE_CONTROL = "public, max-age=60"
_SYNC_INTERVAL_SECONDS = 120

# Hash of the last uploaded items; None forces the next upload.
_last_hash: str | None = None


def catalog_key() -> str:
    return os.getenv("CATALOG_KEY", "catalog.json")


def request_catalog_refresh() -> None:
    """Force the next sync to upload, e.g. after a photo was replaced in place."""
    global _last_hash
    _last_hash = None


def _label(text: str) -> str:
    """Category labels carry a leading emoji for the bot ('📱 iPhone'); drop it."""
    head, _, rest = text.partition(" ")
    return rest if rest and not head.isalnum() else text


def _item(product: Product) -> dict:
    on_sale = is_on_sale(product)
    category_label = CATEGORY_LABELS.get(product.category, product.category)
    subcategory_label = SUBCATEGORY_LABELS.get(product.category, {}).get(product.subcategory, "")
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "category_label": _label(category_label),
        "subcategory_label": _label(subcategory_label) if subcategory_label else None,
        # Free text typed by admins: "Вживаний", "Новий", "Новий запечатаний"...
        "condition": " ".join(present_values(product.brand)) or None,
        "storage": " ".join(present_values(product.storage)) or None,
        "color": " ".join(present_values(product.color)) or None,
        "description": (product.description or "").strip() or None,
        "warranty_days": product.warranty_days or None,
        # Same price fields as hot.json: UAH is shown when set, otherwise USD.
        "price_uah": product.price_uah or None,
        "price_usd": product.price or None,
        "sale_price_uah": (product.sale_price_uah or None) if on_sale else None,
        "sale_price_usd": (product.sale_price or None) if on_sale else None,
        "image": image_url(product),
    }


def build_items(products: list[Product] | None = None) -> list[dict]:
    if products is None:
        products = products_repo.fetch_all()
    return [_item(p) for p in products if p.stock > 0]


def _with_image_versions(items: list[dict], version: int) -> list[dict]:
    """Photos are overwritten under the same key, so bust browser caches per upload."""
    versioned = []
    for item in items:
        image = item["image"]
        if image:
            image = f"{image}{'&' if '?' in image else '?'}v={version}"
        versioned.append({**item, "image": image})
    return versioned


def _sync_once() -> bool:
    """Upload catalog.json if the items changed since the last upload."""
    global _last_hash
    items = build_items()
    digest = hashlib.sha256(
        json.dumps(items, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if digest == _last_hash:
        return True
    version = int(time.time())
    payload = {"updated_at": version, "items": _with_image_versions(items, version)}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ok = upload_object(catalog_key(), body, "application/json; charset=utf-8", _CACHE_CONTROL)
    if ok:
        _last_hash = digest
        logger.info("Published %d catalog item(s) to %s", len(items), catalog_key())
    return ok


async def run_catalog_sync() -> None:
    """Keep catalog.json in sync while the bot runs. Never raises."""
    if not r2_write_enabled():
        logger.warning("Site catalog not published: R2 credentials not configured.")
        return
    while True:
        try:
            await asyncio.to_thread(_sync_once)
        except Exception:  # noqa: BLE001 - the site catalog must never break the bot
            logger.exception("Failed to publish the site catalog")
        await asyncio.sleep(_SYNC_INTERVAL_SECONDS)
