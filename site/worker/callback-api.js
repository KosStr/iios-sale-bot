// POST /api/callback — "Передзвоніть мені" requests from the site's phone
// button (/callback.js). The Worker validates the request and sends it to the
// admins' Telegram chats through the bot, so the Fly machine never wakes up.
//
// Secrets (npx wrangler secret put …; locally: .dev.vars):
//   TELEGRAM_BOT_TOKEN  the bot's token (same bot as BOT_TOKEN on Fly)
//   CALLBACK_CHAT_IDS   comma-separated chat IDs that get the alert; each one
//                       must have pressed /start in the bot at least once
//
// Protections, cheapest first:
//   * only same-origin JSON POSTs (a cross-site browser request needs a CORS
//     preflight, which this route never approves); 2 KB body cap
//   * refused on *.workers.dev, where the Cache API (the rate limiter) is off
//   * honeypot field and a minimum time between opening the form and sending
//   * strict validation: Ukrainian or +international phone, letters-only name,
//     no links anywhere; the product name is looked up from catalog.json, never
//     taken from the request
//   * rate limits per visitor IP, per phone number and per site, kept in the
//     edge cache (free) with an in-memory copy for bursts; IPs and phone
//     numbers are only ever stored as salted hashes
//
// Free tier: one Worker request and one Telegram call per submitted form.

const MAX_BODY_BYTES = 2048;
const MIN_FILL_MS = 1500;         // faster than this is a script, not a person
const MAX_FILL_MS = 6 * 3600e3;   // a form left open for hours: ask to resend
const TELEGRAM_TIMEOUT_MS = 8000;

// [requests, window in seconds]
const LIMITS = {
  ip: [4, 3600],        // one visitor
  phone: [1, 3 * 3600], // one number (repeats are acknowledged, not re-sent)
  site: [60, 3600],     // everyone together, so a flood can't bury the admins
};

const LINK_PATTERN = /https?:|www\.|t\.me|\.(?:com|net|org|ru|ua|io|me|xyz|top|info|biz|site|online)\b|@[a-z0-9_]{3,}/i;
const NAME_PATTERN = /^[\p{L}\p{M}][\p{L}\p{M}' .’ʼ-]{0,49}$/u;
const PRODUCT_ID_PATTERN = /^[A-Za-z0-9_.-]{1,64}$/;

const memoryCounters = new Map();

export async function handleCallback(request, env, ctx, { catalogKey }) {
  const url = new URL(request.url);

  if (request.method !== 'POST') {
    return json(405, { ok: false, error: 'method' }, { Allow: 'POST' });
  }
  if (url.hostname.endsWith('.workers.dev')) {
    return json(403, { ok: false, error: 'host' });
  }
  // Browsers always send Origin on a POST; it must be this site.
  if (request.headers.get('Origin') !== url.origin) {
    return json(403, { ok: false, error: 'origin' });
  }
  if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json')) {
    return json(415, { ok: false, error: 'type' });
  }
  if (Number(request.headers.get('Content-Length') || 0) > MAX_BODY_BYTES) {
    return json(413, { ok: false, error: 'size' });
  }

  let body;
  try {
    const text = await request.text();
    if (text.length > MAX_BODY_BYTES) return json(413, { ok: false, error: 'size' });
    body = JSON.parse(text);
  } catch {
    return json(400, { ok: false, error: 'json' });
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return json(400, { ok: false, error: 'json' });
  }

  // Honeypot: people never see this field. Pretend it worked so bots learn nothing.
  if (typeof body.company === 'string' && body.company.trim()) {
    return json(200, { ok: true });
  }
  const elapsed = Number(body.elapsed);
  if (!Number.isFinite(elapsed) || elapsed < MIN_FILL_MS) {
    return json(400, { ok: false, error: 'too_fast', message: 'Зачекайте секунду й надішліть ще раз.' });
  }
  if (elapsed > MAX_FILL_MS) {
    return json(400, { ok: false, error: 'stale', message: 'Форма була відкрита задовго — надішліть її ще раз.' });
  }

  const phone = normalizePhone(body.phone);
  if (!phone) {
    return json(400, { ok: false, error: 'phone', field: 'phone', message: 'Перевірте номер: наприклад, +380 67 123 45 67.' });
  }
  const name = cleanText(body.name, 50);
  if (name && (!NAME_PATTERN.test(name) || LINK_PATTERN.test(name))) {
    return json(400, { ok: false, error: 'name', field: 'name', message: "Вкажіть ім'я літерами." });
  }
  const note = cleanText(body.note, 120);
  if (note && LINK_PATTERN.test(note)) {
    return json(400, { ok: false, error: 'note', field: 'note', message: 'Без посилань, будь ласка — просто модель чи питання.' });
  }
  const productId = typeof body.productId === 'string' && PRODUCT_ID_PATTERN.test(body.productId)
    ? body.productId : '';

  const token = (env.TELEGRAM_BOT_TOKEN || '').trim();
  const chatIds = String(env.CALLBACK_CHAT_IDS || '').split(',').map(s => s.trim()).filter(Boolean);
  if (!token || !chatIds.length) {
    console.error('callback: TELEGRAM_BOT_TOKEN or CALLBACK_CHAT_IDS is not set');
    return unavailable();
  }

  // Rate limits. The phone limit answers "ok" so a double tap or a second
  // attempt reads as success, but the admins aren't alerted twice.
  const salt = token.slice(-16);
  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';
  const ipKey = await hash(`ip:${ip}:${salt}`);
  const phoneKey = await hash(`phone:${phone}:${salt}`);
  if (!(await allow(url.origin, `ip/${ipKey}`, LIMITS.ip))) {
    return json(429, { ok: false, error: 'rate', message: 'Забагато запитів. Спробуйте пізніше або зателефонуйте нам.' }, { 'Retry-After': '3600' });
  }
  if (!(await allow(url.origin, `phone/${phoneKey}`, LIMITS.phone))) {
    return json(200, { ok: true, duplicate: true });
  }
  if (!(await allow(url.origin, 'site', LIMITS.site))) {
    return json(429, { ok: false, error: 'busy', message: 'Зараз забагато запитів — зателефонуйте нам, будь ласка.' }, { 'Retry-After': '600' });
  }

  const product = productId ? await findProduct(env, catalogKey, productId) : null;
  const page = pageFromReferer(request.headers.get('Referer'), url.origin);
  const text = alertText({ phone, name, note, product, page });

  const results = await Promise.allSettled(chatIds.map(chatId => sendTelegram(token, chatId, text)));
  const delivered = results.filter(r => r.status === 'fulfilled' && r.value).length;
  if (!delivered) {
    console.error('callback: Telegram delivery failed for every chat');
    // Let the visitor try again: undo this request's phone count.
    ctx.waitUntil(forget(url.origin, `phone/${phoneKey}`));
    return json(502, { ok: false, error: 'delivery', message: 'Не вдалося надіслати запит. Зателефонуйте нам, будь ласка.' });
  }
  return json(200, { ok: true });
}

// ── Validation ────────────────────────────────────────────────

// "+380671234567" for Ukrainian numbers in any common spelling, "+<digits>"
// for other countries (only when typed with "+"); null when invalid.
export function normalizePhone(value) {
  if (typeof value !== 'string' || value.length > 40) return null;
  const raw = value.trim();
  if (/[^\d\s()+.-]/.test(raw)) return null;
  const plus = raw.startsWith('+');
  const digits = raw.replace(/\D/g, '');
  let national = null;
  if (digits.length === 12 && digits.startsWith('380')) national = digits.slice(3);
  else if (digits.length === 11 && digits.startsWith('80') && !plus) national = digits.slice(2);
  else if (digits.length === 10 && digits.startsWith('0') && !plus) national = digits.slice(1);
  else if (digits.length === 9 && !plus) national = digits;
  if (national) {
    // Ukrainian numbers never start with 0 after the country code, and a
    // run of one digit ("000000000") is a placeholder, not a number.
    if (national.startsWith('0') || /^(\d)\1+$/.test(national)) return null;
    return `+380${national}`;
  }
  if (plus && digits.length >= 10 && digits.length <= 15 && !digits.startsWith('0') && !digits.startsWith('380') && !/^(\d)\1+$/.test(digits)) {
    return `+${digits}`;
  }
  return null;
}

function cleanText(value, max) {
  if (typeof value !== 'string') return '';
  // Drop control and invisible formatting characters, collapse whitespace.
  const text = value.replace(/[\p{Cc}\p{Cf}]/gu, ' ').replace(/\s+/g, ' ').trim();
  return text.slice(0, max).trim();
}

function prettyPhone(phone) {
  const m = /^\+380(\d{2})(\d{3})(\d{2})(\d{2})$/.exec(phone);
  return m ? `+380 ${m[1]} ${m[2]} ${m[3]} ${m[4]}` : phone;
}

function pageFromReferer(referer, origin) {
  try {
    const ref = new URL(referer);
    if (ref.origin !== origin) return '';
    if (ref.pathname === '/catalog') return 'каталог';
    if (ref.pathname === '/' || ref.pathname === '/index.html') return 'головна';
  } catch { /* no or bad Referer */ }
  return '';
}

async function findProduct(env, catalogKey, productId) {
  try {
    const object = await env.CATALOG.get(catalogKey);
    if (!object) return null;
    const catalog = await object.json();
    const item = (catalog.items || []).find(i => i && i.id === productId);
    return item && item.name ? { id: item.id, name: String(item.name) } : null;
  } catch {
    return null;
  }
}

// ── Telegram ──────────────────────────────────────────────────

function escapeHtml(value) {
  return String(value).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

function alertText({ phone, name, note, product, page }) {
  const time = new Date().toLocaleString('uk-UA', {
    timeZone: 'Europe/Kyiv', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  const lines = ['📞 <b>Запит на дзвінок з сайту</b>', ''];
  lines.push(`☎️ <b>${escapeHtml(prettyPhone(phone))}</b>`);
  if (name) lines.push(`👤 ${escapeHtml(name)}`);
  if (product) lines.push(`📱 Цікавить: ${escapeHtml(product.name)} <code>${escapeHtml(product.id)}</code>`);
  if (note) lines.push(`💬 ${escapeHtml(note)}`);
  lines.push('', `🕒 ${escapeHtml(time)}${page ? ` · ${escapeHtml(page)}` : ''}`);
  return lines.join('\n');
}

async function sendTelegram(token, chatId, text) {
  try {
    const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: 'HTML',
        link_preview_options: { is_disabled: true },
      }),
      signal: AbortSignal.timeout(TELEGRAM_TIMEOUT_MS),
    });
    if (!response.ok) {
      // The description says why (e.g. "chat not found"); never log the token.
      const detail = await response.json().catch(() => ({}));
      console.error(`callback: Telegram ${response.status} for chat ${chatId}: ${detail.description || ''}`);
      return false;
    }
    return true;
  } catch (err) {
    console.error(`callback: Telegram request failed for chat ${chatId}: ${err && err.name}`);
    return false;
  }
}

// ── Rate limiting ─────────────────────────────────────────────
// Counters live in the edge cache (per Cloudflare location, free) and in this
// isolate's memory. Not atomic, which is fine for a contact form: the goal is
// to stop floods, not to count exactly.

async function allow(origin, key, [limit, windowSeconds]) {
  const now = Math.floor(Date.now() / 1000);
  const fromMemory = memoryCounters.get(key);
  let entry = fromMemory && fromMemory.reset > now ? fromMemory : null;

  const cacheKey = new Request(`${origin}/__ratelimit/callback/${key}`);
  try {
    const cached = await caches.default.match(cacheKey);
    if (cached) {
      const stored = await cached.json();
      if (stored.reset > now && (!entry || stored.count > entry.count)) entry = stored;
    }
  } catch { /* cache unavailable: memory only */ }

  if (!entry) entry = { count: 0, reset: now + windowSeconds };
  if (entry.count >= limit) return false;

  entry = { count: entry.count + 1, reset: entry.reset };
  remember(key, entry, now);
  try {
    await caches.default.put(cacheKey, new Response(JSON.stringify(entry), {
      headers: { 'Content-Type': 'application/json', 'Cache-Control': `max-age=${Math.max(1, entry.reset - now)}` },
    }));
  } catch { /* memory copy still applies */ }
  return true;
}

async function forget(origin, key) {
  memoryCounters.delete(key);
  try {
    await caches.default.delete(new Request(`${origin}/__ratelimit/callback/${key}`));
  } catch { /* nothing to undo */ }
}

function remember(key, entry, now) {
  memoryCounters.set(key, entry);
  if (memoryCounters.size > 2000) {
    for (const [k, v] of memoryCounters) if (v.reset <= now) memoryCounters.delete(k);
    if (memoryCounters.size > 2000) memoryCounters.clear();
  }
}

async function hash(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest).slice(0, 16)].map(b => b.toString(16).padStart(2, '0')).join('');
}

// ── Responses ─────────────────────────────────────────────────

function unavailable() {
  return json(503, { ok: false, error: 'unavailable', message: 'Сервіс тимчасово недоступний. Зателефонуйте нам, будь ласка.' });
}

function json(status, data, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'X-Robots-Tag': 'noindex',
      ...extra,
    },
  });
}
