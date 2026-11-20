// Renders /catalog from catalog.json in R2 (published by the bot, see
// store/services/site_catalog.py). Every other path is a free static asset and
// never reaches this script (run_worker_first in wrangler.jsonc).
//
// The page is complete without JavaScript (crawlers see every product);
// /catalog.js, a static asset, only adds search, tabs and filters on top.
//
// Every product also has its own page at /catalog/<id> (the landing page for
// Google Shopping), /feed.xml is the same catalog as a Google Merchant Center
// product feed, and /sitemap.xml lists the landing, /catalog and every
// product page.
//
// Free-tier safety: each rendered page is cached for CACHE_SECONDS under one
// fixed key per path (query strings ignored), so floods hit the edge cache,
// not R2; catalog.json itself is also kept in memory for CATALOG_MEMO_MS.
// Product ids are slugs (store/db/products_repo.py), so any other
// /catalog/... path is redirected without touching R2.
//
// /api/callback (the site's "Передзвоніть мені" form) lives in callback-api.js.

import { handleCallback } from './callback-api.js';

const SITE = 'https://i-ios.store';
const PAGE_PATH = '/catalog';
const CATALOG_KEY = 'catalog.json';
const BOT_URL = 'https://t.me/iios_cv_bot';
const CACHE_SECONDS = 300;
const CATALOG_MEMO_MS = 60_000;
const FEED_PATH = '/feed.xml';
const SITEMAP_PATH = '/sitemap.xml';
const PRODUCT_PATH_RE = /^\/catalog\/([a-z0-9][a-z0-9-]{0,63})\/?$/;

// Order and labels match the bot's categories (store/services/catalog_filter.py).
const CATEGORIES = [
  ['phone', 'iPhone'],
  ['ipad', 'iPad'],
  ['laptop', 'MacBook'],
  ['watch', 'Apple Watch'],
  ['headphones', 'Навушники'],
  ['notebook', 'Ноутбуки'],
  ['android', 'Android'],
  ['other_tech', 'Інша техніка'],
  ['accessories', 'Аксесуари'],
];

// Categories with at least MIN_CATEGORY_ITEMS products also get their own
// page at /catalog/<slug> (e.g. /catalog/iphone), so a search like "iPhone б/у
// Чернівці" lands on a page about exactly that. Thinner categories would make
// thin pages, so their slug redirects to the /catalog tab until they grow.
// The slugs are reserved for product ids (RESERVED_IDS in
// store/db/products_repo.py); keep both lists in sync.
const MIN_CATEGORY_ITEMS = 4;
const CATEGORY_PAGES = {
  phone: { slug: 'iphone', buy: 'iPhone', h1: 'iPhone у Чернівцях', noun: 'iPhone' },
  ipad: { slug: 'ipad', buy: 'iPad', h1: 'iPad у Чернівцях', noun: 'iPad' },
  laptop: { slug: 'macbook', buy: 'MacBook', h1: 'MacBook у Чернівцях', noun: 'MacBook' },
  watch: { slug: 'apple-watch', buy: 'Apple Watch', h1: 'Apple Watch у Чернівцях', noun: 'Apple Watch' },
  headphones: { slug: 'navushnyky', buy: 'навушники', h1: 'Навушники у Чернівцях', noun: 'навушники' },
  notebook: { slug: 'noutbuky', buy: 'ноутбук', h1: 'Ноутбуки у Чернівцях', noun: 'ноутбуки' },
  android: { slug: 'android', buy: 'смартфон Android', h1: 'Смартфони Android у Чернівцях', noun: 'смартфони Android' },
  other_tech: { slug: 'insha-tekhnika', buy: 'техніку', h1: 'Інша техніка в Чернівцях', noun: 'пристрої' },
  accessories: { slug: 'aksesuary', buy: 'аксесуари', h1: 'Аксесуари в Чернівцях', noun: 'аксесуари' },
};
const CATEGORY_BY_SLUG = Object.fromEntries(
  Object.entries(CATEGORY_PAGES).map(([key, page]) => [page.slug, key]),
);

// Same policy as _headers (which only covers static assets). Scripts are
// limited to our own /catalog.js; JSON-LD blocks are data, not executed.
const SECURITY_HEADERS = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self' https://img.i-ios.store; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'; upgrade-insecure-requests",
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
    if (url.pathname === FEED_PATH) {
      return serveCached(request, url, ctx, FEED_PATH, () => renderFeed(env));
    }
    if (url.pathname === SITEMAP_PATH) {
      return serveCached(request, url, ctx, SITEMAP_PATH, () => renderSitemap(env));
    }
    if (url.pathname.startsWith(PAGE_PATH + '/')) {
      const match = PRODUCT_PATH_RE.exec(url.pathname);
      // "/catalog/" and anything that can't be a product id → the catalog.
      if (!match) return Response.redirect(url.origin + PAGE_PATH, 301);
      const path = `${PAGE_PATH}/${match[1]}`;
      if (url.pathname !== path) return Response.redirect(url.origin + path, 301);
      const category = CATEGORY_BY_SLUG[match[1]];
      if (category) return serveCached(request, url, ctx, path, () => renderCategory(env, category));
      return serveCached(request, url, ctx, path, () => renderProduct(env, match[1]));
    }
    if (url.pathname !== PAGE_PATH) {
      return env.ASSETS.fetch(request);
    }
    return serveCached(request, url, ctx, PAGE_PATH, () => render(env));
  },
};

// Serves a rendered response from the edge cache under one fixed key (query
// strings ignored), rendering it on a miss. Error responses are cached too
// (for a minute), so a flood can't turn a missing catalog.json into an R2
// read per request.
async function serveCached(request, url, ctx, path, renderFn) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  const cache = caches.default;
  const cacheKey = new Request(url.origin + path, { method: 'GET' });
  let response = await cache.match(cacheKey);
  if (!response) {
    response = await renderFn();
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }

  const headers = new Headers(response.headers);
  if (url.hostname.endsWith('.workers.dev')) headers.set('X-Robots-Tag', 'noindex');
  const body = request.method === 'HEAD' ? null : response.body;
  return new Response(body, { status: response.status, headers });
}

// catalog.json from R2, or null when it is missing or unreadable. Kept in the
// isolate's memory for a minute, so a burst of product pages (each its own
// cache key) costs one R2 read, not one per page. Misses are kept too.
let catalogMemo = null;

async function loadCatalog(env) {
  if (catalogMemo && Date.now() - catalogMemo.at < CATALOG_MEMO_MS) return catalogMemo.catalog;
  let catalog = null;
  try {
    const object = await env.CATALOG.get(CATALOG_KEY);
    catalog = object ? await object.json() : null;
    if (!catalog || !Array.isArray(catalog.items)) catalog = null;
  } catch {
    catalog = null;
  }
  if (catalog) catalog.items = catalog.items.filter(i => i && i.id && i.name);
  catalogMemo = { at: Date.now(), catalog };
  return catalog;
}

// Temporary: tell crawlers to come back later.
const UNAVAILABLE = { 'Retry-After': '600', 'Cache-Control': 'public, max-age=60' };
const CACHED = { 'Cache-Control': `public, max-age=${CACHE_SECONDS}` };

async function render(env) {
  const catalog = await loadCatalog(env);
  if (!catalog) return htmlResponse(page([], null), 503, UNAVAILABLE);
  return htmlResponse(page(catalog.items, catalog.updated_at), 200, CACHED);
}

async function renderCategory(env, key) {
  const catalog = await loadCatalog(env);
  if (!catalog) return htmlResponse(missingPage(true), 503, UNAVAILABLE);
  if (!hasCategoryPage(key, catalog.items)) {
    // Temporary (302): the page comes back once the category fills up again.
    return new Response(null, {
      status: 302,
      headers: { Location: `${SITE}${PAGE_PATH}#${key}`, 'Cache-Control': 'public, max-age=60' },
    });
  }
  return htmlResponse(page(catalog.items, catalog.updated_at, key), 200, CACHED);
}

function categoryCount(key, items) {
  return items.reduce((n, item) => n + ((item.category || 'other') === key ? 1 : 0), 0);
}

function hasCategoryPage(key, items) {
  return Boolean(CATEGORY_PAGES[key]) && categoryCount(key, items) >= MIN_CATEGORY_ITEMS;
}

// A category's own page when it has one, else its tab on /catalog.
function categoryPath(key, items) {
  return hasCategoryPage(key, items)
    ? `${PAGE_PATH}/${CATEGORY_PAGES[key].slug}`
    : `${PAGE_PATH}#${encodeURIComponent(key)}`;
}

async function renderProduct(env, id) {
  const catalog = await loadCatalog(env);
  if (!catalog) return htmlResponse(missingPage(true), 503, UNAVAILABLE);
  const item = catalog.items.find(i => i.id === id);
  // Sold out (or never existed): a real 404, so Google drops the page.
  if (!item) return htmlResponse(missingPage(false), 404, CACHED);
  const related = catalog.items
    .filter(i => i !== item && i.category === item.category)
    .slice(0, 4);
  return htmlResponse(productPage(item, related, catalog.items), 200, CACHED);
}

async function renderSitemap(env) {
  const catalog = await loadCatalog(env);
  const lastmod = catalog && catalog.updated_at
    ? new Date(catalog.updated_at * 1000).toISOString().slice(0, 10)
    : null;
  const entry = (loc, mod) => `  <url>\n    <loc>${esc(loc)}</loc>${mod ? `\n    <lastmod>${mod}</lastmod>` : ''}\n  </url>`;
  const items = catalog ? catalog.items : [];
  const categories = Object.keys(CATEGORY_PAGES).filter(key => hasCategoryPage(key, items));
  const urls = [
    entry(`${SITE}/`),
    entry(`${SITE}${PAGE_PATH}`, lastmod),
    ...categories.map(key => entry(SITE + categoryPath(key, items), lastmod)),
    ...items.map(item => entry(productUrl(item), lastmod)),
  ];
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join('\n')}
</urlset>
`;
  return new Response(xml, {
    status: 200,
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      ...(catalog ? CACHED : { 'Cache-Control': 'public, max-age=60' }),
    },
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

// "new" / "used" / "" from the admin's free-text condition. Accessories are
// sold new, so one with no condition typed counts as new (and reaches the
// Google feed); any other product without one stays unknown.
function conditionKind(item) {
  const text = (item.condition || '').toLowerCase();
  if (text.includes('нов')) return 'new';
  if (text.includes('вжив') || text.includes('б/у') || text.includes('б/в')) return 'used';
  if (!text && item.category === 'accessories') return 'new';
  return '';
}

const CONDITION_SCHEMA = {
  new: 'https://schema.org/NewCondition',
  used: 'https://schema.org/UsedCondition',
};

// Its own page; an id that isn't a slug (none should be) or that a category
// page owns falls back to its card on /catalog, since PRODUCT_PATH_RE would
// redirect it away and a category slug would show the category instead.
function productPath(item) {
  return PRODUCT_PATH_RE.test(`${PAGE_PATH}/${item.id}`) && !CATEGORY_BY_SLUG[item.id]
    ? `${PAGE_PATH}/${item.id}`
    : `${PAGE_PATH}#p-${encodeURIComponent(item.id)}`;
}

function productUrl(item) {
  return SITE + productPath(item);
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

// Bing flags meta descriptions over 160 characters, so categories are
// listed only while the whole sentence still fits.
const DESCRIPTION_MAX = 160;

function catalogDescription(count, labels, warranty) {
  const head = `${count} ${plural(count, 'товар', 'товари', 'товарів')} в наявності в IIOS (Чернівці)`;
  const tail = `. Нові та вживані, ${warranty ? `гарантія ${warrantyText(warranty)}` : 'гарантія магазину'}, доставка по Україні.`;
  const shown = labels.slice();
  const build = () => head
    + (shown.length ? ': ' + shown.join(', ') + (shown.length < labels.length ? ' та інше' : '') : '')
    + tail;
  while (shown.length && build().length > DESCRIPTION_MAX) shown.pop();
  return build();
}

// ── Structured data ───────────────────────────────────────────

// "<" is escaped so product text can never close the script element.
function ldScripts(blocks) {
  return blocks
    .map(data => `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`)
    .join('\n  ');
}

function breadcrumbsLd(trail) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map(([name, url], index) => ({
      '@type': 'ListItem', position: index + 1, name, item: url,
    })),
  };
}

// The catalog is a summary page: it lists the product pages, and the full
// Product markup lives on each of them (Google's product-carousel pattern).
function jsonLd(items, name, trail) {
  const list = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name,
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem', position: index + 1, url: productUrl(item),
    })),
  };
  return ldScripts([list, breadcrumbsLd(trail)]);
}

function productLd(item, all) {
  const { currency, regular, sale } = prices(item);
  const url = productUrl(item);
  const brand = feedBrand(item);
  const product = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    '@id': `${url}#product`,
    name: feedTitle(item),
    url,
    sku: item.id,
    image: safeImage(item.image) ? [item.image] : undefined,
    description: item.description || undefined,
    brand: brand ? { '@type': 'Brand', name: brand } : undefined,
    color: item.color || undefined,
  };
  const d = deviceDetails(item);
  const properties = [
    d.grade ? ['Стан', d.grade.label] : null,
    batteryText(d) ? ['Акумулятор', batteryText(d)] : null,
    d.sim ? ['SIM', d.sim] : null,
    d.kit.length ? ['Комплект', kitText(d)] : null,
  ].filter(Boolean);
  if (properties.length) {
    product.additionalProperty = properties.map(([name, value]) => ({ '@type': 'PropertyValue', name, value }));
  }
  if (regular) {
    product.offers = {
      '@type': 'Offer',
      url,
      price: sale || regular,
      priceCurrency: currency,
      // The struck-through price Google shows next to a sale price.
      priceSpecification: sale ? {
        '@type': 'UnitPriceSpecification',
        priceType: 'https://schema.org/StrikethroughPrice',
        price: regular,
        priceCurrency: currency,
      } : undefined,
      availability: 'https://schema.org/InStock',
      itemCondition: CONDITION_SCHEMA[conditionKind(item)],
      seller: { '@type': 'Organization', name: 'IIOS', url: `${SITE}/` },
      warranty: item.warranty_days ? {
        '@type': 'WarrantyPromise',
        durationOfWarranty: { '@type': 'QuantitativeValue', value: item.warranty_days, unitCode: 'DAY' },
      } : undefined,
    };
  }
  // A category with its own page is a crumb; a #tab of /catalog is not a page.
  const key = item.category || 'other';
  const trail = [['IIOS', `${SITE}/`], ['Каталог', `${SITE}${PAGE_PATH}`]];
  if (hasCategoryPage(key, all)) trail.push([categoryLabel(key, item), SITE + categoryPath(key, all)]);
  trail.push([item.name, url]);
  return ldScripts([product, breadcrumbsLd(trail)]);
}

// ── Merchant Center feed ──────────────────────────────────────
// RSS 2.0 with Google's g: attributes, fetched by Merchant Center on a
// schedule. Each item links to its /catalog/<id> page, which shows the same
// price, so Google's landing-page checks pass. Shipping and return policies
// are set in Merchant Center itself, not here.
//
// Only UAH prices are listed (Google Shopping in Ukraine accepts nothing
// else); the bot converts dollar-only products by the admin's /rate.

// Categories whose products are always Apple.
const APPLE_CATEGORIES = new Set(['phone', 'ipad', 'laptop', 'watch']);

// Other brands the store carries; the first one named in the title wins.
const KNOWN_BRANDS = [
  'Apple', 'Samsung', 'Xiaomi', 'Redmi', 'Poco', 'Google', 'OnePlus', 'Motorola', 'Huawei',
  'Honor', 'Realme', 'Oppo', 'Nokia', 'Sony', 'Lenovo', 'HP', 'Dell', 'Asus', 'Acer', 'MSI',
  'Microsoft', 'JBL', 'Marshall', 'Remax', 'Baseus', 'Anker', 'Ugreen', 'Belkin', 'Spigen',
];

function feedBrand(item) {
  if (APPLE_CATEGORIES.has(item.category)) return 'Apple';
  const name = item.name.toLowerCase();
  const brand = KNOWN_BRANDS.find(b => new RegExp(`(^|[^a-z])${b.toLowerCase()}([^a-z]|$)`).test(name));
  if (brand) return brand;
  return /^(iphone|ipad|macbook|airpods|apple watch|imac|mac )/i.test(item.name) ? 'Apple' : null;
}

// Characters XML 1.0 forbids (stray control codes in admin-typed text).
function xmlText(value) {
  return esc(String(value ?? '').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, ''));
}

function feedPrice(amount, currency) {
  return `${Number(amount).toFixed(2)} ${currency}`;
}

function feedTitle(item) {
  const parts = [item.name];
  for (const extra of [item.storage, item.color]) {
    if (extra && !item.name.toLowerCase().includes(extra.toLowerCase())) parts.push(extra);
  }
  return parts.join(' ').slice(0, 150);
}

function feedItem(item) {
  const { currency, regular, sale } = prices(item);
  const condition = conditionKind(item);
  const image = safeImage(item.image);
  // Google needs a price in UAH, an image and a known condition (an item with
  // no condition is treated as new, which a used phone must never be).
  if (!regular || currency !== 'UAH' || !image || !condition) return null;

  const title = feedTitle(item);
  const description = item.description || `${title}. ${condition === 'new' ? 'Новий' : 'Вживаний'}.`;
  const brand = feedBrand(item);
  const productType = [item.category_label, item.subcategory_label].filter(Boolean).join(' > ');
  // Short selling points Google may show under the listing.
  const d = deviceDetails(item);
  const highlights = [
    item.warranty_days ? `Гарантія ${warrantyText(item.warranty_days)} від магазину` : '',
    d.grade ? `Стан: ${d.grade.label.toLowerCase()}` : '',
    d.battery !== null ? `Ємність акумулятора ${d.battery}%` : '',
    d.sim ? `SIM: ${d.sim}` : '',
  ].filter(Boolean);
  const fields = [
    ['g:id', item.id],
    ['g:title', title],
    ['g:description', description.slice(0, 5000)],
    ['g:link', productUrl(item)],
    ['g:image_link', image],
    ['g:availability', 'in_stock'],
    ['g:price', feedPrice(regular, currency)],
    sale ? ['g:sale_price', feedPrice(sale, currency)] : null,
    ['g:condition', condition],
    brand ? ['g:brand', brand] : null,
    // No GTIN/MPN is recorded for any product; saying so avoids
    // "missing identifier" warnings in Merchant Center.
    ['g:identifier_exists', 'no'],
    item.color ? ['g:color', item.color] : null,
    productType ? ['g:product_type', productType] : null,
    // Google's spec asks for 2–100 highlights, so a lone one is left out.
    ...(highlights.length >= 2 ? highlights.map(h => ['g:product_highlight', h]) : []),
  ].filter(Boolean);
  return '    <item>\n'
    + fields.map(([tag, value]) => `      <${tag}>${xmlText(value)}</${tag}>`).join('\n')
    + '\n    </item>';
}

async function renderFeed(env) {
  const catalog = await loadCatalog(env);
  if (!catalog) {
    return new Response('Catalog temporarily unavailable', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '600', 'Cache-Control': 'public, max-age=60' },
    });
  }
  const items = catalog.items
    .filter(i => i && i.id && i.name)
    .map(feedItem)
    .filter(Boolean);
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
  <channel>
    <title>IIOS — техніка Apple у Чернівцях</title>
    <link>${SITE}${PAGE_PATH}</link>
    <description>Товари в наявності в магазині IIOS</description>
${items.join('\n')}
  </channel>
</rss>
`;
  return new Response(xml, {
    status: 200,
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': `public, max-age=${CACHE_SECONDS}`,
      'X-Content-Type-Options': 'nosniff',
    },
  });
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
const ICON_BATTERY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="7" width="17" height="10" rx="2.5"/><path d="M22 11v2"/><path d="M6 10.5v3M9.5 10.5v3M13 10.5v3"/></svg>';
const ICON_SPARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/></svg>';
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

// ── Device details ────────────────────────────────────────────
// Admins type a device's details as lines of its description, in the format
// the bot's /add prompt suggests (store/handlers/admin/add.py):
//   Фізична SIM + E-Sim
//   Стан: Відмінний
//   АКБ 100% (53 цикли)
//   Комплект: гарантія | кабель | коробка
//   Замінено задню кришку
// They are read back here, so cards show them as badges and catalog.js can
// filter on them, without new database fields. Lines that match nothing stay
// free notes. Channel posts and the bot keep showing the description as typed.

// Cosmetic grades as admins write them. The tier drives the "Ідеальний стан"
// filter and the badge colour; an unknown wording is shown as typed.
const GRADES = [
  [/ідеальн/i, 'Ідеальний', 'top'],
  [/як\s*нов/i, 'Як новий', 'top'],
  [/відмінн/i, 'Відмінний', 'great'],
  [/хорош/i, 'Хороший', 'good'],
  [/задовільн/i, 'Задовільний', 'fair'],
];

// Shown on the product page under «Що означає стан». Keep it to what the
// store actually promises for each grade.
const GRADE_NOTES = [
  ['Ідеальний / Як новий', 'Без помітних слідів використання.'],
  ['Відмінний', 'Мінімальні сліди використання, помітні лише при уважному огляді.'],
  ['Хороший', 'Є помітні потертості або дрібні подряпини на корпусі.'],
];

const BATTERY_RE = /^(?:акб|акумулятор|батаре[яїю])(?![а-яіїєґ'’])\s*[:\-–—]?\s*(.*)$/i;
const GRADE_RE = /^стан\s*[:\-–—]\s*(.+)$/i;
const KIT_RE = /^комплект(?:ація)?\s*[:\-–—]\s*(.+)$/i;
const REPAIR_RE = /замін|ремонт/i;

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function gradeOf(text) {
  const clean = text.replace(/[!.\s]+$/, '').trim();
  const known = GRADES.find(([re]) => re.test(clean));
  return known ? { label: known[1], tier: known[2] } : { label: capitalize(clean), tier: '' };
}

// "Фізична SIM + E-Sim" → "SIM + eSIM"; "E-Sim" alone → "Лише eSIM" (worth
// spelling out: such an iPhone takes no physical card).
function simOf(line) {
  const esim = /e-?\s?sim/i.test(line);
  const physical = /sim|фіз/i.test(line.replace(/e-?\s?sim/gi, ''));
  if (esim && physical) return 'SIM + eSIM';
  if (esim) return 'Лише eSIM';
  if (physical) return capitalize(line.replace(/\s+/g, ' '));
  return '';
}

const detailsMemo = new WeakMap();

function deviceDetails(item) {
  if (detailsMemo.has(item)) return detailsMemo.get(item);
  const out = { grade: null, battery: null, batteryNew: false, cycles: null, sim: '', kit: [], repairs: [], notes: [] };
  // Accessories carry specs ("Type-C", "30W"), never device details.
  const lines = String(item.description || '').split('\n').map(s => s.trim()).filter(Boolean);
  for (const line of lines) {
    let m;
    if (item.category === 'accessories') { out.notes.push(line); continue; }
    if (!out.grade && (m = GRADE_RE.exec(line))) { out.grade = gradeOf(m[1]); continue; }
    if ((m = BATTERY_RE.exec(line))) {
      const pct = /(\d{1,3})\s*%/.exec(m[1]);
      const cycles = /(\d+)\s*цикл/i.exec(m[1]);
      if (pct && Number(pct[1]) <= 100) out.battery = Number(pct[1]);
      if (cycles) out.cycles = Number(cycles[1]);
      if (/нов/i.test(m[1])) out.batteryNew = true;
      if (out.battery !== null || out.cycles !== null || out.batteryNew) continue;
    }
    if (!out.kit.length && (m = KIT_RE.exec(line))) {
      out.kit = m[1].split(/[|,;]/).map(s => s.trim()).filter(Boolean);
      continue;
    }
    if (!out.sim && line.length <= 40 && /sim/i.test(line)) {
      out.sim = simOf(line);
      if (out.sim) continue;
    }
    if (REPAIR_RE.test(line)) { out.repairs.push(capitalize(line)); continue; }
    out.notes.push(line);
  }
  detailsMemo.set(item, out);
  return out;
}

function hasDetails(d) {
  return Boolean(d.grade || d.battery !== null || d.cycles !== null || d.batteryNew || d.sim || d.kit.length || d.repairs.length);
}

// "100%", "100% · 53 цикли", "96 циклів", "Нова".
function batteryText(d) {
  const parts = [];
  if (d.battery !== null) parts.push(`${d.battery}%`);
  else if (d.batteryNew) parts.push('Нова');
  if (d.cycles !== null) parts.push(`${d.cycles} ${plural(d.cycles, 'цикл', 'цикли', 'циклів')}`);
  return parts.join(' · ');
}

// Short form for the card badge.
function batteryBadge(d) {
  if (d.battery !== null) return `АКБ ${d.battery}%`;
  if (d.batteryNew) return 'АКБ нова';
  if (d.cycles !== null) return `АКБ: ${d.cycles} ${plural(d.cycles, 'цикл', 'цикли', 'циклів')}`;
  return '';
}

function batteryGood(d) {
  return d.batteryNew || (d.battery !== null && d.battery >= 90);
}

function kitText(d) {
  return capitalize(d.kit.join(', ').toLowerCase());
}

function warrantyText(days) {
  return `${days} ${plural(days, 'день', 'дні', 'днів')}`;
}

// The warranty most devices carry (accessories aside), for site-wide copy:
// "Гарантія 90 днів". Null when no device has one.
function storeWarranty(items) {
  const counts = new Map();
  for (const item of items) {
    if (item.category === 'accessories' || !item.warranty_days) continue;
    counts.set(item.warranty_days, (counts.get(item.warranty_days) || 0) + 1);
  }
  let best = null;
  for (const [days, n] of counts) if (!best || n > best[1]) best = [days, n];
  return best ? best[0] : null;
}

function card(item, index, rate) {
  const { regular, sale, fmt } = prices(item);
  const image = safeImage(item.image);
  const kind = conditionKind(item);
  const d = deviceDetails(item);
  // Short label on the photo (never truncated); the admin's full wording,
  // when longer ("Новий запечатаний"), leads the specs line instead.
  const condShort = kind === 'new' ? 'Новий' : kind === 'used' ? 'Вживаний' : (item.condition || '');
  const condFull = item.condition && item.condition !== condShort ? item.condition : '';
  const specs = [condFull, item.storage, item.color, d.sim].filter(Boolean).join(' · ');
  // Grade and battery are what a used-phone buyer looks at first.
  const badges = [
    d.grade ? `<span class="badge badge-grade badge-${d.grade.tier || 'other'}">${ICON_SPARK}${esc(d.grade.label)}</span>` : '',
    batteryBadge(d) ? `<span class="badge badge-bat${batteryGood(d) ? ' is-good' : ''}">${ICON_BATTERY}${esc(batteryBadge(d))}</span>` : '',
  ].join('');
  const note = badges ? '' : firstLine(d.notes.join('\n') || item.description);
  const search = [item.name, item.storage, item.color, item.condition, item.category_label, item.subcategory_label, item.description, d.grade && d.grade.label, d.sim]
    .filter(Boolean).join(' ').toLowerCase();
  const order = sortPrice(item, rate);
  // Photo and name open the product page; "Замовити" goes straight to the bot.
  const pageHref = esc(productPath(item));
  const link = esc(botLink(item));

  let price = '<span class="price-ask">Ціна в боті</span>';
  if (sale) price = `<span class="price">${esc(fmt(sale))}</span><span class="price-old">${esc(fmt(regular))}</span>`;
  else if (regular) price = `<span class="price">${esc(fmt(regular))}</span>`;

  // The first row loads eagerly so the page doesn't open on empty frames.
  const loading = index < 4 ? 'eager' : 'lazy';
  return `
        <article class="card" id="p-${esc(item.id)}" data-i="${index}" data-cat="${esc(item.category || 'other')}" data-sub="${esc(item.subcategory_label || '')}" data-cond="${kind}" data-sale="${sale ? 1 : 0}" data-price="${order ?? ''}" data-bat="${batteryGood(d) ? 1 : 0}" data-grade="${esc(d.grade ? d.grade.tier : '')}" data-q="${esc(search)}">
          <a class="card-media" href="${pageHref}" tabindex="-1" aria-hidden="true">
            ${image ? `<img src="${esc(image)}" alt="" width="480" height="480" loading="${loading}" decoding="async">` : ''}
            ${condShort ? `<span class="tag tag-cond tag-${kind || 'other'}">${esc(condShort)}</span>` : ''}
            ${sale ? `<span class="tag tag-sale">−${Math.round((1 - sale / regular) * 100)}%</span>` : ''}
            ${item.warranty_days ? `<span class="tag tag-warranty">${ICON_SHIELD}Гарантія ${esc(warrantyText(item.warranty_days))}</span>` : ''}
          </a>
          <div class="card-body">
            <h3 class="card-title"><a href="${pageHref}">${esc(item.name)}</a></h3>
            ${specs ? `<p class="card-specs">${esc(specs)}</p>` : ''}
            ${badges ? `<p class="badges">${badges}</p>` : ''}
            ${note ? `<p class="card-note">${esc(note)}</p>` : ''}
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

// The lowest shown UAH price among items, formatted ("9 500 ₴"), or ''.
function minPriceText(items) {
  let min = null;
  for (const item of items) {
    const { currency, regular, sale, fmt } = prices(item);
    const shown = sale || regular;
    if (currency === 'UAH' && shown && (min === null || shown < min.value)) min = { value: shown, fmt };
  }
  return min ? min.fmt(min.value) : '';
}

// Title, description, heading and intro of a category page, from what is in
// stock right now: the condition words and the "від" price follow the items.
// "б/у" (how people search) appears only in the title; the page says "вживані".
// "у Чернівцях" after a consonant, "в Чернівцях" after a vowel (милозвучність).
function inAfter(word) {
  return /[аеєиіїоуюя]$/i.test(word) ? 'в' : 'у';
}

function categoryCopy(key, items) {
  const meta = CATEGORY_PAGES[key];
  const hasNew = items.some(i => conditionKind(i) === 'new');
  const hasUsed = items.some(i => conditionKind(i) === 'used');
  const from = minPriceText(items);
  const titleCond = hasUsed ? (hasNew ? 'нові та б/у' : 'б/у') : '';
  const title = `Купити ${meta.buy} ${inAfter(meta.buy)} Чернівцях — ${[titleCond, from ? `ціни від ${from}` : 'ціни'].filter(Boolean).join(', ')} | IIOS`;
  const cond = hasNew && hasUsed ? 'Нові та вживані' : hasUsed ? 'Вживані' : hasNew ? 'Нові' : '';
  const lead = cond ? `${cond} ${meta.noun}` : meta.noun.charAt(0).toUpperCase() + meta.noun.slice(1);
  const count = `${items.length} ${plural(items.length, 'товар', 'товари', 'товарів')} в наявності`;
  const days = storeWarranty(items);
  const description = clip(
    `${lead} ${inAfter(lead)} магазині IIOS, Чернівці: ${count}${from ? `, від ${from}` : ''}. `
      + `${days ? `Гарантія ${warrantyText(days)}` : 'Гарантія магазину'}, доставка Новою поштою, замовлення в Telegram.`,
    DESCRIPTION_MAX,
  );
  const intro = [
    `${lead} з гарантією ${days ? `${warrantyText(days)} від магазину IIOS` : 'магазину IIOS'}. Забрати можна в магазині в Чернівцях або замовити доставку Новою поштою по Україні.`,
    hasUsed ? 'Стан, акумулятор і комплект вживаних пристроїв вказані в їхніх картках, а перевірити пристрій можна в магазині або у відділенні Нової пошти до оплати.' : '',
  ].filter(Boolean).join(' ');
  return { title, description, h1: meta.h1, intro, label: categoryLabel(key, items[0]) };
}

// The whole catalog, or with `scope` one category's own page: the same
// layout, holding only that category's cards, with its own title and heading.
// The tabs stay, as links to the other categories' pages.
function page(allItems, updatedAt, scope = null) {
  const items = scope ? allItems.filter(i => (i.category || 'other') === scope) : allItems;
  const allGroups = groupByCategory(allItems);
  const groups = scope ? allGroups.filter(([key]) => key === scope) : allGroups;
  const copy = scope ? categoryCopy(scope, items) : null;
  const warranty = storeWarranty(items);
  const title = copy ? copy.title : 'Каталог iPhone, MacBook, AirPods у Чернівцях — ціни | IIOS';
  const description = copy ? copy.description : items.length
    ? catalogDescription(items.length, groups.map(([, g]) => g.label), warranty)
    : 'Каталог нової та вживаної техніки Apple в магазині IIOS у Чернівцях: iPhone, MacBook, AirPods, Apple Watch. Гарантія магазину, доставка по Україні.';
  const canonical = SITE + (scope ? categoryPath(scope, allItems) : PAGE_PATH);
  const trail = [['IIOS', `${SITE}/`], ['Каталог', `${SITE}${PAGE_PATH}`]];
  if (copy) trail.push([copy.label, canonical]);
  const ld = jsonLd(items, copy ? copy.h1 : 'Каталог IIOS — техніка Apple у Чернівцях', trail);

  // Every category is listed for catalog.js, so /catalog#watch from the
  // landing can say "nothing in stock right now" instead of showing nothing.
  const labels = Object.fromEntries(CATEGORIES);
  for (const [key, g] of allGroups) labels[key] = g.label;

  // On /catalog the tabs filter in place (catalog.js), but their hrefs are the
  // category pages, so crawlers follow them. On a category page they are plain
  // links (no data-tab), with the open category marked as the current page.
  const tabs = scope
    ? [
      `<a class="tab" href="${PAGE_PATH}">Усі <span>${allItems.length}</span></a>`,
      ...allGroups.map(([key, g]) => {
        const current = key === scope ? ' is-active" aria-current="page' : '';
        return `<a class="tab${current}" href="${esc(categoryPath(key, allItems))}">${esc(g.label)} <span>${g.items.length}</span></a>`;
      }),
    ].join('')
    : [
      `<a class="tab is-active" href="#all" data-tab="all">Усі <span>${items.length}</span></a>`,
      ...groups.map(([key, g]) => `<a class="tab" href="${esc(categoryPath(key, allItems))}" data-tab="${esc(key)}">${esc(g.label)} <span>${g.items.length}</span></a>`),
    ].join('');
  const hasNew = items.some(i => conditionKind(i) === 'new');
  const hasUsed = items.some(i => conditionKind(i) === 'used');
  const hasSale = items.some(i => prices(i).sale);
  // Condition filters appear only when they would actually split the list.
  const details = items.map(deviceDetails);
  const batteries = details.filter(d => d.battery !== null || d.batteryNew);
  const hasBattery = batteries.some(batteryGood) && batteries.some(d => !batteryGood(d));
  const tiers = details.filter(d => d.grade && d.grade.tier).map(d => d.grade.tier);
  const hasTop = tiers.includes('top') && tiers.some(t => t !== 'top');
  const filters = [
    hasNew && hasUsed ? '<button type="button" class="filter" data-filter="new" aria-pressed="false">Нові</button>' : '',
    hasNew && hasUsed ? '<button type="button" class="filter" data-filter="used" aria-pressed="false">Вживані</button>' : '',
    hasSale ? '<button type="button" class="filter filter-sale" data-filter="sale" aria-pressed="false">Знижки</button>' : '',
    hasTop ? '<button type="button" class="filter" data-filter="top" aria-pressed="false">Ідеальний стан</button>' : '',
    hasBattery ? '<button type="button" class="filter" data-filter="bat" aria-pressed="false">АКБ 90%+</button>' : '',
  ].join('');

  let index = 0;
  const rate = uahPerUsd(items);
  const sections = groups.map(([key, g]) => `
      <section class="group" id="${esc(key)}" data-group="${esc(key)}">${scope ? `
        <h2 class="sr">${esc(g.label)}: товари в наявності</h2>` : `
        <h2 class="group-title">${esc(g.label)} <span>${g.items.length}</span></h2>`}
        <div class="grid">${g.items.map(item => card(item, index++, rate)).join('')}
        </div>
      </section>`).join('');

  const lead = items.length
    ? `${items.length} ${plural(items.length, 'товар', 'товари', 'товарів')} в наявності${updatedAt ? ` · оновлено ${esc(formatDate(updatedAt))}` : ''}`
    : 'Каталог саме оновлюється';

  const crumbs = scope
    ? `<a href="/">Головна</a><span aria-hidden="true">/</span><a href="${PAGE_PATH}">Каталог</a><span aria-hidden="true">/</span><span aria-current="page">${esc(copy.label)}</span>`
    : '<a href="/">Головна</a><span aria-hidden="true">/</span>Каталог';
  const searchHint = scope ? 'Пошук: модель, пам’ять, колір…' : 'Пошук: iPhone 15, 256GB, колір…';

  return `${documentHead({ title, description, canonical, ld })}
<body data-labels="${esc(JSON.stringify(labels))}" data-bot="${BOT_URL}"${scope ? ` data-scope="${esc(scope)}"` : ''}>
  ${siteHeader(!scope)}

  <main>
    <section class="intro wrap">
      <nav class="crumbs" aria-label="Навігаційний ланцюжок">${crumbs}</nav>
      <h1>${esc(copy ? copy.h1 : 'Каталог техніки Apple')}</h1>
      ${items.length ? `<p class="lead"><span class="dot" aria-hidden="true"></span><span>${lead}</span></p>` : ''}
      ${copy ? `<p class="intro-text">${esc(copy.intro)}</p>` : ''}
      <ul class="perks">
        ${warranty
          ? `<li class="perk-warranty">${ICON_SHIELD}Гарантія ${esc(warrantyText(warranty))} на техніку</li>`
          : `<li>${ICON_CHECK}Гарантія магазину</li>`}
        <li>${ICON_CHECK}Доставка Новою поштою</li>
        <li>${ICON_CHECK}Trade-in</li>
        <li>${ICON_CHECK}Розтермінування</li>
      </ul>
      ${items.length ? `
      <label class="search js-only">
        ${ICON_SEARCH}
        <input type="search" id="q" placeholder="${esc(searchHint)}" autocomplete="off" enterkeyhint="search" aria-label="${scope ? `Пошук: ${esc(copy.label)}` : 'Пошук у всьому каталозі'}">
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
      <nav class="pager" id="pager" aria-label="Сторінки каталогу" hidden></nav>
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

  ${siteFooter()}
</body>
</html>`;
}

// ── Shared page chrome ────────────────────────────────────────

function documentHead({ title, description, canonical, ld = '', image = `${SITE}/og-image.jpg`, type = 'website', noindex = false }) {
  return `<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  ${noindex ? '<meta name="robots" content="noindex">' : `<link rel="canonical" href="${esc(canonical)}">`}
  <meta name="theme-color" content="#f6f4ef">
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <meta property="og:type" content="${type}">
  <meta property="og:locale" content="uk_UA">
  <meta property="og:site_name" content="IIOS">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:image" content="${esc(image)}">
  ${noindex ? '' : `<meta property="og:url" content="${esc(canonical)}">`}
  <meta name="twitter:card" content="summary_large_image">
  ${ld}
  <style>${STYLES}</style>
  <script src="/catalog.js" defer></script>
  <script src="/callback.js" defer></script>
</head>`;
}

function siteHeader(onCatalog) {
  return `<header class="top">
    <div class="wrap top-inner">
      <a class="logo" href="/" aria-label="IIOS — на головну">IIOS<span>.</span></a>
      <nav class="top-links" aria-label="Розділи">
        <a href="/">Головна</a>
        <a href="/catalog"${onCatalog ? ' aria-current="page"' : ''}>Каталог</a>
      </nav>
      <a class="top-cta" href="${BOT_URL}" target="_blank" rel="noopener">${ICON_TG}<span>Обрати в Telegram</span></a>
    </div>
  </header>`;
}

// Shortens to `max` characters at a word boundary.
function clip(text, max) {
  if (text.length <= max) return text;
  const cut = text.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return (space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:—-]+$/, '') + '…';
}

// ── Product page ──────────────────────────────────────────────

function productPage(item, related, all) {
  const { regular, sale, fmt } = prices(item);
  const kind = conditionKind(item);
  const name = feedTitle(item);
  const shown = sale || regular;
  const priceText = shown ? fmt(shown) : '';
  const image = safeImage(item.image);
  const bot = esc(botLink(item));
  const categoryKey = item.category || 'other';
  const category = categoryLabel(categoryKey, item);
  const d = deviceDetails(item);
  const warranty = item.warranty_days ? warrantyText(item.warranty_days) : '';

  // "б/у" is how people search for used phones; the page says "Вживаний".
  const title = `${name}${kind === 'used' ? ' б/у' : ''} — купити в Чернівцях${priceText ? ` за ${priceText}` : ''} | IIOS`;
  const condWord = kind === 'new' ? 'Новий' : kind === 'used' ? 'Вживаний' : '';
  // Grade and battery up front: they are what a used-phone search is about.
  const highlights = [
    d.grade ? `стан ${d.grade.label.toLowerCase()}` : '',
    d.battery !== null ? `АКБ ${d.battery}%` : '',
  ].filter(Boolean).join(', ');
  const description = clip(
    `${condWord ? `${condWord} ` : ''}${name}${priceText ? ` за ${priceText}` : ''}${highlights ? `: ${highlights}` : ''}. `
      + `${warranty ? `Гарантія ${warranty}` : 'Гарантія магазину'}, Trade-in, доставка Новою поштою. IIOS, Чернівці.`,
    DESCRIPTION_MAX,
  );

  // Memory and colour are already in the heading; only a longer condition
  // ("Новий запечатаний") earns the line under it.
  const condShort = condWord || item.condition || '';
  const specs = item.condition && item.condition !== condShort ? item.condition : '';

  let price = '<span class="price-ask">Ціну уточнюйте в боті</span>';
  if (sale) {
    price = `<span class="price">${esc(fmt(sale))}</span><span class="price-old">${esc(fmt(regular))}</span>`
      + `<span class="pdp-save">−${Math.round((1 - sale / regular) * 100)}%</span>`;
  } else if (regular) {
    price = `<span class="price">${esc(fmt(regular))}</span>`;
  }

  const condition = item.condition || condWord;
  const facts = [
    ['Стан', [condition, d.grade && d.grade.label.toLowerCase()].filter(Boolean).join(', ')],
    ['Акумулятор', batteryText(d)],
    ['Пам’ять', item.storage],
    ['Колір', item.color],
    ['SIM', d.sim],
    ['Комплект', kitText(d)],
    ['Ремонт', d.repairs.join('; ')],
    ['Гарантія', warranty ? `${warranty} від магазину` : ''],
    ['Категорія', [item.category_label || category, item.subcategory_label].filter(Boolean).join(' · ')],
  ].filter(([, value]) => value);

  // Three tiles under the heading: the facts that sell a used device.
  const tiles = [
    d.grade ? ['Стан', d.grade.label, ''] : null,
    // The tile keeps it short ("100%"); cycles stay in the facts below.
    batteryText(d) ? ['Акумулятор', d.battery !== null ? `${d.battery}%` : batteryText(d), batteryGood(d) ? ' is-good' : ''] : null,
    warranty ? ['Гарантія', warranty, ' is-warranty'] : null,
  ].filter(Boolean);

  // Parsed lines already show as facts; only what is left reads as a note.
  // A description with nothing recognisable keeps its old "Опис" block.
  const parsed = hasDetails(d);
  const notes = parsed ? d.notes.join('\n') : (item.description || '');
  const showLegend = Boolean(d.grade && d.grade.tier);

  const rate = uahPerUsd(all);
  const relatedCards = related.map((other, i) => card(other, 10 + i, rate)).join('');
  const categoryHref = categoryPath(categoryKey, all);

  return `${documentHead({
    title, description, canonical: productUrl(item), ld: productLd(item, all),
    image: image || undefined, type: 'product',
  })}
<body data-bot="${BOT_URL}">
  ${siteHeader(false)}

  <main class="wrap pdp">
    <p class="crumbs"><a href="/">Головна</a><span aria-hidden="true">/</span><a href="${PAGE_PATH}">Каталог</a><span aria-hidden="true">/</span><a href="${esc(categoryHref)}">${esc(category)}</a></p>
    <article class="pdp-main">
      <div class="pdp-media">
        ${image ? `<img src="${esc(image)}" alt="${esc(name)}" width="640" height="640" fetchpriority="high" decoding="async">` : ''}
        ${condShort ? `<span class="tag tag-cond tag-${kind || 'other'}">${esc(condShort)}</span>` : ''}
      </div>
      <div class="pdp-info">
        <h1>${esc(name)}</h1>
        ${specs ? `<p class="pdp-specs">${esc(specs)}</p>` : ''}
        ${tiles.length ? `<dl class="pdp-tiles">${tiles.map(([label, value, mod]) => `
          <div class="tile${mod}"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}
        </dl>` : ''}
        <div class="pdp-price">${price}</div>
        <p class="pdp-stock"><span class="dot" aria-hidden="true"></span>В наявності в Чернівцях</p>
        <div class="pdp-actions">
          <a class="btn" href="${bot}" target="_blank" rel="noopener">${ICON_TG}Замовити в Telegram</a>
          <a class="btn btn-outline" href="tel:+380953407754" data-callback="${esc(item.id)}" data-callback-name="${esc(item.name)}">${ICON_PHONE}Передзвоніть мені</a>
        </div>
        ${warranty ? `
        <aside class="pdp-warranty">
          <span class="pdp-warranty-icon">${ICON_SHIELD}</span>
          <div>
            <p class="pdp-warranty-title">${esc(warranty)} гарантії від IIOS</p>
            <p>Якщо протягом гарантії виявиться дефект — відремонтуємо або замінимо пристрій. Оглянути його можна до оплати: у магазині або у відділенні Нової пошти.</p>
            <a href="/#returns">Умови гарантії та повернення →</a>
          </div>
        </aside>` : ''}
        <ul class="perks">
          ${warranty ? '' : `<li>${ICON_CHECK}Гарантія магазину</li>`}
          <li>${ICON_CHECK}Доставка Новою поштою</li>
          <li>${ICON_CHECK}Trade-in</li>
          <li>${ICON_CHECK}Розтермінування</li>
        </ul>
        ${facts.length ? `
        <section class="pdp-specs-block">
          <h2>Характеристики</h2>
          <dl class="pdp-facts">${facts.map(([label, value]) => `
            <div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}
          </dl>
        </section>` : ''}
        ${notes ? `
        <section class="pdp-desc">
          <h2>${parsed ? 'Додатково' : 'Опис'}</h2>
          <p>${esc(notes)}</p>
        </section>` : ''}
        ${showLegend ? `
        <details class="pdp-legend">
          <summary>Що означає стан «${esc(d.grade.label)}»?${ICON_CHEVRON}</summary>
          <dl>${GRADE_NOTES.map(([label, text]) => `
            <div><dt>${esc(label)}</dt><dd>${esc(text)}</dd></div>`).join('')}
          </dl>
        </details>` : ''}
      </div>
    </article>
    ${relatedCards ? `
    <section class="pdp-related">
      <div class="pdp-related-head">
        <h2>Схожі товари</h2>
        <a class="more" href="${esc(categoryHref)}">Усі: ${esc(category)} →</a>
      </div>
      <div class="grid">${relatedCards}
      </div>
    </section>` : ''}
  </main>

  ${siteFooter()}
</body>
</html>`;
}

// A sold-out product (404) or a missing catalog.json (503).
function missingPage(temporary) {
  const heading = temporary ? 'Сторінка тимчасово недоступна' : 'Цей товар уже продано';
  const text = temporary
    ? 'Каталог саме оновлюється. Актуальна наявність і ціни — у нашому Telegram-боті.'
    : 'Можливо, його вже купили. Подивіться, що є в наявності зараз, або напишіть нам — підберемо схожий.';
  return `${documentHead({ title: `${heading} | IIOS`, description: text, noindex: true })}
<body data-bot="${BOT_URL}">
  ${siteHeader(false)}
  <main class="wrap">
    <div class="empty">
      <p class="empty-title">${heading}</p>
      <p class="empty-text">${text}</p>
      <a class="btn" href="${PAGE_PATH}">Перейти до каталогу</a>
    </div>
  </main>
  ${siteFooter()}
</body>
</html>`;
}

function siteFooter() {
  return `<!-- Same structure and contacts as the landing footer (keep in sync). -->
  <footer class="foot">
    <div class="wrap foot-top">
      <div>
        <div class="foot-logo">IIOS<span>.</span></div>
        <p class="foot-tagline">Нова та вживана техніка Apple, Android і ноутбуки у Чернівцях. Замовлення в Telegram, доставка по Україні.</p>
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
          <a href="/#returns">Повернення</a>
          <a href="https://t.me/IIOS_cv" target="_blank" rel="noopener">Telegram-канал</a>
          <a href="https://t.me/iios_cv_bot" target="_blank" rel="noopener">Telegram-бот</a>
          <a href="https://www.instagram.com/iios_cv" target="_blank" rel="noopener">Instagram</a>
        </nav>
      </div>
    </div>
  </footer>`;
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
.intro-text{max-width:720px;margin-top:12px;font-size:15.5px;line-height:1.6;color:var(--text)}
.lead{display:flex;align-items:flex-start;gap:9px;margin-top:12px;color:var(--muted);font-weight:600;font-size:15px}
.dot{width:8px;height:8px;margin-top:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 4px rgba(47,158,92,.15);flex-shrink:0}
.perks{list-style:none;display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.perks li{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;background:var(--bg2);border:1px solid var(--border);padding:6px 12px 6px 9px;border-radius:100px}
.perks svg{width:14px;height:14px;color:var(--ok-text)}
.perks .perk-warranty{background:var(--ink);border-color:var(--ink);color:#fff}
.perks .perk-warranty svg{color:#e3c48f}
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
/* Warranty rides on the photo, so it is seen before anything else in the card */
.tag-warranty{top:auto;bottom:10px;left:10px;display:flex;align-items:center;gap:5px;background:rgba(18,17,9,.82);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#fff;padding:4px 10px 4px 8px}
.tag-warranty svg{width:13px;height:13px;color:#e3c48f}
/* Grade and battery: what a used-device buyer checks first */
.badges{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.badge{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:700;line-height:1;padding:5px 8px 5px 6px;border-radius:8px;background:var(--bg3);color:var(--ink);white-space:nowrap}
.badge svg{width:13px;height:13px;color:var(--muted)}
.badge-top{background:#e6f3ea;color:var(--ok-text)}
.badge-top svg{color:var(--ok)}
.badge-bat.is-good{background:#e6f3ea;color:var(--ok-text)}
.badge-bat.is-good svg{color:var(--ok)}
/* Wraps the button under the price when a narrow card can't fit both */
.card-foot{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin-top:auto;padding-top:12px}
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

/* Pager, empty state, help band */
.pager{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:6px;margin-top:28px}
.pager[hidden]{display:none}
.page{min-width:42px;height:42px;padding:0 8px;display:inline-flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;font-variant-numeric:tabular-nums;background:var(--bg2);border:1px solid var(--border-strong);border-radius:12px;transition:border-color .2s,background .2s,color .2s}
.page:hover:not(:disabled):not(.is-current){border-color:var(--accent);background:var(--bg3)}
.page.is-current{background:var(--ink);border-color:var(--ink);color:#fff;cursor:default}
.page:disabled{opacity:.35;cursor:default}
.page-gap{min-width:20px;text-align:center;color:var(--muted);font-weight:700}
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
.btn-outline{background:var(--bg2);color:var(--ink);border:1px solid var(--border-strong)}
.btn-outline svg{color:var(--accent2)}
.btn-outline:hover{background:var(--bg3)}

/* Product page */
.pdp{padding-top:28px;padding-bottom:16px}
.pdp-main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:44px;align-items:start;margin-top:6px}
.pdp-media{position:sticky;top:calc(var(--top) + 20px);aspect-ratio:1/1;border-radius:28px;overflow:hidden;background:linear-gradient(160deg,#f1ede4,#e6e0d3);border:1px solid var(--border)}
.pdp-media::before{content:'IIOS';position:absolute;inset:0;display:grid;place-items:center;font-size:40px;font-weight:800;letter-spacing:.04em;color:rgba(23,22,15,.13)}
.pdp-media img{position:relative;width:100%;height:100%;object-fit:cover;display:block}
.pdp-media .tag{top:16px;font-size:13px;padding:5px 12px}
.pdp-media .tag-cond{left:16px}
.pdp-info{min-width:0}
.pdp-info h1{font-size:clamp(28px,4vw,42px);line-height:1.1}
.pdp-specs{margin-top:10px;font-size:15px;font-weight:600;color:var(--muted)}
.pdp-price{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 14px;margin-top:22px}
.pdp-price .price{font-size:38px;letter-spacing:-.03em}
.pdp-price .price-old{font-size:17px;margin:0}
.pdp-price .price-ask{font-size:18px}
.pdp-save{align-self:center;font-size:13px;font-weight:800;color:#fff;background:var(--danger);padding:3px 10px;border-radius:100px}
.pdp-stock{display:flex;align-items:center;gap:9px;margin-top:10px;font-size:14px;font-weight:600;color:var(--ok-text)}
.pdp-stock .dot{margin-top:0}
.pdp-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.pdp-actions .btn{height:52px;padding:0 24px 0 20px;font-size:16px}
.pdp .perks{margin-top:18px}
.pdp-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-top:18px}
.tile{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:10px 14px}
.tile dt{font-size:12px;font-weight:600;color:var(--muted)}
.tile dd{font-size:17px;font-weight:800;letter-spacing:-.01em;margin-top:2px}
.tile.is-good dd{color:var(--ok-text)}
.tile.is-warranty{background:var(--ink);border-color:var(--ink);color:#fff}
.tile.is-warranty dt{color:rgba(255,255,255,.65)}
.pdp-warranty{display:flex;gap:14px;align-items:flex-start;margin-top:22px;padding:18px 20px;border-radius:18px;background:linear-gradient(135deg,#fbf6ec,#f3ead8);border:1px solid rgba(163,129,79,.35)}
.pdp-warranty-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:var(--ink);flex-shrink:0}
.pdp-warranty-icon svg{width:22px;height:22px;color:#e3c48f}
.pdp-warranty-title{font-size:17px;font-weight:800;letter-spacing:-.01em;margin-bottom:4px}
.pdp-warranty p:not(.pdp-warranty-title){font-size:14px;line-height:1.55;color:var(--text)}
.pdp-warranty a{display:inline-block;margin-top:8px;font-size:14px;font-weight:700;color:var(--accent2)}
.pdp-warranty a:hover{color:var(--ink)}
.pdp-specs-block{margin-top:28px}
.pdp-specs-block h2{font-size:22px;letter-spacing:-.015em;margin-bottom:6px}
.pdp-legend{margin-top:20px;background:var(--bg2);border:1px solid var(--border);border-radius:16px}
.pdp-legend summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;font-size:15px;font-weight:700;cursor:pointer;list-style:none}
.pdp-legend summary::-webkit-details-marker{display:none}
.pdp-legend summary svg{width:18px;height:18px;color:var(--muted);transition:transform .2s}
.pdp-legend[open] summary svg{transform:rotate(180deg)}
.pdp-legend dl{padding:0 18px 14px}
.pdp-legend div{padding:8px 0;border-top:1px solid var(--border);font-size:14px}
.pdp-legend dt{font-weight:700}
.pdp-legend dd{color:var(--muted)}
.pdp-facts{margin-top:0;border-top:1px solid var(--border)}
.pdp-facts div{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--border);font-size:15px}
.pdp-facts dt{color:var(--muted)}
.pdp-facts dd{font-weight:600;text-align:right;overflow-wrap:anywhere}
.pdp-desc{margin-top:28px}
.pdp-desc h2,.pdp-related h2{font-size:22px;letter-spacing:-.015em}
.pdp-desc h2{margin-bottom:8px}
.pdp-desc p{white-space:pre-line;overflow-wrap:anywhere}
.pdp-related{margin-top:56px}
.pdp-related-head{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:14px}
.more{font-size:14px;font-weight:700;color:var(--accent2);white-space:nowrap}
.more:hover{color:var(--ink)}

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
  /* Phones keep only the warranty perk: the one that sells */
  .intro .perks li:not(.perk-warranty){display:none}
  .intro .perks{margin-top:12px}
  .search{height:46px;max-width:none;border-radius:14px;margin-top:16px}
  .toolbar-inner{--gutter:16px;padding-top:2px;padding-bottom:8px;gap:8px}
  .tabs{gap:22px}
  .tab{height:44px;font-size:14.5px}
  .controls{gap:10px}
  .sort-label{display:none}
  .summary-text{font-size:13px;padding-top:8px}
  .intro-text{font-size:14.5px;margin-top:10px}
  /* 16px keeps iOS from zooming the page when the select opens */
  .sort select{font-size:16px;font-weight:600}
  .group-title{font-size:19px;margin-bottom:10px}
  .pager{gap:3px;margin-top:22px}
  .page{min-width:34px;height:40px;padding:0 4px;font-size:14px;border-radius:10px}
  .page-gap{min-width:12px}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .card{border-radius:16px}
  .card:hover{transform:none}
  .tag{top:8px;font-size:11.5px;padding:3px 8px}
  .tag-cond{left:8px;max-width:calc(100% - 64px)}
  .tag-sale{right:8px}
  .tag-warranty{bottom:8px;left:8px;top:auto;padding:3px 8px 3px 6px}
  .tag-warranty svg{width:12px;height:12px}
  .badge{font-size:11.5px;padding:4px 6px 4px 5px}
  .badge svg{width:12px;height:12px}
  .pdp-tiles{grid-template-columns:repeat(auto-fit,minmax(90px,1fr))}
  .tile{padding:9px 11px}
  .tile dd{font-size:15px}
  .pdp-warranty{padding:16px}
  .card-body{padding:10px 11px 12px}
  .card-title{font-size:14.5px}
  .card-specs,.card-note{font-size:12.5px}
  .card-foot{flex-direction:column;align-items:stretch;gap:8px;padding-top:8px}
  .price{font-size:18px}
  .card-cta{height:40px;font-size:13.5px}
  .card-call{align-self:center;font-size:12.5px;margin-top:2px}
  .help{flex-direction:column;align-items:flex-start;padding:26px 22px;margin-top:36px;border-radius:24px}
  .help h2{font-size:20px}
  .pdp{padding-top:12px}
  .pdp-main{grid-template-columns:1fr;gap:20px}
  .pdp-media{position:relative;top:auto;border-radius:20px}
  .pdp .perks{display:flex}
  .pdp-price{margin-top:16px}
  .pdp-price .price{font-size:32px}
  .pdp-actions .btn{flex:1 1 100%;justify-content:center}
  .pdp-related{margin-top:40px}
  .pdp-desc h2,.pdp-related h2{font-size:19px}
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
