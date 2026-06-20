"""Initialize the SQLite database: pool, schema, and seed data."""

from __future__ import annotations

import logging
import os

from store.db.connection import db_connection, init_pool
from store.db.schema import apply_schema
from store.db.seed import (
    remove_discontinued_products,
    seed_products,
    sync_catalog_fields,
    sync_missing_products,
)

logger = logging.getLogger(__name__)


def init_database(path: str | None = None) -> None:
    """Create the connection pool, apply schema/indexes, and seed if empty."""
    db_path = path or os.getenv("DATABASE_PATH", "data/store.db")
    init_pool(db_path)
    with db_connection() as conn:
        apply_schema(conn)
        seed_products(conn)
        sync_missing_products(conn)
        sync_catalog_fields(conn)
        remove_discontinued_products(conn)
    logger.info("Database initialized at %s", db_path)
