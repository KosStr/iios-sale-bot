# IIOS Store — Telegram Bot

A Telegram bot for a shop selling used and new Apple devices (iPhone, iPad, Apple Watch, AirPods, MacBook) and accessories. Customers browse a filtered catalog, open product cards with photos, fill a cart and place orders. Admins manage the catalog from inside the bot, and the bot keeps a Telegram channel and a landing page in sync. Ukrainian interface. Built with [python-telegram-bot](https://python-telegram-bot.org/) 22 (async), SQLite and Cloudflare R2.

## Features

**For customers**

- 🛍 Catalog wizard: category → subcategory → price range («менше/більше» the average price, offered once a selection has 5+ products)
- 📦 Variants of one model (e.g. iPhone 13 128GB / 256GB) collapse into a single catalog row
- 📱 Product cards with photos from Cloudflare R2, falling back to text when there is no photo
- 💰 Prices in UAH, USD or both; 🔥 sale prices shown struck-through everywhere
- 🛒 Persistent cart (SQLite) with a live count on the menu button
- 🧾 Guided checkout: name → phone → address (optional) → confirm
- 📞 Contacts and 📍 location screens (values from env vars)
- 🔗 Deep links from the landing page: `?start=cat_<category>` opens a category, `?start=prod_<id>` opens a product

**For admins** (Telegram user IDs listed in `ADMIN_CHAT_IDS`)

- ➕ `/add` — step-by-step wizard (category, name, ID, model, specs, prices, warranty, condition, stock, photo)
- 📋 `/products` — paginated list, edit any field, change category, delete (with a force-delete for products referenced by orders), bulk-delete sold-out products
- 🔥 `/hot` — hot deals published to the landing page as `hot.json`
- 🔔 New-order alerts to every admin and, optionally, to a separate `NOTIFY_CHAT_ID`

**Channel auto-posting** (when `CHANNEL_ID` is set)

- New products are posted to the channel (accessories are never posted)
- Edits update the post; a new photo replaces the post's photo
- Sold-out or deleted products have their post deleted. Telegram doesn't let bots delete posts older than 48 h, so those are marked «❌ ПРОДАНО» and the admin gets the link to remove them by hand

## Project structure

```
store/
├── __main__.py            # Entry point — `python -m store` (webhook or polling)
├── bot.py                 # Application setup, command/button/callback routing, deep links
├── config.py              # Environment variables → Config
├── startup.py             # Fail-fast checks (token, DB directory) before serving
├── keyboards.py           # Reply & inline keyboards for customers
├── data/
│   └── products.py        # Product model, pricing helpers, optional seed catalog
├── handlers/
│   ├── catalog.py         # Catalog results & product cards
│   ├── filters.py         # Category / subcategory / price wizard
│   ├── cart.py            # Cart actions
│   ├── checkout.py        # Checkout conversation
│   ├── booking.py         # Reservation conversation (not linked from any button — see below)
│   ├── info.py            # Contacts & location
│   ├── admin_add.py       # /add wizard
│   ├── admin_products.py  # /products, /hot: list, edit, delete
│   └── admin_ui.py        # Admin texts & keyboards
├── services/
│   ├── catalog_filter.py  # Categories, subcategories, filtering, price ranges
│   ├── grouping.py        # Model/variant grouping
│   ├── cart.py            # Cart service (SQLite-backed)
│   ├── images.py          # R2 image URLs, downloads, uploads
│   ├── channel_sync.py    # Channel post create/edit/delete
│   └── hot_deals.py       # hot.json for the landing page
├── db/
│   ├── connection.py      # SQLite pool (WAL)
│   ├── schema.py          # Tables, indexes, column migrations
│   ├── init_db.py         # Startup initialization
│   ├── seed.py            # Seed/cleanup of the built-in catalog
│   ├── products_repo.py   # Product queries
│   ├── cart_repo.py       # Cart persistence
│   └── orders_repo.py     # Orders and bookings
├── models/
│   └── cart.py            # Cart / CartItem
└── utils/
    ├── admin.py           # Admin check, admin/order notifications
    ├── format.py          # Product card, cart and price formatting
    ├── tg.py              # Edit-or-resend helpers (text ↔ photo messages)
    └── throttle.py        # Per-user lock for callback handlers
scripts/
└── upload_images.py       # Bulk-upload a local folder of images to R2
index.html                 # Landing page (reads hot.json from R2)
images/                    # Landing page images
Dockerfile, fly.toml       # Fly.io deployment
.github/workflows/         # Auto-deploy to Fly.io on push to main
```

## Local development

### 1. Prerequisites

- [Python](https://www.python.org/) 3.10 or newer (the Docker image uses 3.12)
- A Telegram bot token from [@BotFather](https://t.me/BotFather). Use a **separate test bot** locally: polling with the production token removes the production webhook.

### 2. Virtual environment & dependencies

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell) — or run setup.ps1, which does all of this
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in at least `BOT_TOKEN`, and add your own Telegram user ID to `ADMIN_CHAT_IDS` (get it from [@userinfobot](https://t.me/userinfobot)) to use `/add`. Everything else is optional; see the table below.

### 4. Run

```bash
python -m store
```

The catalog starts empty — add products with `/add` (or the «➕ Додати товар» button).

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `BOT_TOKEN` | — (required) | Token from BotFather |
| `ADMIN_CHAT_IDS` | empty | Comma-separated Telegram user IDs with admin access; they also get order alerts |
| `NOTIFY_CHAT_ID` | empty | Extra chat that gets order alerts without admin access |
| `CHANNEL_ID` | empty | `@channel` or `-100…` ID for auto-posting; the bot must be a channel admin with Post/Edit/Delete rights |
| `DATABASE_PATH` | `data/store.db` | SQLite file |
| `DATABASE_POOL_SIZE` | `5` | SQLite connection pool size |
| `USE_WEBHOOK` | on when a webhook URL is known | `false` → long polling (local dev) |
| `WEBHOOK_URL` | `https://$FLY_APP_NAME.fly.dev/<path>` on Fly | Public webhook URL |
| `WEBHOOK_PATH` | `/webhook` | Webhook path |
| `WEBHOOK_SECRET` | empty | Checked against Telegram's `X-Telegram-Bot-Api-Secret-Token` header |
| `PORT` / `WEBHOOK_LISTEN` | `8080` / `0.0.0.0` | Webhook server bind |
| `STORE_NAME`, `STORE_PHONE`, `STORE_TELEGRAM`, `STORE_MANAGER`, `STORE_INSTAGRAM`, `STORE_INSTAGRAM2` | IIOS values | Contacts screen, product cards, channel posts |
| `STORE_ADDRESS`, `STORE_MAP_URL` | IIOS values | Location screen |
| `R2_PUBLIC_BASE_URL` | empty | Public bucket URL; Telegram and the landing page load photos from it |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | empty | R2 API access; needed for photo uploads in `/add`, private-bucket downloads, and `hot.json` |
| `HOT_DEALS_KEY` | `hot.json` | Object key of the landing-page deals file |
| `CURRENCY` | `UAH` | Only logged at startup; it doesn't change what the bot shows |

## Cloudflare R2 images

A product's photo is the R2 object `<product_id>.jpg` unless its `image` field holds another key or a full URL. Photos sent to `/add` or the ✏️ «Фото» edit are uploaded automatically (needs the API credentials).

- **Public bucket:** enable the r2.dev URL or a custom domain and set `R2_PUBLIC_BASE_URL`. Telegram fetches photos by URL.
- **Private bucket:** set the four `R2_*` API variables. The bot downloads the bytes and uploads them to Telegram.

Setting both is the recommended setup: uploads and `hot.json` need the API credentials, and the landing page needs public photo URLs.

To bulk-upload a folder of files named after product IDs:

```bash
python -m scripts.upload_images           # uploads ./images
python -m scripts.upload_images ./pics    # or a custom folder
```

## Database (SQLite)

SQLite in WAL mode with a small connection pool. Tables: `products`, `cart_items`, `orders`, `order_items`, `bookings`, `schema_meta`.

On startup the bot creates the pool (and the parent directory), applies the schema with additive column migrations, inserts any products from the built-in `PRODUCTS` list in `store/data/products.py` (currently empty), and deletes the IDs listed in `DISCONTINUED_PRODUCT_IDS` in `store/db/seed.py`.

Carts, orders and bookings persist across restarts. On Fly.io the file lives on a volume mounted at `/data`.

## How it works

- **Prices** — a product has a USD price, a UAH price, or both; they are entered independently (no exchange rate). A sale price is typed in the product's main currency (UAH when set) and the other currency is scaled by the same discount. Catalog price ranges and order totals use the USD price.
- **Catalog filter state** is per user in `context.user_data["filter"]`; the wizard step is `flt["ui"]`.
- **Images** — `store/services/images.py`; R2 downloads and uploads run in a worker thread so they don't block the bot.
- **Channel posts** — `store/services/channel_sync.py`; every failure is logged and never breaks the admin action.
- **Landing page** — `index.html` is a static page. Admin changes to hot products regenerate `hot.json` in R2 (`store/services/hot_deals.py`), so the Fly machine never has to wake up for site visitors.
- **Bookings** — `store/handlers/booking.py` is still registered, but the «Забронювати» button was removed from product cards, so customers can't currently reach it.

## Deploy to Fly.io

See **[DEPLOY.md](DEPLOY.md)** for the full guide (volume, secrets, R2, webhook, troubleshooting). In short:

```bash
fly volumes create store_data --size 1 --region fra   # region = primary_region in fly.toml
fly secrets set BOT_TOKEN=... ADMIN_CHAT_IDS=... WEBHOOK_SECRET=...
fly deploy
```

Pushing to `main` also deploys automatically via `.github/workflows/fly-deploy.yml` (needs the `FLY_API_TOKEN` repository secret).

## License

MIT
