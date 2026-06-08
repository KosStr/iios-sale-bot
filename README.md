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
│   ├── cart.py           # In-memory cart store
│   ├── catalog_filter.py # Filtering, currency conversion, pricing
│   └── images.py         # Cloudflare R2 image resolution
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

Fill in at least `BOT_TOKEN`. R2 variables are optional — without them, products simply show without photos.

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

### 3. Set secrets

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

### 4. Deploy & keep exactly one machine

This bot uses **long polling**, so Telegram allows only **one** running instance. Ensure Fly runs a single machine:

```bash
fly deploy
fly scale count 1
```

> Running 2+ machines causes a `409 Conflict` (two pollers). Keep the count at 1. (If you later switch to webhooks, you can scale out.)

### 5. Logs & status

```bash
fly logs
fly status
```

## How it works

- **Catalog/discounts** live in `store/data/products.py`. Each product can carry a `sale_price` + `sale_until` for a time-limited discount; the sale price is used everywhere until it expires. Swap this module for a DB later (keep the helper functions).
- **Filtering & pricing** is in `store/services/catalog_filter.py` (USD→UAH rate is configurable there).
- **Images** are resolved in `store/services/images.py`; the bot falls back to text if an image is missing.
- **Cart** is in memory (`store/services/cart.py`) keyed by user id — back it with Redis/DB for production.

## License

MIT
