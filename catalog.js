// Search, category tabs, model chips, filters, sorting and "show more" for
// /catalog (page rendered by worker/index.js). The page works without this
// script; it only filters and reorders the cards that are already there.
(function () {
  const root = document.documentElement;
  root.classList.add('js');

  // Cards revealed per step, so a 500-product catalog isn't one endless scroll.
  const BATCH = 24;
  const COND_LABELS = { new: 'Нові', used: 'Вживані' };

  function plural(n, one, few, many) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function init() {
    const results = document.querySelector('.results');
    if (!results) return;
    const groups = [...document.querySelectorAll('.group')];
    let cards = [...document.querySelectorAll('.card')];
    const tabs = [...document.querySelectorAll('.tab')];
    const filters = [...document.querySelectorAll('.filter')];
    const input = document.getElementById('q');
    const sortSelect = document.getElementById('sort');
    const summary = document.getElementById('summary');
    const resetBtn = document.getElementById('reset');
    const moreBtn = document.getElementById('more');
    const modelsBox = document.getElementById('models');
    const empty = document.getElementById('empty');
    const emptyCta = document.getElementById('empty-cta');
    const toolbar = document.querySelector('.toolbar');
    const bot = document.body.dataset.bot;
    let labels = {};
    try { labels = JSON.parse(document.body.dataset.labels || '{}'); } catch { /* defaults */ }

    const state = { cat: 'all', sub: '', q: '', cond: new Set(), sale: false, sort: 'default', limit: BATCH };

    // Broken or missing photos fall back to the IIOS placeholder behind them.
    document.querySelectorAll('.card-media img').forEach(img => {
      const drop = () => img.remove();
      if (img.complete && img.naturalWidth === 0) drop();
      else img.addEventListener('error', drop, { once: true });
    });

    function matches(card) {
      const d = card.dataset;
      if (state.cat !== 'all' && d.cat !== state.cat) return false;
      if (state.sub && d.sub !== state.sub) return false;
      if (state.cond.size && !state.cond.has(d.cond)) return false;
      if (state.sale && d.sale !== '1') return false;
      if (state.q) {
        return state.q.split(/\s+/).every(word => d.q.includes(word));
      }
      return true;
    }

    function isFiltered() {
      return state.cat !== 'all' || Boolean(state.sub) || Boolean(state.q) || state.cond.size > 0 || state.sale;
    }

    function describe(total) {
      const parts = [`${total} ${plural(total, 'товар', 'товари', 'товарів')}`];
      if (state.cat !== 'all' && labels[state.cat]) parts.push(labels[state.cat]);
      if (state.sub) parts.push(state.sub);
      state.cond.forEach(c => parts.push(COND_LABELS[c] || c));
      if (state.sale) parts.push('зі знижкою');
      if (state.q) parts.push(`«${state.q}»`);
      return parts.join(' · ');
    }

    function apply() {
      let total = 0;
      let shown = 0;
      cards.forEach(card => {
        const ok = matches(card);
        const capped = ok && total >= state.limit;
        card.hidden = !ok;
        card.classList.toggle('is-capped', capped);
        if (ok) { total++; if (!capped) shown++; }
      });
      groups.forEach(group => {
        group.hidden = !group.querySelector('.card:not([hidden]):not(.is-capped)');
      });
      tabs.forEach(tab => {
        const active = tab.dataset.tab === state.cat;
        tab.classList.toggle('is-active', active);
        if (active) tab.setAttribute('aria-current', 'true'); else tab.removeAttribute('aria-current');
      });
      const filtered = isFiltered();
      results.classList.toggle('is-filtered', filtered);

      if (summary) summary.textContent = describe(total);
      if (resetBtn) resetBtn.hidden = !filtered;
      if (moreBtn) {
        const left = total - shown;
        moreBtn.hidden = left <= 0;
        moreBtn.textContent = `Показати ще ${Math.min(BATCH, left)} з ${left}`;
      }

      empty.hidden = total > 0;
      if (!total) {
        const known = state.cat !== 'all' && labels[state.cat];
        const onlyCategory = known && !state.sub && !state.q && !state.cond.size && !state.sale;
        empty.querySelector('.empty-title').textContent = onlyCategory
          ? `${labels[state.cat]}: зараз немає на сайті`
          : 'Нічого не знайдено';
        empty.querySelector('.empty-text').textContent = onlyCategory
          ? 'Асортимент оновлюється щодня — напишіть нам, і ми підберемо модель або привеземо під замовлення.'
          : 'Спробуйте інший запит або напишіть нам — підберемо під ваш бюджет.';
        emptyCta.href = known ? `${bot}?start=cat_${encodeURIComponent(state.cat)}` : bot;
      }
    }

    // Any change to what is listed starts again from the first batch.
    function refresh() {
      state.limit = BATCH;
      apply();
    }

    // Model chips ("iPhone Pro", "iPhone Pro Max"…) for the open category,
    // built from the cards themselves; shown only when there is a real choice.
    function renderModels() {
      if (!modelsBox) return;
      const counts = new Map();
      if (state.cat !== 'all') {
        cards.forEach(card => {
          const sub = card.dataset.sub;
          if (card.dataset.cat === state.cat && sub) counts.set(sub, (counts.get(sub) || 0) + 1);
        });
      }
      const show = counts.size > 1;
      modelsBox.replaceChildren();
      if (show) {
        counts.forEach((count, sub) => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'filter model';
          btn.setAttribute('aria-pressed', String(state.sub === sub));
          btn.append(sub + ' ');
          const n = document.createElement('span');
          n.textContent = count;
          btn.append(n);
          btn.addEventListener('click', () => {
            state.sub = state.sub === sub ? '' : sub;
            [...modelsBox.children].forEach(b => b.setAttribute('aria-pressed', String(b === btn && Boolean(state.sub))));
            refresh();
          });
          modelsBox.append(btn);
        });
      } else {
        state.sub = '';
      }
      modelsBox.hidden = !show;
    }

    function setCategory(cat, { scroll } = {}) {
      state.cat = cat === 'all' || labels[cat] ? cat : 'all';
      state.sub = '';
      renderModels();
      refresh();
      const hash = state.cat === 'all' ? location.pathname : '#' + state.cat;
      history.replaceState(null, '', hash);
      if (scroll && toolbar) {
        const top = toolbar.getBoundingClientRect().top + scrollY - parseInt(getComputedStyle(toolbar).top, 10);
        if (scrollY > top) scrollTo({ top, behavior: 'smooth' });
      }
      const active = tabs.find(t => t.dataset.tab === state.cat);
      active?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
    }

    tabs.forEach(tab => tab.addEventListener('click', e => {
      e.preventDefault();
      setCategory(tab.dataset.tab, { scroll: true });
    }));

    filters.forEach(btn => btn.addEventListener('click', () => {
      const key = btn.dataset.filter;
      const on = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', String(on));
      if (key === 'sale') state.sale = on;
      else if (on) state.cond.add(key);
      else state.cond.delete(key);
      refresh();
    }));

    // Search always covers the whole catalog: typing a query leaves the
    // open category, so "iphone 15" typed on the iPad tab still finds it.
    function setQuery(value) {
      state.q = value.trim().toLowerCase();
      if (state.q && state.cat !== 'all') setCategory('all');
      else refresh();
    }
    input?.addEventListener('input', () => setQuery(input.value));
    input?.addEventListener('keydown', e => {
      if (e.key === 'Escape') { input.value = ''; setQuery(''); }
    });

    // Sorting reorders cards inside each category; products without a price go last.
    function sortCards() {
      const price = card => (card.dataset.price === '' ? null : Number(card.dataset.price));
      const original = (a, b) => a.dataset.i - b.dataset.i;
      groups.forEach(group => {
        const grid = group.querySelector('.grid');
        if (!grid) return;
        const list = [...grid.children];
        list.sort((a, b) => {
          if (state.sort === 'default') return original(a, b);
          const pa = price(a), pb = price(b);
          if (pa === null || pb === null) return (pa === null) - (pb === null) || original(a, b);
          return (state.sort === 'asc' ? pa - pb : pb - pa) || original(a, b);
        });
        grid.append(...list);
      });
      cards = [...document.querySelectorAll('.card')];
    }
    sortSelect?.addEventListener('change', () => {
      state.sort = sortSelect.value;
      sortCards();
      refresh();
    });

    moreBtn?.addEventListener('click', () => {
      state.limit += BATCH;
      apply();
    });

    resetBtn?.addEventListener('click', () => {
      state.q = '';
      state.sale = false;
      state.cond.clear();
      if (input) input.value = '';
      filters.forEach(btn => btn.setAttribute('aria-pressed', 'false'));
      setCategory('all');
    });

    // Shadow under the toolbar once it sticks.
    if (toolbar && 'IntersectionObserver' in window) {
      const sentinel = document.createElement('div');
      toolbar.before(sentinel);
      new IntersectionObserver(([entry]) => {
        toolbar.classList.toggle('is-stuck', !entry.isIntersecting);
      }, { rootMargin: `-${parseInt(getComputedStyle(toolbar).top, 10) + 1}px 0px 0px 0px` }).observe(sentinel);
    }

    // /catalog#watch (e.g. from the landing's category cards) opens that tab;
    // /catalog#p-<id> keeps every card visible so the browser can scroll to it.
    function fromHash() {
      const key = decodeURIComponent(location.hash.slice(1));
      if (key && !key.startsWith('p-')) { setCategory(key, { scroll: false }); return; }
      renderModels();
      state.limit = key ? Infinity : BATCH;
      apply();
    }
    window.addEventListener('hashchange', fromHash);
    fromHash();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
