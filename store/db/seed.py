"""Seed the database from the built-in catalog when empty."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from store.data.products import PRODUCTS

logger = logging.getLogger(__name__)

_INSERT = """
INSERT OR IGNORE INTO products (
    id, brand, name, price, storage, color, stock, description,
    category, image, product_group, sale_price, sale_until
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def seed_products(conn: sqlite3.Connection) -> int:
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count > 0:
        logger.info("Products table already has %d row(s); skipping seed.", count)
        return 0

    rows = []
    for product in PRODUCTS:
        sale_until = (
            product.sale_until.isoformat(timespec="seconds")
            if product.sale_until
            else None
        )
        rows.append(
            (
                product.id,
                product.brand,
                product.name,
                product.price,
                product.storage,
                product.color,
                product.stock,
                product.description,
                product.category,
                product.image,
                product.group,
                product.sale_price,
                sale_until,
            )
        )

    conn.executemany(_INSERT, rows)
    logger.info("Seeded %d product(s) into the database.", len(rows))
    return len(rows)
