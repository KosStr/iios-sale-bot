"""Seed the database from the built-in catalog when empty."""

from __future__ import annotations

import logging
import sqlite3

from store.data.products import PRODUCTS

logger = logging.getLogger(__name__)

# Products removed from the built-in catalog (cleaned up on startup).
DISCONTINUED_PRODUCT_IDS = (
    "samsung-s24-ultra",
    "pixel-8-pro",
    "xiaomi-14",
)

_INSERT = """
INSERT OR IGNORE INTO products (
    id, brand, name, price, storage, color, stock, description,
    category, subcategory, image, product_group, sale_price, sale_until
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _product_row(product) -> tuple:
    sale_until = (
        product.sale_until.isoformat(timespec="seconds")
        if product.sale_until
        else None
    )
    return (
        product.id,
        product.brand,
        product.name,
        product.price,
        product.storage,
        product.color,
        product.stock,
        product.description,
        product.category,
        product.subcategory,
        product.image,
        product.group,
        product.sale_price,
        sale_until,
    )


def seed_products(conn: sqlite3.Connection) -> int:
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count > 0:
        logger.info("Products table already has %d row(s); skipping seed.", count)
        return 0

    rows = [_product_row(product) for product in PRODUCTS]

    conn.executemany(_INSERT, rows)
    logger.info("Seeded %d product(s) into the database.", len(rows))
    return len(rows)


def sync_missing_products(conn: sqlite3.Connection) -> int:
    """Insert catalog products that are not yet in the database."""
    existing = {row[0] for row in conn.execute("SELECT id FROM products").fetchall()}
    missing = [product for product in PRODUCTS if product.id not in existing]
    if not missing:
        return 0

    rows = [_product_row(product) for product in missing]
    conn.executemany(_INSERT, rows)
    logger.info("Added %d missing product(s) from catalog.", len(rows))
    return len(rows)


def sync_catalog_fields(conn: sqlite3.Connection) -> None:
    """Update category/subcategory for catalog products already in the database."""
    conn.executemany(
        """
        UPDATE products
        SET category = ?, subcategory = ?
        WHERE id = ?
        """,
        [(product.category, product.subcategory, product.id) for product in PRODUCTS],
    )


def remove_discontinued_products(conn: sqlite3.Connection) -> int:
    """Remove demo products that are no longer in the catalog."""
    removed = 0
    for product_id in DISCONTINUED_PRODUCT_IDS:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        removed += cur.rowcount
    if removed:
        logger.info("Removed %d discontinued product(s) from the database.", removed)
    return removed
