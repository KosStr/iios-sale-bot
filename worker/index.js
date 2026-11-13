// Renders /catalog from catalog.json in R2 (published by the bot, see
// store/services/site_catalog.py). Every other path is a free static asset and
// never reaches this script (run_worker_first in wrangler.jsonc).
//
// The page is complete without JavaScript (crawlers see every product);
// /catalog.js, a static asset, only adds search, tabs and filters on top.
//
// Free-tier safety: the rendered page is cached for CACHE_SECONDS under one
// fixed key (query strings ignored), so floods hit the edge cache, not R2.
//
// /api/callback (the site's "Передзвоніть мені" form) lives in callback-api.js.

import { handleCallback } from './callback-api.js';

const SITE = 'https://i-ios.store';
const PAGE_PATH = '/catalog';
const CATALOG_KEY = 'catalog.json';
const BOT_URL = 'https://t.me/iios_cv_bot';
const CACHE_SECONDS = 300;

// Order and labels match the bot's categories (store/services/catalog_filter.py).
const CATEGORIES = [
  ['phone', 'iPhone'],
  ['ipad', 'iPad'],
  ['laptop', 'MacBook'],
  ['watch', 'Apple Watch'],
  ['headphones', 'Навушники'],
  ['accessories', 'Аксесуари'],
];

// Same policy as _headers (which only covers static assets). Scripts are
// limited to our own /catalog.js; JSON-LD blocks are data, not executed.
const SECURITY_HEADERS = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self' https://pub-357de5a9fe674c84a20c5f0419f76c39.r2.dev; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'; upgrade-insecure-requests",
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/api/callback') {
      return handleCallback(request, env, ctx, { catalogKey: CATALOG_KEY });
    }
    if (url.pathname.startsWith('/api/')) {
      return new Response('Not Found', { status: 404, headers: { 'Cache-Control': 'no-store' } });
    }
    if (url.pathname !== PAGE_PATH) {
      // "/catalog/" and "/catalog/anything" → the one canonical page.
      if (url.pathname.startsWith(PAGE_PATH + '/')) {
        return Response.redirect(url.origin + PAGE_PATH, 301);
      }
      return env.ASSETS.fetch(request);
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
    }

    const cache = caches.default;
    const cacheKey = new Request(url.origin + PAGE_PATH, { method: 'GET' });
    let response = await cache.match(cacheKey);
    if (!response) {
      response = await render(env);
      // The error page is cached too (for a minute), so a flood can't turn a
      // missing catalog.json into an R2 read per request.
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
    }

    const headers = new Headers(response.headers);
    if (url.hostname.endsWith('.workers.dev')) headers.set('X-Robots-Tag', 'noindex');
    const body = request.method === 'HEAD' ? null : response.body;
    return new Response(body, { status: response.status, headers });
  },
};

async function render(env) {
  let catalog = null;
  try {
    const object = await env.CATALOG.get(CATALOG_KEY);
    if (object) catalog = await object.json();
  } catch {
    catalog = null;
  }
  if (!catalog || !Array.isArray(catalog.items)) {
    // Temporary: tell crawlers to come back later.
    return htmlResponse(page([], null), 503, { 'Retry-After': '600', 'Cache-Control': 'public, max-age=60' });
  }
  const items = catalog.items.filter(i => i && i.id && i.name);
  return htmlResponse(page(items, catalog.updated_at), 200, {
    'Cache-Control': `public, max-age=${CACHE_SECONDS}`,
  });
}

function htmlResponse(html, status, extra) {
  return new Response(html, {
    status,
    headers: { 'Content-Type': 'text/html; charset=utf-8', ...SECURITY_HEADERS, ...extra },
  });
}

// ── Formatting ────────────────────────────────────────────────

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// Only plain https image URLs make it into the page.
function safeImage(url) {
  return typeof url === 'string' && url.startsWith('https://') ? url : null;
}

// One currency per product, as on the landing: UAH when set, else USD.
// The sale price is in that same currency, so old and new prices compare.
function prices(item) {
  const uah = Boolean(item.price_uah);
  const regular = uah ? item.price_uah : item.price_usd;
  const saleRaw = uah ? item.sale_price_uah : item.sale_price_usd;
  const sale = saleRaw && regular && saleRaw < regular ? saleRaw : null;
  const fmt = uah
    ? n => n.toLocaleString('uk-UA') + ' ₴'
    : n => '$' + n.toLocaleString('en-US');
  return { currency: uah ? 'UAH' : 'USD', regular: regular || null, sale, fmt };
}

// "new" / "used" / "" from the admin's free-text condition.
function conditionKind(condition) {
  const text = (condition || '').toLowerCase();
  if (text.includes('нов')) return 'new';
  if (text.includes('вжив') || text.includes('б/у') || text.includes('б/в')) return 'used';
  return '';
}

const CONDITION_SCHEMA = {
  new: 'https://schema.org/NewCondition',
  used: 'https://schema.org/UsedCondition',
};

function productUrl(item) {
  return `${SITE}${PAGE_PATH}#p-${encodeURIComponent(item.id)}`;
}

function botLink(item) {
  return `${BOT_URL}?start=prod_${encodeURIComponent(item.id)}`;
}

function formatDate(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleDateString('uk-UA', {
    day: 'numeric', month: 'long', timeZone: 'Europe/Kyiv',
  });
}

function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function categoryLabel(key, item) {
  const known = CATEGORIES.find(([k]) => k === key);
  return known ? known[1] : (item && item.category_label) || 'Інше';
}

// ── Structured data ───────────────────────────────────────────

function jsonLd(items) {
  const list = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: 'Каталог IIOS — техніка Apple у Чернівцях',
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => {
      const { currency, regular, sale } = prices(item);
      const product = {
        '@type': 'Product',
        '@id': productUrl(item),
        name: item.name,
        url: productUrl(item),
        brand: { '@type': 'Brand', name: 'Apple' },
        category: item.category_label || undefined,
        color: item.color || undefined,
        description: item.description || undefined,
        image: safeImage(item.image) || undefined,
      };
      if (regular) {
        product.offers = {
          '@type': 'Offer',
          price: sale || regular,
          priceCurrency: currency,
          availability: 'https://schema.org/InStock',
          itemCondition: CONDITION_SCHEMA[conditionKind(item.condition)],
          url: botLink(item),
          seller: { '@id': `${SITE}/#store` },
        };
      }
      return { '@type': 'ListItem', position: index + 1, item: product };
    }),
  };
  const breadcrumbs = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'IIOS', item: `${SITE}/` },
      { '@type': 'ListItem', position: 2, name: 'Каталог', item: `${SITE}${PAGE_PATH}` },
    ],
  };
  // "<" is escaped so product text can never close the script element.
  return [list, breadcrumbs]
    .map(data => `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`)
    .join('\n  ');
}

// ── HTML ──────────────────────────────────────────────────────

const ICON_TG = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm4.93 7.003-1.67 7.87c-.125.558-.455.695-.92.432l-2.54-1.872-1.225 1.178c-.135.135-.25.25-.512.25l.182-2.594 4.705-4.25c.204-.182-.044-.283-.317-.1l-5.812 3.66-2.502-.782c-.543-.17-.554-.543.114-.803l9.76-3.762c.452-.164.849.11.738.773z"/></svg>';
const ICON_SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
const ICON_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const ICON_SORT = '<svg class="sort-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 4v16M3 8l4-4 4 4M17 20V4M13 16l4 4 4-4"/></svg>';
const ICON_CHEVRON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const ICON_PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>';
const ICON_PHONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.14 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.05 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 17z"/></svg>';
const ICON_CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
const ICON_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

// Rough UAH→USD rate, used ONLY to order products by price when some are
// priced in UAH and others in USD. Taken from products that carry both
// prices; the constant is a fallback when none do. Never shown to visitors.
const FALLBACK_UAH_PER_USD = 42;

function uahPerUsd(items) {
  const rates = items
    .filter(i => i.price_uah > 0 && i.price_usd > 0)
    .map(i => i.price_uah / i.price_usd)
    .sort((a, b) => a - b);
  return rates.length ? rates[Math.floor(rates.length / 2)] : FALLBACK_UAH_PER_USD;
}

// The displayed price in USD terms, for sorting; null when there is no price.
function sortPrice(item, rate) {
  const { currency, regular, sale } = prices(item);
  const shown = sale || regular;
  if (!shown) return null;
  return Math.round((currency === 'UAH' ? shown / rate : shown) * 100) / 100;
}

// First non-empty line of the admin's description, e.g. "АКБ 96%".
function firstLine(text) {
  const line = String(text || '').split('\n').map(s => s.trim()).find(Boolean) || '';
  return line.length > 90 ? line.slice(0, 89).trimEnd() + '…' : line;
}

function card(item, index, rate) {
  const { regular, sale, fmt } = prices(item);
  const image = safeImage(item.image);
  const kind = conditionKind(item.condition);
  // Short label on the photo (never truncated); the admin's full wording,
  // when longer ("Новий запечатаний"), leads the specs line instead.
  const condShort = kind === 'new' ? 'Новий' : kind === 'used' ? 'Вживаний' : (item.condition || '');
  const condFull = item.condition && item.condition !== condShort ? item.condition : '';
  const specs = [condFull, item.storage, item.color].filter(Boolean).join(' · ');
  const note = firstLine(item.description);
  const search = [item.name, item.storage, item.color, item.condition, item.category_label, item.subcategory_label, item.description]
    .filter(Boolean).join(' ').toLowerCase();
  const order = sortPrice(item, rate);
  const link = esc(botLink(item));

  let price = '<span class="price-ask">Ціна в боті</span>';
  if (sale) price = `<span class="price">${esc(fmt(sale))}</span><span class="price-old">${esc(fmt(regular))}</span>`;
  else if (regular) price = `<span class="price">${esc(fmt(regular))}</span>`;

  // The first row loads eagerly so the page doesn't open on empty frames.
  const loading = index < 4 ? 'eager' : 'lazy';
  return `
        <article class="card" id="p-${esc(item.id)}" data-i="${index}" data-cat="${esc(item.category || 'other')}" data-sub="${esc(item.subcategory_label || '')}" data-cond="${kind}" data-sale="${sale ? 1 : 0}" data-price="${order ?? ''}" data-q="${esc(search)}">
          <a class="card-media" href="${link}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">
            ${image ? `<img src="${esc(image)}" alt="" width="480" height="480" loading="${loading}" decoding="async">` : ''}
            ${condShort ? `<span class="tag tag-cond tag-${kind || 'other'}">${esc(condShort)}</span>` : ''}
            ${sale ? `<span class="tag tag-sale">−${Math.round((1 - sale / regular) * 100)}%</span>` : ''}
          </a>
          <div class="card-body">
            <h3 class="card-title"><a href="${link}" target="_blank" rel="noopener">${esc(item.name)}</a></h3>
            ${specs ? `<p class="card-specs">${esc(specs)}</p>` : ''}
            ${note ? `<p class="card-note">${esc(note)}</p>` : ''}
            ${item.warranty_days ? `<p class="card-warranty">${ICON_SHIELD}Гарантія ${esc(item.warranty_days)} днів</p>` : ''}
            <div class="card-foot">
              <div class="card-price">${price}</div>
              <a class="card-cta" href="${link}" target="_blank" rel="noopener" aria-label="Замовити ${esc(item.name)} у Telegram">${ICON_TG}<span>Замовити</span></a>
            </div>
            <button type="button" class="card-call js-only" data-callback="${esc(item.id)}" data-callback-name="${esc(item.name)}" aria-label="Передзвоніть мені щодо ${esc(item.name)}">${ICON_PHONE}Передзвоніть мені</button>
          </div>
        </article>`;
}

function groupByCategory(items) {
  const groups = new Map();
  for (const item of items) {
    const key = item.category || 'other';
    if (!groups.has(key)) groups.set(key, { label: categoryLabel(key, item), items: [] });
    groups.get(key).items.push(item);
  }
  const order = CATEGORIES.map(([k]) => k);
  const rank = key => (order.indexOf(key) + 1) || order.length + 1;
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
}

function page(items, updatedAt) {
  const groups = groupByCategory(items);
  const title = 'Каталог iPhone, MacBook, AirPods у Чернівцях — ціни | IIOS';
  const description = items.length
    ? `${items.length} ${plural(items.length, 'товар', 'товари', 'товарів')} Apple в наявності в IIOS (Чернівці): ${groups.map(([, g]) => g.label).join(', ')}. Нові та вживані, гарантія магазину, доставка Новою поштою по Україні.`
    : 'Каталог нової та вживаної техніки Apple в магазині IIOS у Чернівцях: iPhone, MacBook, AirPods, Apple Watch. Гарантія магазину, доставка по Україні.';

  // Every category is listed for catalog.js, so /catalog#watch from the
  // landing can say "nothing in stock right now" instead of showing nothing.
  const labels = Object.fromEntries(CATEGORIES);
  for (const [key, g] of groups) labels[key] = g.label;

  const tabs = [
    `<a class="tab is-active" href="#all" data-tab="all">Усі <span>${items.length}</span></a>`,
    ...groups.map(([key, g]) => `<a class="tab" href="#${esc(key)}" data-tab="${esc(key)}">${esc(g.label)} <span>${g.items.length}</span></a>`),
  ].join('');
  const hasNew = items.some(i => conditionKind(i.condition) === 'new');
  const hasUsed = items.some(i => conditionKind(i.condition) === 'used');
  const hasSale = items.some(i => prices(i).sale);
  const filters = [
    hasNew && hasUsed ? '<button type="button" class="filter" data-filter="new" aria-pressed="false">Нові</button>' : '',
    hasNew && hasUsed ? '<button type="button" class="filter" data-filter="used" aria-pressed="false">Вживані</button>' : '',
    hasSale ? '<button type="button" class="filter filter-sale" data-filter="sale" aria-pressed="false">Знижки</button>' : '',
  ].join('');

  let index = 0;
  const rate = uahPerUsd(items);
  const sections = groups.map(([key, g]) => `
      <section class="group" id="${esc(key)}" data-group="${esc(key)}">
        <h2 class="group-title">${esc(g.label)} <span>${g.items.length}</span></h2>
        <div class="grid">${g.items.map(item => card(item, index++, rate)).join('')}
        </div>
      </section>`).join('');

  const lead = items.length
    ? `${items.length} ${plural(items.length, 'товар', 'товари', 'товарів')} в наявності${updatedAt ? ` · оновлено ${esc(formatDate(updatedAt))}` : ''}`
    : 'Каталог саме оновлюється';

  return `<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  <link rel="canonical" href="${SITE}${PAGE_PATH}">
  <meta name="theme-color" content="#f6f4ef">
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="uk_UA">
  <meta property="og:site_name" content="IIOS">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:image" content="${SITE}/og-image.jpg">
  <meta property="og:url" content="${SITE}${PAGE_PATH}">
  <meta name="twitter:card" content="summary_large_image">
  ${jsonLd(items)}
  <style>${STYLES}</style>
  <script src="/catalog.js" defer></script>
  <script src="/callback.js" defer></script>
</head>
<body data-labels="${esc(JSON.stringify(labels))}" data-bot="${BOT_URL}">
  <header class="top">
    <div class="wrap top-inner">
      <a class="logo" href="/" aria-label="IIOS — на головну">IIOS<span>.</span></a>
      <nav class="top-links" aria-label="Розділи">
        <a href="/">Головна</a>
        <a href="/catalog" aria-current="page">Каталог</a>
      </nav>
      <a class="top-cta" href="${BOT_URL}" target="_blank" rel="noopener">${ICON_TG}<span>Обрати в Telegram</span></a>
    </div>
  </header>

  <main>
    <section class="intro wrap">
      <p class="crumbs"><a href="/">Головна</a><span aria-hidden="true">/</span>Каталог</p>
      <h1>Каталог техніки Apple</h1>
      ${items.length ? `<p class="lead"><span class="dot" aria-hidden="true"></span><span>${lead}</span></p>` : ''}
      <ul class="perks">
        <li>${ICON_CHECK}Гарантія магазину</li>
        <li>${ICON_CHECK}Доставка Новою поштою</li>
        <li>${ICON_CHECK}Trade-in</li>
        <li>${ICON_CHECK}Розтермінування</li>
      </ul>
      ${items.length ? `
      <label class="search js-only">
        ${ICON_SEARCH}
        <input type="search" id="q" placeholder="Пошук: iPhone 15, 256GB, колір…" autocomplete="off" enterkeyhint="search" aria-label="Пошук у всьому каталозі">
      </label>` : ''}
    </section>

    ${items.length ? `
    <!-- Only the category and filter rows stick; search scrolls away with the intro. -->
    <div class="toolbar">
      <div class="wrap toolbar-inner">
        <nav class="tabs chips" aria-label="Категорії">${tabs}</nav>
        <!-- Tabs navigate (underlined text); the row below refines: toggle chips on the left, sorting on the right. -->
        <div class="controls js-only">
          <div class="refine chips">
            ${filters ? `<div class="filters" role="group" aria-label="Фільтри">${filters}</div>` : ''}
            <div class="models" id="models" role="group" aria-label="Модель" hidden></div>
          </div>
          <label class="sort">
            ${ICON_SORT}
            <span class="sort-label">Сортування:</span>
            <select id="sort" aria-label="Сортування">
              <option value="default">Типово</option>
              <option value="asc">Дешевші</option>
              <option value="desc">Дорожчі</option>
            </select>
            ${ICON_CHEVRON}
          </label>
        </div>
      </div>
    </div>

    <div class="wrap results">
      <p class="summary-text js-only"><span id="summary" aria-live="polite"></span><button type="button" class="reset" id="reset" hidden>Скинути</button></p>${sections}
      <div class="more-wrap"><button type="button" class="more" id="more" hidden>Показати ще</button></div>
      <div class="empty" id="empty" hidden>
        <p class="empty-title">Нічого не знайдено</p>
        <p class="empty-text">Спробуйте інший запит або напишіть нам — підберемо під ваш бюджет.</p>
        <a class="btn" id="empty-cta" href="${BOT_URL}" target="_blank" rel="noopener">${ICON_TG}Запитати в боті</a>
      </div>
    </div>

    <section class="wrap help">
      <div>
        <h2>Не знайшли потрібну модель?</h2>
        <p>Напишіть нам у Telegram — підберемо пристрій під ваш бюджет або привеземо під замовлення.</p>
      </div>
      <a class="btn btn-light" href="${BOT_URL}" target="_blank" rel="noopener">${ICON_TG}Написати в Telegram</a>
    </section>` : `
    <div class="wrap">
      <div class="empty">
        <p class="empty-title">Каталог саме оновлюється</p>
        <p class="empty-text">Актуальна наявність і ціни — у нашому Telegram-боті.</p>
        <a class="btn" href="${BOT_URL}" target="_blank" rel="noopener">${ICON_TG}Обрати в Telegram</a>
      </div>
    </div>`}
  </main>

  <!-- Same structure and contacts as the landing footer (keep in sync). -->
  <footer class="foot">
    <div class="wrap foot-top">
      <div>
        <div class="foot-logo">IIOS<span>.</span></div>
        <p class="foot-tagline">Нова та вживана техніка Apple у Чернівцях. Замовлення в Telegram, доставка по Україні.</p>
      </div>
      <div>
        <div class="foot-label">Контакти</div>
        <address class="foot-contacts">
          <a href="https://maps.app.goo.gl/8AZcqV7XxU1495Ns6" target="_blank" rel="noopener">${ICON_PIN}м. Чернівці, вул. Заньковецької</a>
          <a href="tel:+380953407754">${ICON_PHONE}+380 95 340 77 54</a>
          <span>${ICON_CLOCK}Пн–Нд, 10:00–20:00</span>
        </address>
      </div>
      <div>
        <div class="foot-label">Посилання</div>
        <nav class="foot-links" aria-label="Посилання">
          <a href="/">Головна</a>
          <a href="https://t.me/IIOS_cv" target="_blank" rel="noopener">Telegram-канал</a>
          <a href="https://t.me/iios_cv_bot" target="_blank" rel="noopener">Telegram-бот</a>
          <a href="https://www.instagram.com/iios_cv" target="_blank" rel="noopener">Instagram</a>
        </nav>
      </div>
    </div>
  </footer>
</body>
</html>`;
}

// Tokens match index.html so the catalog reads as part of the same site.
const STYLES = `
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f6f4ef;--bg2:#fff;--bg3:#eeeae0;--border:rgba(20,19,15,.09);--border-strong:rgba(20,19,15,.16);--text:#17160f;--muted:#6a6658;--accent:#a3814f;--accent2:#7a5c34;--ink:#121109;--danger:#c2412c;--ok:#2f9e5c;--ok-text:#1d7443;--shadow:0 20px 50px rgba(23,22,15,.10);--shadow-sm:0 6px 18px rgba(23,22,15,.06);--radius:20px;--top:64px}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
button,select{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
svg{flex-shrink:0}
h1,h2{text-wrap:balance}
:focus-visible{outline:2px solid var(--accent2);outline-offset:2px;border-radius:8px}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.js-only{display:none!important}
.js .js-only{display:flex!important}
[hidden]{display:none!important}

/* Header */
.top{position:sticky;top:0;z-index:30;height:var(--top);background:rgba(246,244,239,.82);backdrop-filter:saturate(1.4) blur(20px);-webkit-backdrop-filter:saturate(1.4) blur(20px);border-bottom:1px solid var(--border)}
.top-inner{display:flex;align-items:center;gap:20px;height:100%}
.logo{font-size:21px;font-weight:800;letter-spacing:.02em}
.logo span{color:var(--accent)}
.top-links{display:flex;gap:4px;margin-left:8px}
.top-links a{display:flex;align-items:center;height:36px;font-size:14px;font-weight:600;color:var(--muted);padding:0 13px;border-radius:100px;transition:color .2s,background .2s}
.top-links a:hover{color:var(--ink);background:var(--bg3)}
.top-links a[aria-current]{color:var(--ink);background:var(--bg2);box-shadow:inset 0 0 0 1px var(--border)}
.top-cta{margin-left:auto;display:flex;align-items:center;gap:8px;height:40px;background:var(--ink);color:#fff;font-size:14px;font-weight:700;padding:0 20px 0 15px;border-radius:100px;white-space:nowrap;transition:transform .15s,background .2s}
.top-cta svg{width:16px;height:16px}
.top-cta:hover{background:#2a2820;transform:translateY(-1px)}

/* Intro */
.intro{padding-top:32px;padding-bottom:18px}
.crumbs{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);margin-bottom:8px}
.crumbs a{padding:6px 0}
.crumbs a:hover{color:var(--ink)}
h1{font-size:clamp(30px,5vw,48px);line-height:1.05;letter-spacing:-.035em;font-weight:800}
.lead{display:flex;align-items:flex-start;gap:9px;margin-top:12px;color:var(--muted);font-weight:600;font-size:15px}
.dot{width:8px;height:8px;margin-top:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 4px rgba(47,158,92,.15);flex-shrink:0}
.perks{list-style:none;display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.perks li{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;background:var(--bg2);border:1px solid var(--border);padding:6px 12px 6px 9px;border-radius:100px}
.perks svg{width:14px;height:14px;color:var(--ok-text)}
.search{align-items:center;gap:10px;background:var(--bg2);border:1px solid var(--border-strong);border-radius:16px;padding:0 14px;height:48px;max-width:560px;margin-top:20px;transition:border-color .2s,box-shadow .2s}
.search:focus-within{border-color:var(--accent2);box-shadow:0 0 0 4px rgba(163,129,79,.16)}
.search svg{width:19px;height:19px;color:var(--muted)}
.search input{flex:1;min-width:0;height:100%;border:0;outline:0;background:none;font:inherit;font-size:16px;color:var(--text)}
.search input::placeholder{color:var(--muted);opacity:1}

/* Toolbar: category tabs + filters/models, sticky under the header */
.toolbar{position:sticky;top:var(--top);z-index:20;background:rgba(246,244,239,.92);backdrop-filter:saturate(1.4) blur(20px);-webkit-backdrop-filter:saturate(1.4) blur(20px);border-bottom:1px solid transparent;transition:border-color .2s,box-shadow .2s}
.toolbar.is-stuck{border-bottom-color:var(--border);box-shadow:0 8px 24px rgba(23,22,15,.05)}
.toolbar-inner{--gutter:24px;display:flex;flex-direction:column;gap:10px;padding-top:4px;padding-bottom:10px}
.chips{display:flex;align-items:center;gap:6px;overflow-x:auto;scrollbar-width:none;margin:0 calc(-1 * var(--gutter));padding:2px var(--gutter);scroll-padding:0 var(--gutter)}
.chips::-webkit-scrollbar{display:none}
/* Categories are navigation: plain text with an underline on a hairline, not buttons */
.tabs{gap:26px;padding-top:0;padding-bottom:0;background:linear-gradient(var(--border-strong),var(--border-strong)) var(--gutter) 100%/calc(100% - 2 * var(--gutter)) 1px no-repeat}
.tab{display:flex;align-items:center;gap:6px;flex-shrink:0;white-space:nowrap;height:46px;font-size:15px;font-weight:600;color:var(--muted);box-shadow:inset 0 -2px 0 transparent;transition:color .2s,box-shadow .2s}
.tab span{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--muted);opacity:.8}
.tab:hover{color:var(--ink)}
.tab.is-active{color:var(--ink);font-weight:700;box-shadow:inset 0 -2px 0 var(--ink)}
.tab:focus-visible{outline-offset:-2px}
.controls{align-items:center;gap:14px}
.controls .refine{flex:1;min-width:0;margin:0;padding:2px 0;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 20px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 20px),transparent)}
.filters,.models{display:flex;gap:6px;flex-shrink:0}
.filters + .models{padding-left:10px;margin-left:4px;border-left:1px solid var(--border-strong)}
/* Filters are toggles: small chips that fill in when on */
.filter{display:flex;align-items:center;gap:6px;flex-shrink:0;white-space:nowrap;height:34px;padding:0 13px;font-size:13px;font-weight:600;border-radius:100px;background:var(--bg2);border:1px solid var(--border-strong);transition:background .2s,border-color .2s,color .2s}
.filter span{font-size:12px;color:var(--muted);font-weight:600}
.filter:hover{border-color:var(--accent)}
.filter[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:#fff;padding-left:10px}
.filter[aria-pressed=true]::before{content:'✓';font-size:12px}
.filter[aria-pressed=true] span{color:rgba(255,255,255,.7)}
.filter-sale::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--danger)}
.filter-sale[aria-pressed=true]{background:var(--danger);border-color:var(--danger)}
.filter-sale[aria-pressed=true]::before{width:auto;height:auto;background:none}

/* Result count + sorting */
.results{padding-bottom:24px}
.summary-text{flex-wrap:wrap;align-items:center;gap:0 12px;padding-top:14px;min-height:44px;font-size:14px;font-weight:600;color:var(--muted)}
.reset{font-size:14px;font-weight:700;color:var(--accent2);text-decoration:underline;text-underline-offset:3px;padding:8px 0}
.reset:hover{color:var(--ink)}
.sort{position:relative;display:flex;align-items:center;gap:6px;flex-shrink:0;font-size:13px;color:var(--muted)}
.sort-icon{width:15px;height:15px}
.sort select{-webkit-appearance:none;appearance:none;height:34px;padding:0 20px 0 0;font-size:13px;font-weight:700;color:var(--ink);border-radius:8px;transition:color .2s}
.sort:hover select{color:var(--accent2)}
.sort svg:last-child{position:absolute;right:0;width:15px;height:15px;pointer-events:none}
/* The count only earns a row once something narrows the list; the tabs already show totals. */
.js .results:not(.is-filtered) .summary-text{display:none!important}

.group{padding-top:18px;scroll-margin-top:calc(var(--top) + 120px)}
.group-title{display:flex;align-items:baseline;gap:8px;font-size:22px;letter-spacing:-.015em;margin-bottom:14px}
.group-title span{font-size:14px;color:var(--muted);font-weight:600}
.is-filtered .group-title{display:none}
.is-filtered .group{padding-top:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}

/* Card */
.card{position:relative;display:flex;flex-direction:column;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow-sm);transition:transform .25s ease,box-shadow .25s ease,border-color .25s;scroll-margin-top:calc(var(--top) + 130px)}
.card.is-capped{display:none}
.card:hover{transform:translateY(-3px);box-shadow:var(--shadow);border-color:var(--border-strong)}
.card:target{border-color:var(--accent);box-shadow:0 0 0 3px rgba(163,129,79,.25),var(--shadow)}
.card-media{position:relative;display:block;aspect-ratio:1/1;overflow:hidden;background:linear-gradient(160deg,#f1ede4,#e6e0d3)}
.card-media::before{content:'IIOS';position:absolute;inset:0;display:grid;place-items:center;font-size:26px;font-weight:800;letter-spacing:.04em;color:rgba(23,22,15,.13)}
.card-media img{position:relative;width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s ease}
.card:hover .card-media img{transform:scale(1.04)}
.tag{position:absolute;top:10px;z-index:1;font-size:12px;font-weight:700;padding:4px 10px;border-radius:100px;line-height:1.4;white-space:nowrap}
.tag-cond{left:10px;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:var(--ink);max-width:calc(100% - 84px);overflow:hidden;text-overflow:ellipsis}
.tag-new{color:var(--ok-text)}
.tag-sale{right:10px;background:var(--danger);color:#fff;font-weight:800}
.card-body{display:flex;flex-direction:column;gap:4px;padding:14px 16px 16px;flex:1}
.card-title{font-size:16.5px;line-height:1.3;font-weight:700;letter-spacing:-.01em}
.card-title a:hover{color:var(--accent2)}
.card-specs{font-size:13px;color:var(--muted)}
.card-note{font-size:13px;line-height:1.4;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-warranty{display:flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600;color:var(--accent2);margin-top:2px}
.card-warranty svg{width:13px;height:13px}
.card-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:auto;padding-top:12px}
.card-price{display:flex;flex-direction:column;line-height:1.15;min-width:0}
.price{font-size:21px;font-weight:800;letter-spacing:-.02em;color:var(--ink);white-space:nowrap}
.price-old{font-size:13px;color:var(--muted);text-decoration:line-through;margin-top:2px}
.price-ask{font-size:14px;font-weight:600;color:var(--muted)}
/* Outlined, so the price stays the loudest thing in the card */
.card-cta{display:flex;align-items:center;justify-content:center;gap:6px;flex-shrink:0;background:var(--bg2);color:var(--ink);border:1px solid var(--border-strong);font-size:14px;font-weight:700;height:42px;padding:0 16px 0 13px;border-radius:100px;transition:background .2s,color .2s,border-color .2s,transform .15s}
.card-cta svg{width:17px;height:17px;color:var(--accent2);transition:color .2s}
.card-cta:hover{background:var(--ink);border-color:var(--ink);color:#fff}
.card-cta:hover svg{color:#fff}
.card-cta:active{transform:scale(.97)}
/* Secondary to "Замовити": a quiet text link under the price row (opens /callback.js's form) */
.card-call{align-items:center;gap:6px;align-self:flex-start;margin-top:4px;padding:8px 0 0;font-size:13px;font-weight:600;color:var(--muted);transition:color .2s}
.card-call svg{width:14px;height:14px;color:var(--accent2)}
.card-call:hover{color:var(--ink)}

/* Show more, empty state, help band */
.more-wrap{display:flex;justify-content:center}
.more{margin-top:24px;height:48px;padding:0 28px;font-size:15px;font-weight:700;background:var(--bg2);border:1px solid var(--border-strong);border-radius:100px;transition:border-color .2s,background .2s}
.more:hover{border-color:var(--accent);background:var(--bg3)}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--ink);color:#fff;font-weight:700;font-size:15px;padding:13px 22px 13px 18px;border-radius:100px;transition:background .2s,transform .15s}
.btn svg{width:18px;height:18px}
.btn:hover{background:var(--accent2)}
.empty{text-align:center;background:var(--bg2);border:1px dashed var(--border-strong);border-radius:var(--radius);padding:44px 24px;margin:24px 0 8px}
.empty-title{font-size:20px;font-weight:800;margin-bottom:6px}
.empty-text{color:var(--muted);max-width:420px;margin:0 auto 18px}
.help{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-top:48px;margin-bottom:56px;background:var(--ink);color:#fff;border-radius:28px;padding:32px 36px;background-image:radial-gradient(600px 200px at 100% 0,rgba(163,129,79,.45),transparent)}
.help h2{font-size:24px;line-height:1.2;letter-spacing:-.02em;margin-bottom:6px}
.help p{color:rgba(255,255,255,.72);max-width:520px}
.btn-light{background:#fff;color:var(--ink);flex-shrink:0}
.btn-light:hover{background:var(--bg3)}

/* Footer (mirrors the landing) */
.foot{border-top:1px solid var(--border);margin-top:40px;padding:44px 0 calc(36px + env(safe-area-inset-bottom))}
.foot-top{display:grid;grid-template-columns:1.4fr 1fr auto;gap:32px 48px;align-items:start}
.foot-logo{font-size:18px;font-weight:700}
.foot-logo span{color:var(--accent)}
.foot-tagline{font-size:13px;color:var(--muted);line-height:1.6;margin-top:8px;max-width:260px}
.foot-label{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.foot-contacts{display:flex;flex-direction:column;font-style:normal;font-size:14px}
.foot-contacts a,.foot-contacts span{display:inline-flex;align-items:center;gap:10px;padding:7px 0;transition:color .15s}
.foot-contacts svg{width:16px;height:16px;color:var(--accent)}
.foot-links{display:flex;flex-direction:column;font-size:14px}
.foot-links a{padding:7px 0;transition:color .15s}
.foot a:hover{color:var(--accent2)}

@media (max-width:720px){
  /* Header scrolls away on phones; only the chip rows stay pinned. */
  :root{--top:0px}
  .wrap{padding:0 16px}
  .top{position:static;height:58px}
  .top-links{display:none}
  .intro{padding-top:14px;padding-bottom:12px}
  .perks{display:none}
  .search{height:46px;max-width:none;border-radius:14px;margin-top:16px}
  .toolbar-inner{--gutter:16px;padding-top:2px;padding-bottom:8px;gap:8px}
  .tabs{gap:22px}
  .tab{height:44px;font-size:14.5px}
  .controls{gap:10px}
  .sort-label{display:none}
  .summary-text{font-size:13px;padding-top:8px}
  /* 16px keeps iOS from zooming the page when the select opens */
  .sort select{font-size:16px;font-weight:600}
  .group-title{font-size:19px;margin-bottom:10px}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .card{border-radius:16px}
  .card:hover{transform:none}
  .tag{top:8px;font-size:11.5px;padding:3px 8px}
  .tag-cond{left:8px;max-width:calc(100% - 64px)}
  .tag-sale{right:8px}
  .card-body{padding:10px 11px 12px}
  .card-title{font-size:14.5px}
  .card-specs,.card-note{font-size:12.5px}
  .card-foot{flex-direction:column;align-items:stretch;gap:8px;padding-top:8px}
  .price{font-size:18px}
  .card-cta{height:40px;font-size:13.5px}
  .card-call{align-self:center;font-size:12.5px;margin-top:2px}
  .help{flex-direction:column;align-items:flex-start;padding:26px 22px;margin-top:36px;border-radius:24px}
  .help h2{font-size:20px}
  .foot-top{grid-template-columns:1fr;gap:26px;text-align:center;justify-items:center}
  .foot-tagline{margin-left:auto;margin-right:auto}
  .foot-contacts{align-items:center}
  .foot-links{flex-direction:row;flex-wrap:wrap;justify-content:center;gap:0 22px}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{transition:none!important}
}
`;
