# Deploy IIOS Store Bot — step by step

This guide walks you through deploying the Telegram bot to **Fly.io** with:

- persistent **SQLite** on a Fly Volume
- optional **Cloudflare R2** for product images
- store contacts/location from environment variables

---

## Before you start

You will need:

| Item | Where to get it |
|------|-----------------|
| Telegram bot token | [@BotFather](https://t.me/BotFather) → `/newbot` or use an existing bot |
| Fly.io account | [fly.io](https://fly.io) (free tier is enough to start) |
| `flyctl` CLI | [Install flyctl](https://fly.io/docs/flyctl/install/) |
| Git (recommended) | To push code; or deploy from your local folder |

Optional but recommended:

- Your Telegram user ID ([@userinfobot](https://t.me/userinfobot)) for order/booking notifications
- Cloudflare account + R2 bucket for product photos

---

## Part 1 — Prepare the project locally

### Step 1. Open the project folder

```powershell
cd C:\Users\KostiantynStrusovsky\Desktop\pet
```

### Step 2. Verify the bot runs locally (optional but recommended)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m store
```

In Telegram, open your bot and send `/start`. Press **Ctrl+C** to stop.

> **Local dev uses polling** (`USE_WEBHOOK=false` in `.env`).  
> **Production on Fly.io uses webhooks** (`USE_WEBHOOK=true` in `fly.toml`).  
> Do **not** run the bot locally with the **same bot token** while Fly is live — starting local polling calls `deleteWebhook` and breaks production until you redeploy Fly.

### Step 3. Check `fly.toml`

Open `fly.toml`. The default app name is `iios-store-bot`. If that name is already taken on Fly.io, change it:

```toml
app = "your-unique-app-name"
primary_region = "waw"
```

`waw` = Warsaw (good for Ukraine). You can pick another region: `fly platform regions`.

---

## Part 2 — Fly.io: first-time setup

### Step 4. Log in to Fly.io

```powershell
fly auth login
```

This opens a browser to authenticate.

### Step 5. Create the Fly app (first deploy only)

From the project folder:

```powershell
fly launch --no-deploy
```

When prompted:

- **Use existing fly.toml?** → Yes
- **App name** → keep or change to something unique
- **Region** → `waw` (must match the volume region later)
- **Postgres / Redis?** → No
- **Deploy now?** → No (we set secrets and volume first)

If the app already exists, skip this step.

---

## Part 3 — Persistent database (Fly Volume)

The bot stores products, carts, orders and bookings in SQLite at `/data/store.db`. That path must live on a **Fly Volume**, or data is lost on every restart.

### Step 6. Create the volume (once per app)

Use the **same region** as `primary_region` in `fly.toml`:

```powershell
fly volumes create store_data --size 1 --region waw
```

- Name `store_data` must match `source = "store_data"` in `fly.toml`.
- Size `1` GB is enough for a small store; increase later if needed.

Verify:

```powershell
fly volumes list
```

You should see `store_data` in region `waw`.

---

## Part 4 — Secrets and configuration

Never commit secrets to git. Set them on Fly with `fly secrets set`.

### Step 7. Required secret: bot token

```powershell
fly secrets set BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
```

Replace with the token from BotFather.

**Recommended — webhook secret** (Telegram sends this in the `X-Telegram-Bot-Api-Secret-Token` header):

```powershell
fly secrets set WEBHOOK_SECRET="pick-a-long-random-string-here"
```

On Fly, the public webhook URL is built automatically:

`https://<your-app-name>.fly.dev/webhook`

Override with `WEBHOOK_URL` if you use a custom domain:

```powershell
fly secrets set WEBHOOK_URL="https://bot.your-domain.com/webhook"
```

### Step 8. Recommended secrets

**Admin notifications** (your Telegram user ID):

```powershell
fly secrets set ADMIN_CHAT_IDS="123456789"
```

Multiple admins (comma-separated):

```powershell
fly secrets set ADMIN_CHAT_IDS="111111111,222222222"
```

**Store contacts** (shown in the «Контакти» button):

```powershell
fly secrets set `
  STORE_NAME="IIOS Store" `
  STORE_PHONE="+380 99 123 45 67" `
  STORE_EMAIL="info@iios.store" `
  STORE_TELEGRAM="@iios_cv" `
  STORE_INSTAGRAM="@iios.store" `
  STORE_WEBSITE="https://iios.store" `
  STORE_HOURS="Пн–Нд, 10:00–20:00"
```

**Store location** (shown in «Локація»):

```powershell
fly secrets set `
  STORE_ADDRESS="м. Чернівці, вул. Головна, 1" `
  STORE_LATITUDE="48.291839" `
  STORE_LONGITUDE="25.935355"
```

> Non-secret settings like `CURRENCY=UAH` and `DATABASE_PATH=/data/store.db` are already in `fly.toml` under `[env]`.

List current secrets (values are hidden):

```powershell
fly secrets list
```

---

## Part 5 — Cloudflare R2 images (optional)

Skip this section if you are fine with text-only product cards for now.

### Step 9. Create an R2 bucket

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → **R2** → **Create bucket** (e.g. `iios-store-images`).
2. Choose one mode:

**Option A — Public URL (simplest)**

1. Bucket → **Settings** → enable public access / r2.dev subdomain.
2. Copy the public base URL (e.g. `https://pub-xxxx.r2.dev`).

```powershell
fly secrets set R2_PUBLIC_BASE_URL="https://pub-xxxx.r2.dev"
```

**Option B — Private bucket (bot fetches via S3 API)**

1. R2 → **Manage R2 API Tokens** → create token with read/write on the bucket.
2. Note: Account ID, Access Key ID, Secret Access Key, bucket name.

```powershell
fly secrets set `
  R2_ACCOUNT_ID="your_account_id" `
  R2_ACCESS_KEY_ID="your_access_key" `
  R2_SECRET_ACCESS_KEY="your_secret_key" `
  R2_BUCKET="iios-store-images"
```

### Step 10. Upload product images

Image files should be named after product IDs, e.g. `iphone-15-pro.jpg`.

Locally (with R2 credentials in `.env`):

```powershell
# Put images in ./images/
python -m scripts.upload_images
```

Object keys default to `<product_id>.jpg` (see `store/services/images.py`).

---

## Part 6 — Deploy

### Step 11. Deploy the app

Make sure you run deploy **from the project folder** that contains `Dockerfile` and `fly.toml`:

```powershell
cd C:\Users\KostiantynStrusovsky\Desktop\pet
fly deploy
```

If you see `app does not have a Dockerfile or buildpacks configured`:

1. Confirm the files exist: `dir Dockerfile fly.toml`
2. `fly.toml` must include `[build]` with `dockerfile = "Dockerfile"` (already set in this repo)
3. If deploying via **GitHub Actions**, commit and push `Dockerfile`, `fly.toml`, `requirements.txt`, and the `store/` folder to `main`

Fly will:

1. Build the Docker image from `Dockerfile`
2. Attach the volume at `/data`
3. Start the bot with `python -m store`
4. On first start: create SQLite schema, indexes, and seed products

### Step 12. Confirm webhook mode

After deploy, logs should show:

```
Starting webhook on 0.0.0.0:8080/webhook -> https://iios-store-bot.fly.dev/webhook
Application started
```

Verify the webhook is registered with Telegram:

```powershell
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

You should see your Fly URL and `"pending_update_count": 0` (or low).

`fly.toml` keeps **one machine always running** (`min_machines_running = 1`) so Telegram can always deliver POST requests.

### Step 13. Check logs

```powershell
fly logs
```

Look for:

```
SQLite pool ready: /data/store.db
Database initialized at /data/store.db
Seeded 15 product(s) into the database.
Application started
```

### Step 14. Test in Telegram

1. Make sure the bot is **not** running locally.
2. Open your bot in Telegram.
3. Send `/start`.
4. Try **Каталог**, **Кошик**, **Контакти**, **Локація**.

---

## Part 7 — Updates and maintenance

### Redeploy after code changes

```powershell
fly deploy
```

The SQLite file on the volume is **preserved** — carts, orders and catalog data remain.

### View app status

```powershell
fly status
fly machines list
```

### SSH into the machine (debugging)

```powershell
fly ssh console
ls -la /data
```

You should see `store.db` (and possibly `store.db-wal` / `store.db-shm` with WAL mode).

### Change secrets later

```powershell
fly secrets set BOT_TOKEN="new_token"
```

Each `fly secrets set` triggers a rolling restart.

### Restart without redeploy

```powershell
fly apps restart
```

---

## Troubleshooting

### Machine restart loop

If Fly shows **"Machines Restarting a Lot"**, open **Logs from Previous Starts** for the machine ID (e.g. `e2862de0b11148`). Search for **`STARTUP FAILED:`** — that line tells you exactly why the app exited.

**Fix in order:**

1. Set the bot token (most common):
   ```powershell
   fly secrets set BOT_TOKEN="YOUR_TOKEN_FROM_BOTFATHER"
   fly deploy
   ```

2. Create the volume in **`fra`** (must match `primary_region` in `fly.toml`):
   ```powershell
   fly volumes list
   fly volumes create store_data --size 1 --region fra
   fly deploy
   ```

3. Watch logs after redeploy:
   ```powershell
   fly logs
   ```
   Success:
   ```
   Telegram bot OK: @your_bot
   Database initialized at /data/store.db
   Starting webhook on 0.0.0.0:8080/webhook
   Application started
   ```

| Problem | Cause | Fix |
|---------|--------|-----|
| Bot silent after local `python -m store` | Local polling deleted the production webhook | Redeploy Fly: `fly deploy` |
| **Machine restart loop** | App crashes on startup (check **Logs from Previous Starts**) | See checklist below |
| `STARTUP FAILED: BOT_TOKEN is invalid` | Wrong or missing secret | `fly secrets set BOT_TOKEN="..."` then `fly deploy` |
| `To use start_webhook, PTB must be installed via pip install "python-telegram-bot[webhooks]"` | Missing webhook deps in Docker image | Ensure `requirements.txt` has `python-telegram-bot[webhooks]` and redeploy |
| `STARTUP FAILED: Database directory '/data' does not exist` | Volume missing or wrong region | `fly volumes create store_data --size 1 --region fra` (match `primary_region`) |
| Webhook URL wrong in `getWebhookInfo` | Custom domain or renamed app | Update `WEBHOOK_URL` in `fly.toml` or set secret; redeploy |
| `401` / updates ignored | `WEBHOOK_SECRET` mismatch | Use the same secret in Fly secrets and redeploy |
| Bot starts but no data after restart | Volume missing or wrong mount | Create volume; check `fly volumes list` and `[mounts]` in `fly.toml` |
| `Can't parse entities` on contacts | Old deployment | Redeploy latest code (contacts use HTML) |
| No product photos | R2 not configured or images not uploaded | Set R2 secrets; run `upload_images` |
| App won't start — volume error | Volume in different region than app | Create volume in same region as `primary_region` |
| Empty catalog | DB seeded only when empty | Normal on first run; check logs for "Seeded N product(s)" |

---

## Quick reference — full first-time deploy

```powershell
# 1. Login
fly auth login

# 2. Create app (first time)
fly launch --no-deploy

# 3. Volume for SQLite (region must match primary_region in fly.toml — fra)
fly volumes create store_data --size 1 --region fra

# 4. Secrets
fly secrets set BOT_TOKEN="YOUR_TOKEN"
fly secrets set WEBHOOK_SECRET="your-random-secret"
fly secrets set ADMIN_CHAT_IDS="YOUR_TELEGRAM_ID"

# 5. Deploy
fly deploy

# 6. Watch logs & verify webhook
fly logs
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

---

## Cost notes (Fly.io)

- One `shared-cpu-1x` machine (~512 MB) runs continuously.
- 1 GB volume has a small monthly cost.
- See [Fly.io pricing](https://fly.io/docs/about/pricing/) for current rates.

---

## Security reminders

- Do **not** commit `.env` to git (it is in `.gitignore`).
- Rotate the bot token via BotFather if it was ever shared in chat.
- Use `fly secrets set` for all tokens and API keys on production.
