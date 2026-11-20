// Search, category tabs, model chips, filters, sorting and pagination for
// /catalog and the category pages /catalog/<slug> (rendered by
// worker/index.js). The page works without this script; it only filters and
// reorders the cards that are already there.
//
// A category page (body[data-scope]) holds one category only: its tabs are
// plain links to the other pages, and search stays inside the category.
(function () {
  const root = document.documentElement;
  root.classList.add('js');

  // Cards per page, so a 500-product catalog isn't one endless scroll.
  const PAGE_SIZE = 24;
  const COND_LABELS = { new: 'Нові', used: 'Вживані' };
  // Condition toggles read from the card (data-grade, data-bat), which the
  // worker parses out of each product's description.
  const FLAGS = {
    top: { label: 'ідеальний стан', test: d => d.grade === 'top' },
    bat: { label: 'АКБ 90%+', test: d => d.bat === '1' },
  };

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
    // Only /catalog's tabs filter in place; a category page's tabs navigate.
    const tabs = [...document.querySelectorAll('.tab[data-tab]')];
    const filters = [...document.querySelectorAll('.filter')];
    const input = document.getElementById('q');
    const sortSelect = document.getElementById('sort');
    const summary = document.getElementById('summary');
    const resetBtn = document.getElementById('reset');
    const pager = document.getElementById('pager');
    const modelsBox = document.getElementById('models');
    const empty = document.getElementById('empty');
    const emptyCta = document.getElementById('empty-cta');
    const toolbar = document.querySelector('.toolbar');
    const bot = document.body.dataset.bot;
    const scope = document.body.dataset.scope || '';
    const home = scope || 'all';
    let labels = {};
    try { labels = JSON.parse(document.body.dataset.labels || '{}'); } catch { /* defaults */ }

    const state = { cat: home, sub: '', q: '', cond: new Set(), flags: new Set(), sale: false, sort: 'default', page: 1 };

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
      for (const flag of state.flags) if (!FLAGS[flag].test(d)) return false;
      if (state.q) {
        return state.q.split(/\s+/).every(word => d.q.includes(word));
      }
      return true;
    }

    function isFiltered() {
      return state.cat !== home || Boolean(state.sub) || Boolean(state.q) || state.cond.size > 0 || state.flags.size > 0 || state.sale;
    }

    function describe(total) {
      const parts = [`${total} ${plural(total, 'товар', 'товари', 'товарів')}`];
      if (state.cat !== home && labels[state.cat]) parts.push(labels[state.cat]);
      if (state.sub) parts.push(state.sub);
      state.cond.forEach(c => parts.push(COND_LABELS[c] || c));
      if (state.sale) parts.push('зі знижкою');
      state.flags.forEach(f => parts.push(FLAGS[f].label));
      if (state.q) parts.push(`«${state.q}»`);
      return parts.join(' · ');
    }

    // Page numbers to offer: all of them when few, otherwise the first, the
    // last and the neighbours of the current one (null marks a gap).
    function pageList(current, pages) {
      if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
      const from = Math.max(2, Math.min(current - 1, pages - 3));
      const to = Math.min(pages - 1, Math.max(current + 1, 4));
      const list = [1];
      if (from > 2) list.push(null);
      for (let p = from; p <= to; p++) list.push(p);
      if (to < pages - 1) list.push(null);
      list.push(pages);
      return list;
    }

    function pageButton(text, page, label) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'page';
      btn.textContent = text;
      btn.dataset.page = page;
      btn.setAttribute('aria-label', label);
      return btn;
    }

    function renderPager(pages) {
      if (!pager) return;
      pager.hidden = pages <= 1;
      pager.replaceChildren();
      if (pages <= 1) return;
      const prev = pageButton('‹', state.page - 1, 'Попередня сторінка');
      prev.disabled = state.page === 1;
      pager.append(prev);
      pageList(state.page, pages).forEach(p => {
        if (p === null) {
          const gap = document.createElement('span');
          gap.className = 'page-gap';
          gap.textContent = '…';
          gap.setAttribute('aria-hidden', 'true');
          pager.append(gap);
          return;
        }
        const btn = pageButton(String(p), p, `Сторінка ${p}`);
        if (p === state.page) {
          btn.classList.add('is-current');
          btn.setAttribute('aria-current', 'page');
        }
        pager.append(btn);
      });
      const next = pageButton('›', state.page + 1, 'Наступна сторінка');
      next.disabled = state.page === pages;
      pager.append(next);
    }

    function apply() {
      const matched = cards.filter(matches);
      const total = matched.length;
      const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      state.page = Math.min(Math.max(1, state.page), pages);
      const start = (state.page - 1) * PAGE_SIZE;
      const onPage = new Set(matched.slice(start, start + PAGE_SIZE));
      const isMatch = new Set(matched);
      cards.forEach(card => {
        const ok = isMatch.has(card);
        card.hidden = !ok;
        card.classList.toggle('is-capped', ok && !onPage.has(card));
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
      renderPager(pages);

      empty.hidden = total > 0;
      if (!total) {
        const known = state.cat !== 'all' && labels[state.cat];
        const onlyCategory = known && !state.sub && !state.q && !state.cond.size && !state.flags.size && !state.sale;
        empty.querySelector('.empty-title').textContent = onlyCategory
          ? `${labels[state.cat]}: зараз немає на сайті`
          : 'Нічого не знайдено';
        empty.querySelector('.empty-text').textContent = onlyCategory
          ? 'Асортимент оновлюється щодня — напишіть нам, і ми підберемо модель або привеземо під замовлення.'
          : 'Спробуйте інший запит або напишіть нам — підберемо під ваш бюджет.';
        emptyCta.href = known ? `${bot}?start=cat_${encodeURIComponent(state.cat)}` : bot;
      }
    }

    // Any change to what is listed starts again from the first page.
    function refresh() {
      state.page = 1;
      apply();
    }

    // Top of the results, just below the pinned toolbar.
    function scrollToResults() {
      const pinned = toolbar ? toolbar.offsetHeight + parseInt(getComputedStyle(toolbar).top, 10) : 0;
      const top = results.getBoundingClientRect().top + scrollY - pinned;
      const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
      scrollTo({ top: Math.max(0, top), behavior: reduce ? 'auto' : 'smooth' });
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
      state.cat = scope || (cat === 'all' || labels[cat] ? cat : 'all');
      state.sub = '';
      renderModels();
      refresh();
      if (!scope) {
        const hash = state.cat === 'all' ? location.pathname : '#' + state.cat;
        history.replaceState(null, '', hash);
      }
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
      else if (FLAGS[key]) state.flags[on ? 'add' : 'delete'](key);
      else if (on) state.cond.add(key);
      else state.cond.delete(key);
      refresh();
    }));

    // Search always covers the whole catalog: typing a query leaves the
    // open category, so "iphone 15" typed on the iPad tab still finds it.
    function setQuery(value) {
      state.q = value.trim().toLowerCase();
      if (state.q && state.cat !== home) setCategory('all');
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

    pager?.addEventListener('click', e => {
      const btn = e.target.closest('.page');
      if (!btn || btn.disabled || btn.classList.contains('is-current')) return;
      state.page = Number(btn.dataset.page);
      apply();
      scrollToResults();
    });

    resetBtn?.addEventListener('click', () => {
      state.q = '';
      state.sale = false;
      state.cond.clear();
      state.flags.clear();
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
    // /catalog#p-<id> opens the page that holds that card and scrolls to it.
    function fromHash() {
      const key = decodeURIComponent(location.hash.slice(1));
      if (key && !key.startsWith('p-')) { setCategory(key, { scroll: false }); return; }
      renderModels();
      const target = key ? document.getElementById(key) : null;
      const index = target ? cards.filter(matches).indexOf(target) : -1;
      state.page = index >= 0 ? Math.floor(index / PAGE_SIZE) + 1 : 1;
      apply();
      if (index >= 0) target.scrollIntoView({ block: 'center' });
    }
    window.addEventListener('hashchange', fromHash);
    fromHash();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
