"""Product image storage backed by Cloudflare R2 (S3-compatible).

Two ways to serve images (configure via environment variables):

1. Public bucket / custom domain — set ``R2_PUBLIC_BASE_URL``. Images are
   sent to Telegram by URL (cheapest: Telegram fetches them directly).
2. Private bucket — set ``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``,
   ``R2_SECRET_ACCESS_KEY`` and ``R2_BUCKET``. Image bytes are pulled via the
   S3 API and uploaded to Telegram.

If nothing is configured, products are simply shown without photos.

A product's ``image`` field holds the object key (e.g. ``iphone-15-pro.jpg``)
or a full http(s) URL.
"""

from __future__ import annotations

import functools
import logging
import os

from store.data.products import Product

logger = logging.getLogger(__name__)


def _public_base() -> str:
    return os.getenv("R2_PUBLIC_BASE_URL", "").rstrip("/")


def _private_config() -> dict[str, str]:
    return {
        "account_id": os.getenv("R2_ACCOUNT_ID", ""),
        "access_key": os.getenv("R2_ACCESS_KEY_ID", ""),
        "secret_key": os.getenv("R2_SECRET_ACCESS_KEY", ""),
        "bucket": os.getenv("R2_BUCKET", ""),
    }


def _private_enabled() -> bool:
    return all(_private_config().values())


def _object_key(product: Product) -> str:
    """R2 object key for a product. Defaults to '<id>.jpg' if not set."""
    return product.image or f"{product.id}.jpg"


def image_url(product: Product) -> str | None:
    """Return a public URL for the product image, or None."""
    if product.image and product.image.startswith(("http://", "https://")):
        return product.image
    base = _public_base()
    if base:
        return f"{base}/{_object_key(product)}"
    return None


@functools.lru_cache(maxsize=1)
def _client():
    import boto3  # imported lazily so the bot runs without boto3/R2

    cfg = _private_config()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="auto",
    )


def get_image_bytes(product: Product) -> bytes | None:
    """Fetch image bytes from a private R2 bucket, or None on any failure."""
    if not _private_enabled():
        return None
    key = _object_key(product)
    try:
        obj = _client().get_object(Bucket=_private_config()["bucket"], Key=key)
        return obj["Body"].read()
    except Exception as err:  # noqa: BLE001 - log and fall back to no image
        logger.warning("R2 fetch failed for %s: %s", key, err)
        return None


def photo_source(product: Product):
    """Best available photo for Telegram: a URL (preferred) or raw bytes.

    Returns something accepted by ``Bot.send_photo(photo=...)`` or None.
    """
    url = image_url(product)
    if url:
        return url
    return get_image_bytes(product)
