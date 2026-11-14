// "Передзвоніть мені": a floating phone button (landing and /catalog) that
// opens a short form; the number goes to POST /api/callback (worker/
// callback-api.js), which sends it to the admins in Telegram.
//
// Any element with data-callback="<product id>" (and data-callback-name)
// opens the same form for that product, e.g. the "Передзвоніть мені" link on
// /catalog cards. Styles are injected here because /catalog's CSP only allows
// inline styles. Without <dialog> support the button is a plain tel: link.
(function () {
  if (window.IIOSCallback) return;

  const PHONE_TEL = '+380953407754';
  const PHONE_SHOWN = '+380 95 340 77 54';
  const OPEN_HOUR = 10;
  const CLOSE_HOUR = 20;
  const REQUEST_TIMEOUT_MS = 12000;

  const ICON_PHONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.14 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.05 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 17z"/></svg>';
  const ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  const ICON_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

  const CSS = `
.cb-fab{position:fixed;right:20px;bottom:calc(20px + env(safe-area-inset-bottom));z-index:140;display:flex;align-items:center;justify-content:center;gap:9px;height:56px;min-width:56px;padding:0 22px 0 18px;border:0;border-radius:100px;background:var(--ink,#121109);color:#fff;font:inherit;font-size:15px;font-weight:700;line-height:1;text-decoration:none;cursor:pointer;box-shadow:0 12px 30px rgba(18,17,9,.28);-webkit-tap-highlight-color:transparent;transition:background .2s,transform .2s,opacity .25s,bottom .3s ease,visibility 0s}
.cb-fab svg{width:21px;height:21px;color:var(--accent,#a3814f);flex-shrink:0}
.cb-fab:hover{background:#2a2820;transform:translateY(-2px)}
.cb-fab:active{transform:scale(.96)}
.cb-fab:focus-visible{outline:3px solid var(--accent,#a3814f);outline-offset:3px}
.cb-fab.cb-hide{opacity:0;visibility:hidden;pointer-events:none;transition:opacity .2s,visibility 0s .2s}
.cb-fab.cb-ping::after{content:'';position:absolute;inset:0;border-radius:inherit;box-shadow:0 0 0 0 rgba(163,129,79,.55);animation:cb-ping 1.6s ease-out 2}
@keyframes cb-ping{to{box-shadow:0 0 0 16px rgba(163,129,79,0)}}
@media (max-width:720px){
  .cb-fab{right:16px;bottom:calc(16px + env(safe-area-inset-bottom));width:56px;padding:0}
  .cb-fab-label{display:none}
  .cb-fab svg{width:23px;height:23px}
  .cb-fab.cb-lift{bottom:calc(82px + env(safe-area-inset-bottom))}
}
.cb{width:min(420px,calc(100vw - 32px));max-height:calc(100dvh - 32px);margin:auto;padding:0;border:0;border-radius:24px;background:var(--bg2,#fff);color:var(--text,#17160f);box-shadow:0 30px 80px rgba(18,17,9,.3);overflow:auto;overscroll-behavior:contain}
.cb::backdrop{background:rgba(18,17,9,.5);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}
.cb[open]{animation:cb-in .22s ease-out}
@keyframes cb-in{from{opacity:0;transform:translateY(12px) scale(.98)}}
.cb-card{position:relative;padding:26px 24px 22px}
.cb-close{position:absolute;top:12px;right:12px;display:grid;place-items:center;width:40px;height:40px;border:0;border-radius:50%;background:var(--bg3,#eeeae0);color:var(--muted,#6a6658);cursor:pointer;transition:background .2s,color .2s}
.cb-close:hover{color:var(--ink,#121109)}
.cb-close svg{width:18px;height:18px}
.cb-badge{display:grid;place-items:center;width:48px;height:48px;border-radius:16px;background:var(--ink,#121109);color:var(--accent,#a3814f);margin-bottom:14px}
.cb-badge svg{width:23px;height:23px}
.cb-done .cb-badge{background:var(--ok,#2f9e5c);color:#fff;border-radius:50%}
.cb h2:focus{outline:0}
.cb h2{font-size:23px;line-height:1.2;letter-spacing:-.02em;font-weight:800;margin:0 44px 6px 0}
.cb-sub{font-size:14.5px;line-height:1.5;color:var(--muted,#6a6658);margin:0 0 16px}
.cb-product{font-size:14px;line-height:1.4;background:var(--bg,#f6f4ef);border:1px solid var(--border,rgba(20,19,15,.09));border-radius:12px;padding:10px 12px;margin:0 0 14px}
.cb-product b{font-weight:700}
.cb-field{display:block;margin:0 0 12px}
.cb-field span{display:block;font-size:13px;font-weight:700;margin-bottom:6px}
.cb-field i{font-style:normal;font-weight:500;color:var(--muted,#6a6658)}
.cb-field input{display:block;width:100%;height:50px;padding:0 14px;border:1px solid var(--border-strong,rgba(20,19,15,.16));border-radius:14px;background:var(--bg2,#fff);color:inherit;font:inherit;font-size:16px;outline:0;transition:border-color .2s,box-shadow .2s}
.cb-field input::placeholder{color:var(--muted,#6a6658);opacity:.7}
.cb-field input:focus{border-color:var(--accent2,#7a5c34);box-shadow:0 0 0 4px rgba(163,129,79,.16)}
.cb-field input[aria-invalid=true]{border-color:var(--danger,#c2412c);box-shadow:0 0 0 4px rgba(194,65,44,.12)}
.cb-hp{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}
.cb-alert{font-size:13.5px;line-height:1.45;font-weight:600;color:var(--danger,#c2412c);margin:2px 0 12px}
.cb-alert a{text-decoration:underline;text-underline-offset:2px;white-space:nowrap}
.cb-submit{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:52px;margin-top:4px;border:0;border-radius:100px;background:var(--ink,#121109);color:#fff;font:inherit;font-size:16px;font-weight:700;cursor:pointer;transition:background .2s,opacity .2s}
.cb-submit:hover{background:var(--accent2,#7a5c34)}
.cb-submit:disabled{opacity:.6;cursor:progress}
.cb-submit svg{width:18px;height:18px}
.cb-fine{font-size:12.5px;line-height:1.5;color:var(--muted,#6a6658);text-align:center;margin:12px 0 0}
.cb-fine a{color:var(--text,#17160f);font-weight:700;white-space:nowrap}
.cb [hidden]{display:none!important}
@media (prefers-reduced-motion:reduce){
  .cb-fab,.cb-fab::after,.cb[open]{transition:none!important;animation:none!important}
}`;

  function kyivHour() {
    try {
      return Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Kyiv', hour: 'numeric', hourCycle: 'h23' }).format(new Date()));
    } catch (e) {
      return new Date().getHours();
    }
  }
  function isOpenNow() {
    const hour = kyivHour();
    return hour >= OPEN_HOUR && hour < CLOSE_HOUR;
  }

  // Same rules as normalizePhone() in worker/callback-api.js (keep in sync).
  function normalizePhone(value) {
    const raw = String(value || '').trim();
    if (!raw || raw.length > 40 || /[^\d\s()+.-]/.test(raw)) return null;
    const plus = raw.startsWith('+');
    const digits = raw.replace(/\D/g, '');
    let national = null;
    if (digits.length === 12 && digits.startsWith('380')) national = digits.slice(3);
    else if (digits.length === 11 && digits.startsWith('80') && !plus) national = digits.slice(2);
    else if (digits.length === 10 && digits.startsWith('0') && !plus) national = digits.slice(1);
    else if (digits.length === 9 && !plus) national = digits;
    if (national) {
      if (national.startsWith('0') || /^(\d)\1+$/.test(national)) return null;
      return '+380' + national;
    }
    if (plus && digits.length >= 10 && digits.length <= 15 && !digits.startsWith('0') && !digits.startsWith('380') && !/^(\d)\1+$/.test(digits)) {
      return '+' + digits;
    }
    return null;
  }
  function prettyPhone(phone) {
    const m = /^\+380(\d{2})(\d{3})(\d{2})(\d{2})$/.exec(phone);
    return m ? '+380 ' + m[1] + ' ' + m[2] + ' ' + m[3] + ' ' + m[4] : phone;
  }

  function el(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function init() {
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    const supported = typeof HTMLDialogElement === 'function' && 'showModal' in HTMLDialogElement.prototype;
    const fab = supported
      ? el(`<button type="button" class="cb-fab" aria-haspopup="dialog" aria-label="Передзвоніть мені">${ICON_PHONE}<span class="cb-fab-label">Передзвоніть мені</span></button>`)
      : el(`<a class="cb-fab" href="tel:${PHONE_TEL}" aria-label="Зателефонувати ${PHONE_SHOWN}">${ICON_PHONE}<span class="cb-fab-label">Зателефонувати</span></a>`);
    document.body.appendChild(fab);
    avoidOverlaps(fab);

    // One gentle nudge after a while on the page; never with reduced motion.
    if (!window.matchMedia || !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setTimeout(() => {
        fab.classList.add('cb-ping');
        setTimeout(() => fab.classList.remove('cb-ping'), 3500);
      }, 9000);
    }

    if (!supported) {
      document.addEventListener('click', (e) => {
        if (!e.target.closest('[data-callback]')) return;
        e.preventDefault();
        window.location.href = 'tel:' + PHONE_TEL;
      });
      return;
    }

    const dialog = buildDialog();
    document.body.appendChild(dialog);
    const api = wire(dialog);
    window.IIOSCallback = { open: api.open };

    fab.addEventListener('click', () => api.open({ source: 'fab' }));
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('[data-callback]');
      if (!trigger) return;
      e.preventDefault();
      api.open({
        source: 'card',
        productId: trigger.dataset.callback || '',
        productName: trigger.dataset.callbackName || '',
      });
    });
  }

  // Landing page: rise above the mobile sticky CTA bar, step aside while the
  // cookie banner is open (both toggle a "visible" class).
  function avoidOverlaps(fab) {
    const follow = (id, cls) => {
      const node = document.getElementById(id);
      if (!node) return;
      const sync = () => fab.classList.toggle(cls, node.classList.contains('visible'));
      new MutationObserver(sync).observe(node, { attributes: true, attributeFilter: ['class'] });
      sync();
    };
    follow('sticky-cta', 'cb-lift');
    follow('cookie-banner', 'cb-hide');
  }

  function buildDialog() {
    return el(`
<dialog class="cb" aria-labelledby="cb-title">
  <form class="cb-card" novalidate>
    <button type="button" class="cb-close" aria-label="Закрити">${ICON_CLOSE}</button>
    <div class="cb-step-form">
      <div class="cb-badge">${ICON_PHONE}</div>
      <h2 id="cb-title">Передзвонимо вам</h2>
      <p class="cb-sub" id="cb-sub"></p>
      <p class="cb-product" hidden>Цікавить: <b></b></p>
      <label class="cb-field">
        <span>Телефон</span>
        <input name="phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="22" placeholder="+380 67 123 45 67" required aria-describedby="cb-alert">
      </label>
      <label class="cb-field">
        <span>Ім'я <i>· необов'язково</i></span>
        <input name="name" type="text" autocomplete="given-name" maxlength="50" autocapitalize="words" aria-describedby="cb-alert">
      </label>
      <label class="cb-field cb-note">
        <span>Що цікавить? <i>· необов'язково</i></span>
        <input name="note" type="text" maxlength="120" placeholder="Напр., iPhone 15 Pro до 35 000 ₴" aria-describedby="cb-alert">
      </label>
      <div class="cb-hp" aria-hidden="true">
        <label>Компанія <input name="company" type="text" tabindex="-1" autocomplete="off"></label>
      </div>
      <p class="cb-alert" id="cb-alert" role="alert" hidden></p>
      <button type="submit" class="cb-submit">${ICON_PHONE}<span>Чекаю дзвінка</span></button>
      <p class="cb-fine">Номер потрібен лише для дзвінка щодо вашого запиту. Або зателефонуйте самі: <a href="tel:${PHONE_TEL}">${PHONE_SHOWN}</a></p>
    </div>
    <div class="cb-step-done" hidden>
      <div class="cb-done"><div class="cb-badge">${ICON_CHECK}</div></div>
      <h2 tabindex="-1" class="cb-done-title">Дякуємо!</h2>
      <p class="cb-sub cb-done-text"></p>
      <button type="button" class="cb-submit cb-finish">Добре</button>
    </div>
  </form>
</dialog>`);
  }

  function wire(dialog) {
    const form = dialog.querySelector('form');
    const stepForm = dialog.querySelector('.cb-step-form');
    const stepDone = dialog.querySelector('.cb-step-done');
    const sub = dialog.querySelector('#cb-sub');
    const productBox = dialog.querySelector('.cb-product');
    const noteField = dialog.querySelector('.cb-note');
    const alertBox = dialog.querySelector('#cb-alert');
    const submit = dialog.querySelector('.cb-submit');
    const submitLabel = submit.querySelector('span');
    const inputs = {
      phone: form.elements.phone,
      name: form.elements.name,
      note: form.elements.note,
      company: form.elements.company,
    };
    let context = {};
    let openedAt = 0;
    let busy = false;

    function setError(message, field) {
      Object.values(inputs).forEach(input => input.removeAttribute('aria-invalid'));
      if (!message) {
        alertBox.hidden = true;
        alertBox.textContent = '';
        return;
      }
      alertBox.hidden = false;
      alertBox.textContent = message + ' ';
      const call = document.createElement('a');
      call.href = 'tel:' + PHONE_TEL;
      call.textContent = PHONE_SHOWN;
      if (!field) alertBox.append('Телефон: ', call);
      const input = field && inputs[field];
      if (input) {
        input.setAttribute('aria-invalid', 'true');
        input.focus();
      }
    }

    function showForm() {
      stepForm.hidden = false;
      stepDone.hidden = true;
      sub.textContent = isOpenNow()
        ? 'Залиште номер — менеджер зателефонує найближчим часом і відповість на всі питання.'
        : `Ми працюємо щодня з ${OPEN_HOUR}:00 до ${CLOSE_HOUR}:00 — залиште номер, і менеджер зателефонує, щойно відкриємося.`;
      const product = context.productName;
      productBox.hidden = !product;
      noteField.hidden = Boolean(product);
      if (product) productBox.querySelector('b').textContent = product;
      setError('');
    }

    function open(options) {
      context = options || {};
      if (!dialog.open) {
        showForm();
        dialog.showModal();
      }
      openedAt = Date.now();
      if (!inputs.phone.value) inputs.phone.value = '+380 ';
      const end = inputs.phone.value.length;
      inputs.phone.focus();
      try { inputs.phone.setSelectionRange(end, end); } catch (e) { /* type=tel without selection API */ }
    }

    function close() {
      dialog.close();
    }

    function done(phone) {
      const name = inputs.name.value.trim();
      dialog.querySelector('.cb-done-title').textContent = name ? `Дякуємо, ${name}!` : 'Дякуємо!';
      const when = isOpenNow() ? 'найближчим часом' : `завтра після ${OPEN_HOUR}:00`;
      dialog.querySelector('.cb-done-text').textContent =
        `Ми отримали ваш запит і зателефонуємо на ${prettyPhone(phone)} ${when}.`;
      stepForm.hidden = true;
      stepDone.hidden = false;
      dialog.querySelector('.cb-done-title').focus();
      form.reset();
    }

    function track() {
      try {
        if (typeof window.gtag === 'function') {
          window.gtag('event', 'generate_lead', { method: 'callback', cta_position: context.source || 'fab', transport_type: 'beacon' });
        }
        if (typeof window.fbq === 'function') {
          window.fbq('track', 'Lead', { content_name: 'callback', content_category: context.source || 'fab' });
        }
      } catch (e) { /* analytics must never break the form */ }
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      const phone = normalizePhone(inputs.phone.value);
      if (!phone) {
        setError('Перевірте номер: наприклад, +380 67 123 45 67.', 'phone');
        return;
      }
      setError('');
      busy = true;
      submit.disabled = true;
      submitLabel.textContent = 'Надсилаємо…';

      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      const timer = controller && setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      try {
        const response = await fetch('/api/callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          signal: controller ? controller.signal : undefined,
          body: JSON.stringify({
            phone: inputs.phone.value,
            name: inputs.name.value,
            note: context.productName ? '' : inputs.note.value,
            productId: context.productId || '',
            company: inputs.company.value,
            elapsed: Date.now() - openedAt,
          }),
        });
        let data = {};
        try { data = await response.json(); } catch (err) { /* non-JSON error page */ }
        if (response.ok && data.ok) {
          if (!data.duplicate) track();
          done(phone);
        } else {
          setError(data.message || 'Не вдалося надіслати запит.', data.field);
        }
      } catch (err) {
        setError("Немає зв'язку з сервером. Перевірте інтернет або зателефонуйте нам.");
      } finally {
        if (timer) clearTimeout(timer);
        busy = false;
        submit.disabled = false;
        submitLabel.textContent = 'Чекаю дзвінка';
      }
    });

    Object.values(inputs).forEach(input => input.addEventListener('input', () => {
      if (input.getAttribute('aria-invalid')) setError('');
    }));
    dialog.querySelector('.cb-close').addEventListener('click', close);
    dialog.querySelector('.cb-finish').addEventListener('click', close);
    // A tap on the dimmed backdrop closes the dialog (the click lands on <dialog> itself).
    dialog.addEventListener('click', (e) => { if (e.target === dialog) close(); });

    return { open };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
