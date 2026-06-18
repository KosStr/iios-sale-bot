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
CATEGORY_ACCESSORIES = "accessories"


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
    image: str = ""
    # Products sharing the same non-empty `group` are variants of one model
    # (e.g. "iPhone 13" in 128GB/256GB). Empty means a standalone product.
    group: str = ""
    # Time-limited discount: special price (USD) active until `sale_until`.
    sale_price: int | None = None
    sale_until: datetime | None = None


# Reference moment used to set the demo sales below relative to startup.
_NOW = datetime.now()


PRODUCTS: list[Product] = [
    # --- Смартфони -----------------------------------------------------------
    Product(
        id="iphone-15-pro",
        brand="Apple",
        name="iPhone 15 Pro",
        price=999,
        storage="256GB",
        color="Natural Titanium",
        stock=12,
        category=CATEGORY_PHONE,
        description=(
            "Чип A17 Pro, 6.1\" дисплей Super Retina XDR, титановий корпус "
            "та професійна система камер."
        ),
    ),
    Product(
        id="samsung-s24-ultra",
        brand="Samsung",
        name="Galaxy S24 Ultra",
        price=1199,
        storage="512GB",
        color="Titanium Black",
        stock=8,
        category=CATEGORY_PHONE,
        description=(
            "Snapdragon 8 Gen 3, 6.8\" Dynamic AMOLED 2X, вбудований S Pen "
            "та камера на 200 Мп."
        ),
        sale_price=1099,
        sale_until=_NOW + timedelta(days=2),
    ),
    Product(
        id="pixel-8-pro",
        brand="Google",
        name="Pixel 8 Pro",
        price=899,
        storage="128GB",
        color="Obsidian",
        stock=5,
        category=CATEGORY_PHONE,
        description=(
            "Google Tensor G3, 6.7\" дисплей Super Actua та найкращі "
            "можливості Google AI у камері."
        ),
    ),
    # --- iPhone 13 (grouped model with several variants) ---------------------
    Product(
        id="iphone-13-128-midnight",
        brand="Apple",
        name="iPhone 13",
        price=599,
        storage="128GB",
        color="Midnight",
        stock=10,
        category=CATEGORY_PHONE,
        group="iPhone 13",
        description=(
            "Чип A15 Bionic, 6.1\" Super Retina XDR, подвійна камера "
            "та надійна автономність."
        ),
    ),
    Product(
        id="iphone-13-128-blue",
        brand="Apple",
        name="iPhone 13",
        price=599,
        storage="128GB",
        color="Blue",
        stock=4,
        category=CATEGORY_PHONE,
        group="iPhone 13",
        description=(
            "Чип A15 Bionic, 6.1\" Super Retina XDR, подвійна камера "
            "та надійна автономність."
        ),
    ),
    Product(
        id="iphone-13-256-starlight",
        brand="Apple",
        name="iPhone 13",
        price=699,
        storage="256GB",
        color="Starlight",
        stock=7,
        category=CATEGORY_PHONE,
        group="iPhone 13",
        description=(
            "Чип A15 Bionic, 6.1\" Super Retina XDR, подвійна камера "
            "та надійна автономність."
        ),
    ),
    Product(
        id="xiaomi-14",
        brand="Xiaomi",
        name="Xiaomi 14",
        price=699,
        storage="256GB",
        color="Jade Green",
        stock=20,
        category=CATEGORY_PHONE,
        description=(
            "Snapdragon 8 Gen 3, 6.36\" LTPO AMOLED та потрійна камера, "
            "налаштована Leica."
        ),
    ),
    # --- Годинники -----------------------------------------------------------
    Product(
        id="apple-watch-9",
        brand="Apple",
        name="Apple Watch Series 9",
        price=399,
        storage="45mm",
        color="Midnight",
        stock=15,
        category=CATEGORY_WATCH,
        description=(
            "Чип S9, яскравіший дисплей, жест Double Tap та датчики здоров'я."
        ),
        sale_price=329,
        sale_until=_NOW + timedelta(hours=12),
    ),
    Product(
        id="galaxy-watch-6",
        brand="Samsung",
        name="Galaxy Watch6",
        price=299,
        storage="44mm",
        color="Graphite",
        stock=10,
        category=CATEGORY_WATCH,
        description=(
            "Wear OS, моніторинг сну та складу тіла, тонкі рамки дисплея."
        ),
    ),
    # --- Навушники -----------------------------------------------------------
    Product(
        id="airpods-pro-2",
        brand="Apple",
        name="AirPods Pro 2 (USB-C)",
        price=249,
        storage="ANC",
        color="White",
        stock=25,
        category=CATEGORY_HEADPHONES,
        description=(
            "Активне шумопоглинання, адаптивний звук та зарядка USB-C."
        ),
    ),
    Product(
        id="sony-wh1000xm5",
        brand="Sony",
        name="Sony WH-1000XM5",
        price=349,
        storage="ANC",
        color="Black",
        stock=7,
        category=CATEGORY_HEADPHONES,
        description=(
            "Топове шумопоглинання, до 30 годин роботи та чистий звук."
        ),
        sale_price=299,
        sale_until=_NOW + timedelta(days=2),
    ),
    # --- Ноутбуки ------------------------------------------------------------
    Product(
        id="macbook-air-m3",
        brand="Apple",
        name="MacBook Air 13 M3",
        price=1099,
        storage="16GB / 512GB",
        color="Midnight",
        stock=6,
        category=CATEGORY_LAPTOP,
        description=(
            "Чип Apple M3, 13.6\" Liquid Retina, до 18 годин автономності."
        ),
    ),
    Product(
        id="zenbook-14",
        brand="ASUS",
        name="ASUS ZenBook 14 OLED",
        price=899,
        storage="16GB / 1TB",
        color="Ponder Blue",
        stock=9,
        category=CATEGORY_LAPTOP,
        description=(
            "Intel Core Ultra 7, 14\" OLED 2.8K та легкий металевий корпус."
        ),
    ),
    # --- Аксесуари -----------------------------------------------------------
    Product(
        id="anker-charger-65w",
        brand="Anker",
        name="Зарядний пристрій Anker 65W",
        price=39,
        storage="65W",
        color="White",
        stock=50,
        category=CATEGORY_ACCESSORIES,
        description=(
            "Компактний GaN-зарядний на 3 порти для телефонів і ноутбуків."
        ),
    ),
    Product(
        id="spigen-case",
        brand="Spigen",
        name="Чохол Spigen Rugged Armor",
        price=19,
        storage="—",
        color="Matte Black",
        stock=0,
        category=CATEGORY_ACCESSORIES,
        description=(
            "Захисний чохол із поглинанням ударів та матовим покриттям."
        ),
    ),
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
