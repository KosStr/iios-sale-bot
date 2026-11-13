# Deploy IIOS Store Bot — step by step

This guide walks you through deploying the Telegram bot to **Fly.io** with:

- persistent **SQLite** on a Fly Volume
- optional **Cloudflare R2** for product images and the landing page's `hot.json`
- optional **channel auto-posting** and order notifications
- store contacts/location from environment variables

The website (landing page and `/catalog`) is deployed separately to **Cloudflare Workers** — see Step 12b.

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
cd path\to\iios-sale-bot
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
primary_region = "fra"
```

`fra` = Frankfurt (the repo default). `waw` (Warsaw) is also close to Ukraine; see `fly platform regions`. Whatever you pick, the volume must be in the same region.

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
- **Region** → `fra` (must match the volume region later)
- **Postgres / Redis?** → No
- **Deploy now?** → No (we set secrets and volume first)

If the app already exists, skip this step.

---

## Part 3 — Persistent database (Fly Volume)

The bot stores products, carts, orders and bookings in SQLite at `/data/store.db`. That path must live on a **Fly Volume**, or data is lost on every restart.

### Step 6. Create the volume (once per app)

Use the **same region** as `primary_region` in `fly.toml`:

```powershell
fly volumes create store_data --size 1 --region fra
```

- Name `store_data` must match `source = "store_data"` in `fly.toml`.
- Size `1` GB is enough for a small store; increase later if needed.

Verify:

```powershell
fly volumes list
```

You should see `store_data` in region `fra`.

---

## Part 4 — Secrets and configuration

Never commit secrets to git. Set them on Fly with `fly secrets set`.

### Step 7. Required secret: bot token

```powershell
fly secrets set BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
```

Replace with the token from BotFather.

**Webhook secret** (Telegram sends this in the `X-Telegram-Bot-Api-Secret-Token` header; requests without it get `403`). If unset, the bot derives one from `BOT_TOKEN`, so the webhook is never open. Setting your own is still fine:

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

Admins can use `/add`, `/products` and `/hot`, and receive order alerts.

**Order alerts without admin access** (optional):

```powershell
fly secrets set NOTIFY_CHAT_ID="123456789"
```

**Channel auto-posting** (optional). Add the bot to the channel as an admin with *Post*, *Edit* and *Delete messages* rights, then:

```powershell
fly secrets set CHANNEL_ID="@your_channel"   # or the numeric -100… ID
```

**Store contacts** (shown in «Контакти», on product cards and in channel posts). Each one has a built-in IIOS default, so set only what differs:

```powershell
fly secrets set `
  STORE_NAME="IIOS Store" `
  STORE_PHONE="+380 95 340 77 54" `
  STORE_TELEGRAM="@iios_cv" `
  STORE_MANAGER="@iios_manager" `
  STORE_INSTAGRAM="@iios_cv" `
  STORE_INSTAGRAM2="@iios_tehnika"
```

**Store location** (shown in «Локація»):

```powershell
fly secrets set `
  STORE_ADDRESS="м. Чернівці, вул. Заньковецької" `
  STORE_MAP_URL="https://maps.app.goo.gl/8AZcqV7XxU1495Ns6"
```

> Non-secret settings (`DATABASE_PATH=/data/store.db`, `USE_WEBHOOK`, `WEBHOOK_URL`, `PORT`) are already in `fly.toml` under `[env]`.

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

Photos sent to the bot in `/add` or ✏️ «Фото» are uploaded to R2 automatically (Option B credentials required). To bulk-upload, name files after product IDs, e.g. `iphone-15-pro.jpg`.

Locally (with R2 credentials in `.env`):

```powershell
# Put images in ./images/
python -m scripts.upload_images
```

Object keys default to `<product_id>.jpg` (see `store/services/images.py`).

### Step 11. Hot deals on the landing page (optional)

Admins mark products as hot in the bot (`/products` → product → ✏️ Редагувати →
🔥 Зробити гарячою; `/hot` lists them). On every change the bot uploads
`hot.json` to the bucket, and `index.html` builds the deals carousel from it.
The deals also rotate through the product card in the hero phone mockup (photo,
name, colour, price counting down to the sale price, about 5 seconds each). That mockup is decorative: it has no buttons and does not
link anywhere.

Needs **both** options above: the R2 write credentials (to upload the file) and
`R2_PUBLIC_BASE_URL` (so the JSON has photo URLs). Only in-stock products are
published. "Акційна ціна" is typed in the product's main currency (UAH if set,
otherwise USD; the other one is scaled by the same discount). It strikes through
the regular price and adds a `-N%` badge on the landing, and the bot card, channel
post, cart and orders use the sale price too.

The browser fetches `hot.json` from another origin, so allow it once in
Cloudflare → R2 → bucket → **Settings** → **CORS Policy**:

```json
[
  {
    "AllowedOrigins": [
      "https://i-ios.store",
      "https://www.i-ios.store",
      "https://store.iios.workers.dev",
      "http://localhost:8787",
      "http://127.0.0.1:8787",
      "http://localhost:8000",
      "http://localhost:5500",
      "http://127.0.0.1:5500"
    ],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 86400
  }
]
```

If the fetch fails or the file has no deals, the deals section stays hidden and
the hero phone shows a short sample chat instead of a product card. An origin
missing from the CORS list above looks exactly like that, so add the
`wrangler dev` origin (`localhost:8787`) if you want to see deals in the local
preview. The object key can be changed with the
`HOT_DEALS_KEY` env var (default `hot.json`).

### Step 11b. Website catalog (`/catalog`)

With the same R2 credentials, the bot uploads every in-stock product to
`catalog.json` (checked every 2 minutes while it runs, uploaded only on
change). `worker/index.js` renders it as plain HTML with Product structured
data at `https://i-ios.store/catalog`, so search engines and AI assistants can
read products and prices. Only `/catalog` runs the Worker (`run_worker_first`
in `wrangler.jsonc`); the rendered page is cached for 5 minutes, so edits
appear on the site within about 7 minutes. Key: `CATALOG_KEY` (default
`catalog.json`).

The page is complete without JavaScript. `catalog.js` adds the controls on top
of the rendered cards:

- **Category tabs** — underlined text links with product counts; `/catalog#phone`
  (used by the landing's category cards) opens that tab directly.
- **Filters** — toggle chips: Нові / Вживані (shown when the catalog has both)
  and Знижки (shown when something is on sale), plus model chips inside a
  category that has more than one model.
- **Sorting** — Типово / Дешевші / Дорожчі, within each category.
- **Search** — covers the whole catalog and leaves the open category.
- **Result count** with «Скинути» — shown only once something narrows the list.
- **«Показати ще»** — cards are revealed 24 at a time.

Test locally without touching production:

```bash
npx wrangler r2 object put iios/catalog.json --local --file sample.json
npx wrangler dev --local    # http://127.0.0.1:8787/catalog
```

### Step 11c. «Передзвоніть мені» on the website

A round phone button sits in the bottom-right corner of the landing page and
`/catalog`, and every `/catalog` card has a «Передзвоніть мені» link. Both open
a short form (phone, optional name, optional «Що цікавить?»). The Worker
(`worker/callback-api.js`, route `POST /api/callback`) checks the request and
sends the number to Telegram through the bot. The bot on Fly is not involved.

Give the Worker the bot token and the chats that should get the alerts. Each
chat must have pressed **/start** in the bot at least once, or Telegram refuses
the message («chat not found»):

```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN   # paste the same token as BOT_TOKEN
npx wrangler secret put CALLBACK_CHAT_IDS    # e.g. 123456789,987654321
```

Secrets apply at once, with no redeploy. Until both are set, the form shows
«Сервіс тимчасово недоступний» with the store phone number, and the Worker logs
the reason (`npx wrangler tail`).

Protections, all on the free plan:

- Same-origin JSON only (a cross-site browser request is refused), 2 KB body
  limit, and refused on `*.workers.dev`, where the rate limiter can't run.
- A hidden honeypot field, and forms sent within 1.5 s of opening are refused.
- Validation: Ukrainian numbers in any common spelling (`+380…`, `0…`, `80…`)
  or `+`international ones. Names may contain letters only, and links are
  refused in every field. The product name comes from `catalog.json`, never
  from the request.
- Rate limits in the edge cache (per Cloudflare location): 4 requests an hour
  per visitor, 1 alert per number every 3 hours (a repeat says «done» without
  a second alert), and 60 an hour for the whole site. IPs and numbers are kept
  only as salted hashes.
- Alerts are plain text with no link previews, and nothing is stored apart
  from the Telegram message.

To test locally, put the secrets in `.dev.vars` (git-ignored). Use a test bot
and your own chat ID:

```bash
printf 'TELEGRAM_BOT_TOKEN=<test bot token>\nCALLBACK_CHAT_IDS=<your chat id>\n' > .dev.vars
npx wrangler dev --port 8787
```

---

## Part 6 — Deploy

### Step 12. Deploy the app

Make sure you run deploy **from the project folder** that contains `Dockerfile` and `fly.toml`:

```powershell
fly deploy
```

Pushing to `main` on GitHub also deploys automatically (`.github/workflows/fly-deploy.yml`). It needs a `FLY_API_TOKEN` repository secret (`fly tokens create deploy`).

If you see `app does not have a Dockerfile or buildpacks configured`:

1. Confirm the files exist: `dir Dockerfile fly.toml`
2. `fly.toml` must include `[build]` with `dockerfile = "Dockerfile"` (already set in this repo)
3. If deploying via **GitHub Actions**, commit and push `Dockerfile`, `fly.toml`, `requirements.txt`, and the `store/` folder to `main`

### Step 12b. Deploy the website

The landing page and `/catalog` live on Cloudflare Workers and are deployed
from the same folder, separately from the bot. Pushing to `main` does **not**
deploy the site.

```bash
npx wrangler dev --port 8787   # preview: http://localhost:8787 and /catalog
npx wrangler deploy            # publish
```

- First time only: `npx wrangler login`.
- Only the files allowed by `.assetsignore` are uploaded (`index.html`,
  `catalog.js`, `callback.js`, icons, `robots.txt`, `sitemap.xml`, `og-image.jpg`), plus the
  Worker in `worker/` (`index.js`, `callback-api.js`). Add a new public file to `.assetsignore` or it
  will not be served.
- Check `https://i-ios.store/` and `https://i-ios.store/catalog` afterwards.
  `/catalog` is cached for 5 minutes, so allow that long if it still looks old.
- Usual order: change on a branch → preview → `wrangler deploy` → open a pull
  request and merge it, so `main` matches what is live.

Back to the bot — on `fly deploy`, Fly will:

1. Build the Docker image from `Dockerfile`
2. Attach the volume at `/data`
3. Start the bot with `python -m store`
4. On first start: create the SQLite schema and indexes (the catalog starts empty — add products with `/add`)

### Step 13. Confirm webhook mode

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

`fly.toml` lets the machine **suspend when idle** (`auto_stop_machines = 'suspend'`, `min_machines_running = 0`). Fly's proxy wakes it when Telegram POSTs an update, so the first update after a quiet period takes a moment longer. Set `min_machines_running = 1` if you want it always on.

### Step 14. Check logs

```powershell
fly logs
```

Look for:

```
Telegram bot OK: @your_bot (123456789)
SQLite pool ready: /data/store.db (size=5)
Database initialized at /data/store.db
Starting webhook on 0.0.0.0:8080/webhook -> https://iios-store-bot.fly.dev/webhook
Application started
```

### Step 15. Test in Telegram

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

Website changes (`index.html`, `catalog.js`, `callback.js`, `worker/`) need `npx wrangler deploy` instead (Step 12b); the bot does not have to be redeployed for them.

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
| No product photos | R2 not configured or images not uploaded | Set R2 secrets; re-send the photo via ✏️ «Фото» or run `upload_images` |
| Channel post not created/updated | `CHANNEL_ID` unset or bot lacks channel admin rights | Set `CHANNEL_ID`; give the bot Post/Edit/Delete rights. Errors are logged as `Could not … channel post` |
| «Пост у каналі не видалено» alert | Telegram doesn't let bots delete posts older than 48 h | The post is marked «❌ ПРОДАНО»; delete it by hand via the link the bot sends |
| App won't start — volume error | Volume in different region than app | Create volume in same region as `primary_region` |
| Empty catalog | The built-in seed catalog is empty | Normal on first run — add products with `/add` |

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

# 7. Website (separate from the bot)
npx wrangler deploy
```

---

## Cost notes (Fly.io)

- One `shared-cpu-1x` machine (512 MB), suspended while idle.
- 1 GB volume has a small monthly cost.
- See [Fly.io pricing](https://fly.io/docs/about/pricing/) for current rates.

---

## Cost and abuse protection

What a flood of requests can cost, and how each part is capped:

| Part | Billing risk | Protection |
|------|--------------|------------|
| Landing (`index.html` on Workers static assets) | None: static asset requests are free and unlimited | Never set `run_worker_first` to `true` in `wrangler.jsonc`. Security headers in `_headers` |
| `/catalog` (Worker, `worker/index.js`) | Only `/catalog` and `/api/*` invoke the Worker: 100k requests/day on the Free plan, then it errors instead of billing | `run_worker_first` lists only `/catalog` and `/api/*`; the rendered page (and the error page) is cached, so a flood does not become one R2 read per request |
| `/api/callback` (Worker, `worker/callback-api.js`) | One Worker request per submitted form, sharing the 100k/day with `/catalog` | Same-origin JSON only, honeypot, minimum fill time, per-visitor, per-number and site-wide limits in the edge cache (Step 11c) |
| R2 photos + `hot.json` via `r2.dev` | Every request is an uncached R2 Class B read; `r2.dev` has no WAF or rate limiting | Move to a custom domain with cache + rate limiting (below) |
| Bot on Fly (`/webhook`) | Junk traffic keeps the machine awake, plus egress | One machine only, `[http_service.concurrency]` caps in `fly.toml`, secret token rejects forged requests with `403` |

### Put R2 behind a custom domain (recommended)

1. Cloudflare → **R2** → bucket → **Settings** → **Custom Domains** → **Connect Domain** → `img.i-ios.store`.
2. Same page: **Public Development URL** (`r2.dev`) → **Disallow**. Do this only after step 5, or the live landing loses its images.
3. **Caching** → **Cache Rules** → create a rule: *Hostname equals `img.i-ios.store`* → **Eligible for cache**, Edge TTL **Use cache-control header if present**, else 1 hour. Photos and `hot.json` (`max-age=60`) are then served from the CDN, so repeated requests no longer reach R2.
4. **Security** → **WAF** → **Rate limiting rules**: *Hostname equals `img.i-ios.store`* → 100 requests / 10 s per IP → **Block** for 10 s. The Free plan includes one rule.
5. Replace the `pub-…r2.dev` host with `https://img.i-ios.store` in `index.html`, `_headers` (CSP) and the `R2_PUBLIC_BASE_URL` Fly secret, then redeploy both. The R2 CORS policy (Step 11) stays the same.

### Spending alerts

- Cloudflare → **Manage Account** → **Notifications** → **Add** → **Usage Based Billing**: get an email when R2 or Workers usage crosses a threshold.
- Stay on the Workers **Free** plan if possible. Its limits fail closed, so requests are refused instead of billed.
- Fly.io → **Billing**: turn on usage alerts. Check `fly scale show` shows a single machine, since only extra machines can multiply the cost.

---

## Security reminders

- Do **not** commit `.env` to git (it is in `.gitignore`).
- Rotate the bot token via BotFather if it was ever shared in chat.
- Use `fly secrets set` for all tokens and API keys on production.
