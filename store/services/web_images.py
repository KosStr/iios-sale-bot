"""Web-sized copies of product photos for the website.

Admins upload photos straight from the phone camera (around 1920x2560, 300 KB),
far more than a catalog card needs. Next to every original ``<key>`` the bot
keeps a small WebP at ``web/<key stem>.webp``; the site (catalog.json and
hot.json) links to that copy, while Telegram keeps using the original.

A web copy's URL carries its own upload time (``?v=``), so it is cached
"forever" and only re-downloaded when that photo is replaced.

Copies are made on upload, and ``ensure_web_copies`` backfills the ones that
are missing (photos uploaded before this existed).
"""

from __future__ import annotations

import io
import logging
import threading
import time

from store.models.product import Product
from store.services.images import (
    delete_object,
    get_image_bytes,
    image_url,
    list_objects,
    object_key,
    public_base,
    upload_image,
    upload_object,
)

logger = logging.getLogger(__name__)

WEB_PREFIX = "web/"
# Catalog cards are at most ~300 CSS px wide; this covers 2x screens.
MAX_SIZE = (640, 960)
_QUALITY = 80
_CACHE_CONTROL = "public, max-age=31536000, immutable"

_lock = threading.Lock()
# Web copy key -> upload time; None until the bucket has been listed.
_versions: dict[str, int] | None = None
# Originals that are missing or unreadable, so they are not retried every sync.
_failed: set[str] = set()


def web_key(image_key: str) -> str:
    """Key of the web copy for an original's key ('a.jpg' -> 'web/a.webp')."""
    head, dot, _ext = image_key.rpartition(".")
    stem = head if dot and "/" not in _ext else image_key
    return f"{WEB_PREFIX}{stem}.webp"


def make_web_copy(data: bytes) -> bytes | None:
    """Downscale an image to a WebP that fits MAX_SIZE, or None if unreadable."""
    try:
        from PIL import Image, ImageOps  # lazy: the bot runs without Pillow

        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "WEBP", quality=_QUALITY, method=6)
            return out.getvalue()
    except Exception as err:  # noqa: BLE001 - a bad photo must not break an upload
        logger.warning("Could not make a web copy: %s", err)
        return None


def _known() -> dict[str, int] | None:
    """Web copies present in the bucket (listed once, then tracked in memory)."""
    global _versions
    with _lock:
        if _versions is None:
            _versions = list_objects(WEB_PREFIX)
        return _versions


def _publish(image_key: str, data: bytes) -> bool:
    """Make and upload the web copy of `image_key`."""
    body = make_web_copy(data)
    key = web_key(image_key)
    if body is None or not upload_object(key, body, "image/webp", _CACHE_CONTROL):
        return False
    known = _known()
    if known is not None:
        with _lock:
            known[key] = int(time.time())
    _failed.discard(image_key)
    return True


def _forget(image_key: str) -> None:
    """Drop a web copy that no longer matches its original."""
    key = web_key(image_key)
    known = _known()
    if known is None or key in known:
        delete_object(key)
    if known is not None:
        with _lock:
            known.pop(key, None)


def upload_product_photo(image_key: str, data: bytes) -> bool:
    """Upload a product photo plus its web copy. True when the original is stored."""
    if not upload_image(image_key, data):
        return False
    if not _publish(image_key, data):
        # The site falls back to the original instead of showing the old photo.
        _forget(image_key)
    return True


def _is_external(product: Product) -> bool:
    return product.image.startswith(("http://", "https://"))


def ensure_web_copies(products: list[Product]) -> int:
    """Create missing web copies for `products`; returns how many were made."""
    known = _known()
    if known is None:
        return 0
    made = 0
    for product in products:
        if _is_external(product):
            continue
        key = object_key(product)
        if web_key(key) in known or key in _failed:
            continue
        data = get_image_bytes(product)
        if data and _publish(key, data):
            made += 1
        else:
            _failed.add(key)
    if made:
        logger.info("Made %d web photo copy(ies)", made)
    return made


def web_image_url(product: Product) -> str | None:
    """Public URL of the product's web copy, or None when there isn't one."""
    base = public_base()
    if not base or _is_external(product):
        return None
    key = web_key(object_key(product))
    version = (_known() or {}).get(key)
    if version is None:
        return None
    return f"{base}/{key}?v={version}"


def site_image_url(product: Product, fallback_version: int) -> str | None:
    """Photo URL for the website: the web copy, else the versioned original.

    Originals are overwritten under the same key, so they get the publish
    time as a cache-buster; web copies already carry their own version.
    """
    url = web_image_url(product)
    if url:
        return url
    url = image_url(product)
    if url:
        url = f"{url}{'&' if '?' in url else '?'}v={fallback_version}"
    return url
