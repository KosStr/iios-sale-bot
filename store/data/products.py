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


# Reference moment used to set the demo sales below relative to startup.
_NOW = datetime.now()


PRODUCTS: list[Product] = [
    # ── iPhone 17 ─────────────────────────────────────────────────────────────
    Product(
        id="iphone-17-128-black",
        brand="Apple",
        name="iPhone 17",
        price=899,
        storage="128GB",
        color="Black",
        stock=8,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_17,
        group="iPhone 17",
        description="Чип A19, тонкий алюмінієвий корпус, Camera Control і 48 Мп камера.",
    ),
    Product(
        id="iphone-17-256-white",
        brand="Apple",
        name="iPhone 17",
        price=1009,
        storage="256GB",
        color="White",
        stock=5,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_17,
        group="iPhone 17",
        description="Чип A19, тонкий алюмінієвий корпус, Camera Control і 48 Мп камера.",
    ),
    Product(
        id="iphone-17-pro-256-titanium",
        brand="Apple",
        name="iPhone 17 Pro",
        price=1199,
        storage="256GB",
        color="Natural Titanium",
        stock=4,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_17,
        group="iPhone 17 Pro",
        description="Чип A19 Pro, титановий корпус, 5× оптичний зум та ProMotion 120 Гц.",
    ),
    Product(
        id="iphone-17-pro-max-512-desert",
        brand="Apple",
        name="iPhone 17 Pro Max",
        price=1399,
        storage="512GB",
        color="Desert Titanium",
        stock=3,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_17,
        group="iPhone 17 Pro Max",
        description="Найбільший екран 6.9\", A19 Pro, батарея на цілий день і 5× зум.",
    ),
    # ── iPhone 16 ─────────────────────────────────────────────────────────────
    Product(
        id="iphone-16-128-black",
        brand="Apple",
        name="iPhone 16",
        price=799,
        storage="128GB",
        color="Black",
        stock=14,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16",
        description="Чип A18, Camera Control, 48 Мп камера та підтримка Apple Intelligence.",
    ),
    Product(
        id="iphone-16-128-teal",
        brand="Apple",
        name="iPhone 16",
        price=799,
        storage="128GB",
        color="Teal",
        stock=9,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16",
        description="Чип A18, Camera Control, 48 Мп камера та підтримка Apple Intelligence.",
    ),
    Product(
        id="iphone-16-256-pink",
        brand="Apple",
        name="iPhone 16",
        price=909,
        storage="256GB",
        color="Pink",
        stock=6,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16",
        description="Чип A18, Camera Control, 48 Мп камера та підтримка Apple Intelligence.",
    ),
    Product(
        id="iphone-16-pro-256-black",
        brand="Apple",
        name="iPhone 16 Pro",
        price=999,
        storage="256GB",
        color="Black Titanium",
        stock=10,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16 Pro",
        description="Чип A18 Pro, 5× зум, ProMotion 120 Гц і титановий корпус.",
        sale_price=949,
        sale_until=_NOW + timedelta(days=3),
    ),
    Product(
        id="iphone-16-pro-256-white",
        brand="Apple",
        name="iPhone 16 Pro",
        price=999,
        storage="256GB",
        color="White Titanium",
        stock=7,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16 Pro",
        description="Чип A18 Pro, 5× зум, ProMotion 120 Гц і титановий корпус.",
    ),
    Product(
        id="iphone-16-pro-max-256-black",
        brand="Apple",
        name="iPhone 16 Pro Max",
        price=1199,
        storage="256GB",
        color="Black Titanium",
        stock=5,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_16,
        group="iPhone 16 Pro Max",
        description="Екран 6.9\", A18 Pro, найдовша автономність в лінійці та 5× зум.",
    ),
    # ── iPhone 15 ─────────────────────────────────────────────────────────────
    Product(
        id="iphone-15-pro",
        brand="Apple",
        name="iPhone 15 Pro",
        price=899,
        storage="256GB",
        color="Natural Titanium",
        stock=12,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_15,
        group="iPhone 15 Pro",
        description="Чип A17 Pro, 6.1\" Super Retina XDR, титановий корпус і Pro-камери.",
    ),
    Product(
        id="iphone-15-pro-black",
        brand="Apple",
        name="iPhone 15 Pro",
        price=899,
        storage="256GB",
        color="Black Titanium",
        stock=8,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_15,
        group="iPhone 15 Pro",
        description="Чип A17 Pro, 6.1\" Super Retina XDR, титановий корпус і Pro-камери.",
    ),
    Product(
        id="iphone-15-128-black",
        brand="Apple",
        name="iPhone 15",
        price=699,
        storage="128GB",
        color="Black",
        stock=15,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_15,
        group="iPhone 15",
        description="Чип A16 Bionic, Dynamic Island, 48 Мп камера і USB-C.",
    ),
    Product(
        id="iphone-15-128-blue",
        brand="Apple",
        name="iPhone 15",
        price=699,
        storage="128GB",
        color="Blue",
        stock=11,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_15,
        group="iPhone 15",
        description="Чип A16 Bionic, Dynamic Island, 48 Мп камера і USB-C.",
    ),
    Product(
        id="iphone-15-256-pink",
        brand="Apple",
        name="iPhone 15",
        price=809,
        storage="256GB",
        color="Pink",
        stock=6,
        category=CATEGORY_PHONE,
        subcategory=SUBCATEGORY_IPHONE_15,
        group="iPhone 15",
        description="Чип A16 Bionic, Dynamic Island, 48 Мп камера і USB-C.",
        sale_price=759,
        sale_until=_NOW + timedelta(days=1),
    ),
    # ── iPhone 13 (без підкатегорії) ──────────────────────────────────────────
    Product(
        id="iphone-13-128-midnight",
        brand="Apple",
        name="iPhone 13",
        price=479,
        storage="128GB",
        color="Midnight",
        stock=10,
        category=CATEGORY_PHONE,
        group="iPhone 13",
        description="Чип A15 Bionic, 6.1\" Super Retina XDR і надійна автономність.",
    ),
    Product(
        id="iphone-13-256-starlight",
        brand="Apple",
        name="iPhone 13",
        price=549,
        storage="256GB",
        color="Starlight",
        stock=7,
        category=CATEGORY_PHONE,
        group="iPhone 13",
        description="Чип A15 Bionic, 6.1\" Super Retina XDR і надійна автономність.",
    ),
    # ── Годинники ─────────────────────────────────────────────────────────────
    Product(
        id="apple-watch-ultra-2",
        brand="Apple",
        name="Apple Watch Ultra 2",
        price=799,
        storage="49mm",
        color="Natural Titanium",
        stock=6,
        category=CATEGORY_WATCH,
        description="Титановий корпус, GPS L5, 60 годин автономності та яскравість 3000 нт.",
    ),
    Product(
        id="apple-watch-10",
        brand="Apple",
        name="Apple Watch Series 10",
        price=399,
        storage="46mm",
        color="Jet Black",
        stock=14,
        category=CATEGORY_WATCH,
        description="Найтонший Apple Watch, великий екран, швидка зарядка та sleep apnea.",
    ),
    Product(
        id="apple-watch-9",
        brand="Apple",
        name="Apple Watch Series 9",
        price=349,
        storage="45mm",
        color="Midnight",
        stock=15,
        category=CATEGORY_WATCH,
        description="Чип S9, Double Tap, яскравий дисплей та датчики здоров'я.",
        sale_price=299,
        sale_until=_NOW + timedelta(hours=18),
    ),
    Product(
        id="apple-watch-se-2",
        brand="Apple",
        name="Apple Watch SE 2",
        price=249,
        storage="40mm",
        color="Starlight",
        stock=20,
        category=CATEGORY_WATCH,
        description="Найдоступніший Apple Watch з GPS, датчиком серця та crash detection.",
    ),
    # ── Навушники ─────────────────────────────────────────────────────────────
    Product(
        id="airpods-4",
        brand="Apple",
        name="AirPods 4",
        price=129,
        storage="—",
        color="White",
        stock=30,
        category=CATEGORY_HEADPHONES,
        description="Новий дизайн без ніжки, H2 чип, адаптивний звук і USB-C кейс.",
    ),
    Product(
        id="airpods-pro-2",
        brand="Apple",
        name="AirPods Pro 2 (USB-C)",
        price=249,
        storage="ANC",
        color="White",
        stock=25,
        category=CATEGORY_HEADPHONES,
        description="Активне шумопоглинання, адаптивний звук, hearing aid і USB-C.",
    ),
    Product(
        id="airpods-max-midnight",
        brand="Apple",
        name="AirPods Max",
        price=549,
        storage="ANC",
        color="Midnight",
        stock=8,
        category=CATEGORY_HEADPHONES,
        description="Накладні навушники з ANC, просторовим звуком і плетеним кейсом.",
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
        description="Топове шумопоглинання, до 30 годин роботи та чистий звук.",
        sale_price=299,
        sale_until=_NOW + timedelta(days=2),
    ),
    # ── MacBook ───────────────────────────────────────────────────────────────
    Product(
        id="macbook-air-13-m4",
        brand="Apple",
        name="MacBook Air 13 M4",
        price=1099,
        storage="16GB / 256GB",
        color="Sky Blue",
        stock=8,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        group="MacBook Air 13 M4",
        description="Чип Apple M4, 13.6\" Liquid Retina, до 18 годин автономності.",
    ),
    Product(
        id="macbook-air-13-m4-midnight",
        brand="Apple",
        name="MacBook Air 13 M4",
        price=1099,
        storage="16GB / 256GB",
        color="Midnight",
        stock=5,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        group="MacBook Air 13 M4",
        description="Чип Apple M4, 13.6\" Liquid Retina, до 18 годин автономності.",
    ),
    Product(
        id="macbook-air-m3",
        brand="Apple",
        name="MacBook Air 13 M3",
        price=999,
        storage="16GB / 512GB",
        color="Midnight",
        stock=6,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        description="Чип Apple M3, 13.6\" Liquid Retina, до 18 годин автономності.",
        sale_price=949,
        sale_until=_NOW + timedelta(days=5),
    ),
    Product(
        id="macbook-air-15-m3",
        brand="Apple",
        name="MacBook Air 15 M3",
        price=1299,
        storage="16GB / 512GB",
        color="Starlight",
        stock=4,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        description="Найбільший MacBook Air: 15.3\" Liquid Retina, M3 і до 18 годин роботи.",
    ),
    Product(
        id="macbook-pro-14-m4",
        brand="Apple",
        name="MacBook Pro 14 M4",
        price=1599,
        storage="24GB / 512GB",
        color="Space Black",
        stock=5,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        description="Чип M4, 14.2\" Liquid Retina XDR, ProMotion 120 Гц і MagSafe.",
    ),
    Product(
        id="macbook-pro-16-m4-pro",
        brand="Apple",
        name="MacBook Pro 16 M4 Pro",
        price=2499,
        storage="48GB / 512GB",
        color="Space Black",
        stock=3,
        category=CATEGORY_LAPTOP,
        subcategory=SUBCATEGORY_MACBOOK_M,
        description="M4 Pro, 16.2\" XDR 120 Гц, до 24 годин автономності та HDMI 2.1.",
    ),
    # ── iPad ──────────────────────────────────────────────────────────────────
    Product(
        id="ipad-pro-13-m4-256",
        brand="Apple",
        name="iPad Pro 13 M4",
        price=1299,
        storage="256GB",
        color="Silver",
        stock=5,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_PRO,
        group="iPad Pro 13 M4",
        description="Найтонший Apple продукт: OLED Ultra Retina XDR, M4 та Apple Pencil Pro.",
    ),
    Product(
        id="ipad-pro-11-m4-256",
        brand="Apple",
        name="iPad Pro 11 M4",
        price=999,
        storage="256GB",
        color="Space Black",
        stock=7,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_PRO,
        group="iPad Pro 11 M4",
        description="OLED екран 11\", чип M4, Tandem OLED технологія та USB 4.",
    ),
    Product(
        id="ipad-air-13-m2-256",
        brand="Apple",
        name="iPad Air 13 M2",
        price=799,
        storage="256GB",
        color="Blue",
        stock=8,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_AIR,
        group="iPad Air 13 M2",
        description="Великий 13\" Liquid Retina, чип M2 та підтримка Apple Pencil Pro.",
    ),
    Product(
        id="ipad-air-11-m2-128",
        brand="Apple",
        name="iPad Air 11 M2",
        price=599,
        storage="128GB",
        color="Starlight",
        stock=10,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_AIR,
        group="iPad Air 11 M2",
        description="11\" Liquid Retina, чип M2, USB-C та підтримка Apple Pencil Pro.",
    ),
    Product(
        id="ipad-mini-7-128",
        brand="Apple",
        name="iPad mini 7",
        price=499,
        storage="128GB",
        color="Purple",
        stock=12,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_MINI,
        description="8.3\" Liquid Retina, чип A17 Pro, Apple Intelligence та USB-C.",
    ),
    Product(
        id="ipad-10-64",
        brand="Apple",
        name="iPad 10",
        price=349,
        storage="64GB",
        color="Yellow",
        stock=18,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_BASE,
        group="iPad 10",
        description="10.9\" Liquid Retina, чип A14 Bionic, Touch ID зверху та USB-C.",
    ),
    Product(
        id="ipad-10-256",
        brand="Apple",
        name="iPad 10",
        price=479,
        storage="256GB",
        color="Silver",
        stock=9,
        category=CATEGORY_IPAD,
        subcategory=SUBCATEGORY_IPAD_BASE,
        group="iPad 10",
        description="10.9\" Liquid Retina, чип A14 Bionic, Touch ID зверху та USB-C.",
    ),
    # ── Аксесуари ─────────────────────────────────────────────────────────────
    Product(
        id="magsafe-charger-15w",
        brand="Apple",
        name="MagSafe зарядний пристрій 25W",
        price=45,
        storage="25W",
        color="White",
        stock=40,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CHARGER,
        description="Офіційний MagSafe для iPhone 12+, до 25 Вт бездротової зарядки.",
    ),
    Product(
        id="anker-charger-65w",
        brand="Anker",
        name="Зарядний пристрій Anker 65W",
        price=39,
        storage="65W",
        color="White",
        stock=50,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CHARGER,
        description="Компактний GaN на 3 порти (2×USB-C + USB-A) для телефонів і ноутбуків.",
    ),
    Product(
        id="spigen-case-iphone-16",
        brand="Spigen",
        name="Чохол Spigen Ultra Hybrid iPhone 16",
        price=22,
        storage="—",
        color="Crystal Clear",
        stock=45,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CASE,
        description="Прозорий PC + TPU, жовтіє повільніше та захищає кути від ударів.",
    ),
    Product(
        id="spigen-case",
        brand="Spigen",
        name="Чохол Spigen Rugged Armor iPhone 15",
        price=19,
        storage="—",
        color="Matte Black",
        stock=20,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CASE,
        description="Захисний чохол із поглинанням ударів та матовим покриттям.",
    ),
    Product(
        id="anker-powercore-20k",
        brand="Anker",
        name="Anker PowerCore 20K",
        price=49,
        storage="20 000 mAh",
        color="Black",
        stock=30,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_POWERBANK,
        description="20 000 mAh, два USB-порти та швидка зарядка Power Delivery 22.5W.",
    ),
    Product(
        id="anker-powercore-10k",
        brand="Anker",
        name="Anker PowerCore 10K",
        price=29,
        storage="10 000 mAh",
        color="Black",
        stock=35,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_POWERBANK,
        description="Компактний павербанк 10 000 mAh із USB-C та USB-A виходами.",
    ),
    Product(
        id="usb-c-cable-2m",
        brand="Baseus",
        name="Кабель USB-C 2 м",
        price=15,
        storage="2 m",
        color="Black",
        stock=40,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CABLE,
        description="Нейлоновий USB-C — USB-C, 100W PD, для зарядки та передачі даних.",
    ),
    Product(
        id="lightning-usbc-cable",
        brand="Baseus",
        name="Кабель Lightning — USB-C 1 м",
        price=12,
        storage="1 m",
        color="White",
        stock=30,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_CABLE,
        description="Швидка зарядка 20W для iPhone 8–14 через адаптер USB-C.",
    ),
    Product(
        id="screen-guard-iphone-16",
        brand="ESR",
        name="Захисне скло iPhone 16",
        price=13,
        storage="6.1\"",
        color="Clear",
        stock=50,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_SCREEN_GUARD,
        description="Загартоване скло 9H, oleophobic-покриття, сумісне з Face ID.",
    ),
    Product(
        id="screen-guard-iphone-15",
        brand="ESR",
        name="Захисне скло iPhone 15",
        price=12,
        storage="6.1\"",
        color="Clear",
        stock=35,
        category=CATEGORY_ACCESSORIES,
        subcategory=SUBCATEGORY_SCREEN_GUARD,
        description="Скло 9H з oleophobic-покриттям та повною сумісністю з Face ID.",
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
