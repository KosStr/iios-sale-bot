# IIOS Store — Telegram Bot

A Telegram bot that sells phones, watches, headphones, laptops and accessories. Customers browse a filtered catalog, view product cards (with photos from Cloudflare R2), manage a cart, place orders and make reservations. Ukrainian interface. Built with [python-telegram-bot](https://python-telegram-bot.org/) (async).

## Features

- 🛍 Catalog with categories (📱 смартфони, ⌚ годинники, 🎧 навушники, 💻 ноутбуки, 🔌 аксесуари)
- 🔍 Filter by category, currency (UAH/USD) and price range
- 🔥 Time-limited discounts (sale price + live countdown)
- 📱 Product cards with photos served from Cloudflare R2
- 🛒 In-memory shopping cart (add / remove / clear)
- 🧾 Guided checkout (name → phone → address → confirm)
- 📅 Reservations ("Забронювати") for any model
- 📞 Contacts and 📍 location (map pin)
- 🔔 Optional order/booking notifications to admin chats

## Project structure

```
store/
├── __main__.py           # Entry point — `python -m store`
├── bot.py                # Application setup, command & callback routing
├── config.py             # Loads/validates environment variables
├── keyboards.py          # Reply & inline keyboards
├── data/
│   └── products.py       # Catalog + time-limited discount fields
├── handlers/
│   ├── catalog.py        # Catalog list & product cards (photos)
│   ├── cart.py           # Cart actions
│   ├── checkout.py       # Checkout conversation
│   ├── booking.py        # Reservation conversation
│   ├── filters.py        # Category / currency / price filter UI
│   └── info.py           # Contacts & location
├── services/
│   ├── cart.py           # Cart service (SQLite-backed)
│   ├── catalog_filter.py # Filtering, currency conversion, pricing
│   ├── grouping.py       # Product variant grouping
│   └── images.py         # Cloudflare R2 image resolution
├── db/
│   ├── connection.py     # SQLite pool (WAL, configurable path)
│   ├── schema.py         # Tables and indexes
│   ├── init_db.py        # Startup initialization
│   ├── seed.py           # Seed catalog on first run
│   ├── products_repo.py  # Product queries
│   ├── cart_repo.py      # Cart persistence
│   └── orders_repo.py    # Orders and bookings
├── models/
│   └── cart.py           # Cart domain models
└── utils/
    ├── format.py         # Text/price/discount formatting
    └── tg.py             # Message edit/resend helpers (text ↔ photo)
scripts/
└── upload_images.py      # Upload local images/ folder to R2
Dockerfile, .dockerignore, fly.toml   # Fly.io deployment
```

## Local development

### 1. Prerequisites

- [Python](https://www.python.org/) 3.10 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### 2. Virtual environment & dependencies

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in at least `BOT_TOKEN`. Optional: `DATABASE_PATH` (defaults to `data/store.db`). R2 variables are optional — without them, products simply show without photos.

> Tip: get your Telegram user ID from [@userinfobot](https://t.me/userinfobot) to use in `ADMIN_CHAT_IDS`.

### 4. Run

```bash
python -m store
```

## Cloudflare R2 images

Product image object keys default to `<product_id>.jpg` (e.g. `iphone-15-pro.jpg`). You can also set a full URL or a custom key in a product's `image` field.

### Create the bucket

1. Cloudflare dashboard → **R2** → **Create bucket** (e.g. `iios-store-images`).
2. Choose how images are served:
   - **Public (simplest):** enable the bucket's public **r2.dev** URL or attach a custom domain, then set `R2_PUBLIC_BASE_URL` (e.g. `https://pub-xxxx.r2.dev`). Telegram fetches images directly by URL.
   - **Private:** create an **R2 API token** (Account → R2 → Manage API Tokens) and set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. The bot pulls bytes via the S3 API.

### Upload images

Put files named after product IDs into an `images/` folder and run:

```bash
python -m scripts.upload_images           # uploads ./images
python -m scripts.upload_images ./pics    # or a custom folder
```

(Requires the private R2 variables to be set.)

## Deploy to Fly.io

**Full step-by-step guide:** see **[DEPLOY.md](DEPLOY.md)** (volume, secrets, R2, troubleshooting).

Quick summary:

### 1. Install & sign in

```bash
# Install flyctl: https://fly.io/docs/flyctl/install/
fly auth login
```

### 2. Create the app

From the project folder (a `fly.toml` is already included):

```bash
fly launch --no-deploy
```

Accept reusing the existing `fly.toml`. Pick a unique app name and a region (e.g. `waw`). Decline databases — this bot doesn't need them.

### 3. Create a persistent volume (SQLite)

The bot stores products, carts, orders and bookings in **SQLite** on a Fly Volume so data survives restarts:

```bash
fly volumes create store_data --size 1 --region waw
```

`fly.toml` already mounts it at `/data` and sets `DATABASE_PATH=/data/store.db`.

### 4. Set secrets

Never put secrets in `fly.toml`. Set them with `fly secrets`:

```bash
fly secrets set BOT_TOKEN=123456789:your-token
fly secrets set ADMIN_CHAT_IDS=111111111

# R2 — public mode:
fly secrets set R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev
# …or R2 — private mode:
fly secrets set R2_ACCOUNT_ID=xxxx R2_ACCESS_KEY_ID=xxxx \
                R2_SECRET_ACCESS_KEY=xxxx R2_BUCKET=iios-store-images
```

### 5. Deploy

```bash
fly deploy
fly logs
```

This bot uses **webhooks** on Fly.io (Telegram POSTs updates to `https://<app>.fly.dev/webhook`). Local dev uses **polling** when `USE_WEBHOOK=false` in `.env`.

> Do not run local polling with the same bot token while Fly is live — it removes the production webhook. Redeploy with `fly deploy` to restore it.

### 6. Logs & status

```bash
fly logs
fly status
```

## Database (SQLite)

Persistent storage uses **SQLite** with WAL mode and a small connection pool.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/store.db` | Path to the SQLite file |
| `DATABASE_POOL_SIZE` | `5` | Connection pool size |

**Locally:** the file is created under `data/store.db` on first run.

**On Fly.io:** mount a volume at `/data` and set `DATABASE_PATH=/data/store.db` (already in `fly.toml`).

On startup the bot:
1. Creates the connection pool and ensures the parent directory exists
2. Applies schema, indexes, and foreign keys
3. Seeds the catalog from `store/data/products.py` if the products table is empty

**Tables:** `products`, `cart_items`, `orders`, `order_items`, `bookings`

**Indexes:** category, product group, cart user id, order/booking user id and created_at, etc.

Carts survive restarts; confirmed orders and bookings are persisted.

## How it works

- **Catalog** is seeded into SQLite from `store/data/products.py` on first run, then read from the database. Edit products in code and re-seed, or add admin tooling later.
- **Filtering & pricing** is in `store/services/catalog_filter.py` (USD→UAH rate is configurable there).
- **Images** are resolved in `store/services/images.py`; the bot falls back to text if an image is missing.
- **Cart / orders / bookings** are stored in SQLite (`store/db/`).

## License

MIT
