/*
 * GE360 Tracker 0.2 — analitica first-party per GE360.
 *
 * Nessun dato personale: niente IP, nomi, telefoni, email o testo dei moduli.
 * La sessione vive in sessionStorage (si chiude con la scheda). L'ID visitatore
 * persistente è disattivato di default e si accende solo dalle impostazioni
 * del plugin (valuta prima il banner consenso).
 */
(() => {
  const cfg = window.GE360TrackerConfig;
  if (!cfg?.endpoint) return;
  if (navigator.webdriver) return; // browser automatizzati / bot dichiarati

  const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
  const ACTIVE_WINDOW_MS = 30 * 1000;
  const params = new URLSearchParams(window.location.search);

  // ---------- utilità ----------
  const storage = (name) => {
    try {
      const s = window[name];
      s.setItem('__ge360', '1');
      s.removeItem('__ge360');
      return s;
    } catch {
      return null;
    }
  };
  const ss = storage('sessionStorage');
  const ls = cfg.persistentVisitor ? storage('localStorage') : null;

  const uid = () => {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  };

  const cut = (value, max = 120) => String(value || '').slice(0, max);

  const selectorOf = (el) => {
    if (typeof el === 'string') return cut(el);
    if (!el || !el.tagName) return '';
    let out = el.tagName.toLowerCase();
    if (el.id) out += `#${el.id}`;
    else if (typeof el.className === 'string' && el.className.trim()) {
      out += `.${el.className.trim().split(/\s+/)[0]}`;
    }
    return cut(out);
  };

  // ---------- attribuzione ----------
  const SEARCH = ['google.', 'bing.', 'duckduckgo.', 'yahoo.', 'ecosia.', 'yandex.'];
  const SOCIAL = ['facebook.', 'fb.com', 'instagram.', 'linkedin.', 'tiktok.', 't.co', 'x.com', 'youtube.'];

  const referrerHost = () => {
    if (!document.referrer) return '';
    try {
      return new URL(document.referrer).hostname.toLowerCase().replace(/^www\./, '');
    } catch {
      return '';
    }
  };

  const ownHost = window.location.hostname.toLowerCase().replace(/^www\./, '');

  const referrerSource = (host) => {
    if (!host) return 'direct';
    if (host === ownHost) return 'internal';
    if (host.includes('google.')) return 'google';
    if (host.includes('facebook.') || host.includes('fb.com')) return 'facebook';
    if (host.includes('instagram.')) return 'instagram';
    return host;
  };

  const clickIdType = () => {
    const ids = [
      ['gclid', 'google_ads'],
      ['gbraid', 'google_ads'],
      ['wbraid', 'google_ads'],
      ['fbclid', 'meta'],
      ['msclkid', 'microsoft_ads'],
    ];
    for (const [param, type] of ids) {
      if (params.get(param)) return type;
    }
    return '';
  };

  const newAttribution = () => {
    const host = referrerHost();
    const clickId = clickIdType();
    const utmSource = (params.get('utm_source') || '').toLowerCase();
    const fromClick = { google_ads: 'google', meta: 'facebook', microsoft_ads: 'bing' };
    const source = utmSource || fromClick[clickId] || referrerSource(host);

    let medium = (params.get('utm_medium') || '').toLowerCase();
    if (!medium) {
      if (clickId === 'google_ads' || clickId === 'microsoft_ads') medium = 'cpc';
      else if (clickId === 'meta') medium = 'social';
      else if (source === 'direct') medium = 'none';
      else if (SEARCH.some((s) => host.includes(s))) medium = 'organic';
      else if (SOCIAL.some((s) => host.includes(s))) medium = 'social';
      else medium = 'referral';
    }

    return {
      source,
      medium,
      campaign: cut(params.get('utm_campaign')),
      term: cut(params.get('utm_term')),
      content: cut(params.get('utm_content')),
      click_id: clickId,
      landing: window.location.pathname,
      referrer_host: host,
    };
  };

  // ---------- sessione ----------
  const now = Date.now();
  let session = null;
  try {
    session = JSON.parse(ss?.getItem('ge360_session') || 'null');
  } catch {
    session = null;
  }

  const incoming = newAttribution();
  const externalArrival =
    Boolean(params.get('utm_source') || incoming.click_id) ||
    !['direct', 'internal'].includes(incoming.source);

  if (
    !session ||
    now - session.last > SESSION_TIMEOUT_MS ||
    (externalArrival && incoming.source !== session.attr?.source)
  ) {
    session = { id: uid(), started: now, last: now, pages: 0, attr: incoming };
  }
  session.pages += 1;
  session.last = now;
  const saveSession = () => {
    try {
      ss?.setItem('ge360_session', JSON.stringify(session));
    } catch {
      /* storage pieno o bloccato */
    }
  };
  saveSession();

  let visitorId = '';
  if (ls) {
    visitorId = ls.getItem('ge360_vid') || '';
    if (!visitorId) {
      visitorId = uid();
      ls.setItem('ge360_vid', visitorId);
    }
  }

  const device = (() => {
    const ua = navigator.userAgent || '';
    const shortSide = Math.min(window.screen?.width || 0, window.screen?.height || 0);
    if (/iPad|Tablet/i.test(ua) || (/Android/i.test(ua) && !/Mobi/i.test(ua))) return 'tablet';
    if (/Mobi|iPhone|Android/i.test(ua) || (shortSide && shortSide < 600)) return 'mobile';
    return 'desktop';
  })();

  // ---------- invio ----------
  const build = (eventType, extra = {}, value = null) => {
    const attr = session.attr || {};
    return {
      event_id: uid(),
      event_type: eventType,
      source: attr.source || 'direct',
      campaign: attr.campaign || '',
      content_id: cfg.contentId || '',
      url: window.location.href,
      referrer: document.referrer || '',
      session_id: session.id,
      visitor_id: visitorId,
      device,
      value,
      meta: {
        medium: attr.medium || '',
        term: attr.term || '',
        content: attr.content || '',
        click_id: attr.click_id || '',
        landing: attr.landing || '',
        page_index: session.pages,
        lang: cut(navigator.language, 16),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        ...extra,
      },
    };
  };

  const post = (events) => {
    const body = JSON.stringify({ events });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' });
      if (navigator.sendBeacon(cfg.endpoint, blob)) return;
    }
    fetch(cfg.endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body,
    }).catch(() => {});
  };

  let queue = [];
  const flush = () => {
    while (queue.length) post(queue.splice(0, 20));
  };
  // Conversioni e page view partono subito; il resto viaggia a blocchi.
  const send = (type, extra, value) => post([build(type, extra, value)]);
  const enqueue = (type, extra, value) => {
    queue.push(build(type, extra, value));
    if (queue.length >= 15) flush();
  };

  // ---------- page view / 404 ----------
  send('page_view', { title: cut(document.title, 160) });
  if (cfg.is404) send('page_404', { path: cut(window.location.pathname, 300) });

  // ---------- scroll ----------
  const marks = [25, 50, 75, 90];
  const reached = new Set();
  let maxScroll = 0;
  let scrollScheduled = false;
  const measureScroll = () => {
    scrollScheduled = false;
    const doc = document.documentElement;
    const height = Math.max(doc.scrollHeight, document.body?.scrollHeight || 0);
    if (!height) return;
    const percent = Math.min(100, Math.round(((window.scrollY + window.innerHeight) / height) * 100));
    maxScroll = Math.max(maxScroll, percent);
    for (const mark of marks) {
      if (percent >= mark && !reached.has(mark)) {
        reached.add(mark);
        enqueue('scroll_depth', {}, mark);
      }
    }
  };
  window.addEventListener('scroll', () => {
    if (!scrollScheduled) {
      scrollScheduled = true;
      window.requestAnimationFrame(measureScroll);
    }
  }, { passive: true });

  // ---------- tempo di attenzione reale ----------
  let lastActive = Date.now();
  let engagedMs = 0;
  let engagedSent = 0;
  const markActive = () => {
    lastActive = Date.now();
  };
  ['scroll', 'mousemove', 'keydown', 'touchstart', 'pointerdown'].forEach((name) =>
    window.addEventListener(name, markActive, { passive: true })
  );
  window.setInterval(() => {
    if (document.visibilityState === 'visible' && Date.now() - lastActive < ACTIVE_WINDOW_MS) {
      engagedMs += 1000;
    }
  }, 1000);

  const reportEngagement = () => {
    const delta = engagedMs - engagedSent;
    if (delta < 1000) return;
    engagedSent = engagedMs;
    enqueue('page_engagement', { max_scroll: maxScroll }, delta);
  };

  // ---------- click ----------
  const DOWNLOAD = /\.(pdf|docx?|xlsx?|pptx?|zip|rar|dwg)(\?|#|$)/i;
  let lastClick = { target: null, time: 0, count: 0 };

  document.addEventListener('click', (event) => {
    // Rage click: 3+ click ravvicinati sullo stesso elemento = frustrazione.
    const target = event.target;
    const t = Date.now();
    if (target === lastClick.target && t - lastClick.time < 700) lastClick.count += 1;
    else lastClick.count = 1;
    lastClick.target = target;
    lastClick.time = t;
    if (lastClick.count === 3) enqueue('rage_click', { target: selectorOf(target) });

    const link = target.closest?.('a[href]');
    if (!link) return;
    const raw = (link.getAttribute('href') || '').trim();
    const href = raw.toLowerCase();
    const label = { target: selectorOf(link), text: cut(link.textContent?.trim(), 60) };

    if (href.startsWith('tel:')) return send('phone_click', label);
    if (href.startsWith('mailto:')) return send('email_click', label);
    if (href.includes('wa.me/') || href.includes('api.whatsapp.com/') || href.includes('whatsapp://')) {
      return send('whatsapp_click', label);
    }
    if (link.matches('[data-ge360-track="cta"]')) return send('cta_click', label);

    if (DOWNLOAD.test(href)) {
      const ext = (href.match(DOWNLOAD) || [])[1] || '';
      return enqueue('file_download', { ...label, file_ext: ext });
    }

    try {
      const url = new URL(raw, window.location.href);
      const host = url.hostname.toLowerCase().replace(/^www\./, '');
      if (/^https?:$/.test(url.protocol) && host && host !== ownHost) {
        enqueue('outbound_click', { ...label, target_host: host });
      }
    } catch {
      /* href non valido */
    }
  }, { passive: true, capture: true });

  // ---------- moduli ----------
  const isTrackedForm = (form) =>
    form instanceof HTMLFormElement &&
    (form.matches('[data-ge360-track="form"]') ||
      form.matches('.wpcf7-form') ||
      form.matches('.wp-block-jetpack-contact-form') ||
      form.querySelector('input[type="email"], input[type="tel"]'));

  const formId = (form) => {
    const forms = Array.from(document.forms);
    return cut(form.id || form.getAttribute('name') || `form_${forms.indexOf(form) + 1}`, 60);
  };

  const startedForms = new WeakSet();
  document.addEventListener('focusin', (event) => {
    const form = event.target?.form || event.target?.closest?.('form');
    if (!form || startedForms.has(form) || !isTrackedForm(form)) return;
    startedForms.add(form);
    enqueue('form_start', { form_id: formId(form) });
  }, true);

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!isTrackedForm(form)) return;
    send('form_submit', { form_id: formId(form) });
  }, true);

  // ---------- Core Web Vitals (misurati sui visitatori reali) ----------
  const vitals = window.webVitals;
  if (vitals) {
    const report = (metric) => {
      const a = metric.attribution || {};
      const target = a.element || a.interactionTarget || a.largestShiftTarget || '';
      enqueue(
        'web_vital',
        { metric_name: metric.name, metric_rating: metric.rating, vital_target: cut(target) },
        metric.name === 'CLS' ? Math.round(metric.value * 1000) / 1000 : Math.round(metric.value)
      );
    };
    ['onLCP', 'onINP', 'onCLS', 'onFCP', 'onTTFB'].forEach((name) => {
      try {
        vitals[name]?.(report);
      } catch {
        /* browser non supportato */
      }
    });
  }

  // I listener di chiusura vanno registrati DOPO web-vitals, così le sue
  // misure finali entrano nella coda prima dell'invio.
  const onHide = () => {
    reportEngagement();
    session.last = Date.now();
    saveSession();
    flush();
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') onHide();
  });
  window.addEventListener('pagehide', onHide);
})();
