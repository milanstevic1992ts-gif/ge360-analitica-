(() => {
  const cfg = window.GE360TrackerConfig;
  if (!cfg?.endpoint) return;

  const cleanSource = () => {
    const params = new URLSearchParams(window.location.search);
    return params.get('utm_source') || '';
  };

  const cleanCampaign = () => {
    const params = new URLSearchParams(window.location.search);
    return params.get('utm_campaign') || '';
  };

  const send = (eventType) => {
    const body = JSON.stringify({
      event_type: eventType,
      source: cleanSource(),
      campaign: cleanCampaign(),
      content_id: cfg.contentId || '',
      url: window.location.href,
      referrer: document.referrer || '',
    });

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

  send('page_view');

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    if (!link) return;

    const href = (link.getAttribute('href') || '').trim().toLowerCase();

    if (href.startsWith('tel:')) {
      send('phone_click');
      return;
    }

    if (href.startsWith('mailto:')) {
      send('email_click');
      return;
    }

    if (
      href.includes('wa.me/') ||
      href.includes('api.whatsapp.com/') ||
      href.includes('whatsapp://')
    ) {
      send('whatsapp_click');
      return;
    }

    if (link.matches('[data-ge360-track="cta"]')) {
      send('cta_click');
    }
  }, { passive: true });

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;

    if (
      form.matches('[data-ge360-track="form"]') ||
      form.matches('.wpcf7-form') ||
      form.matches('.wp-block-jetpack-contact-form') ||
      form.querySelector('input[type="email"], input[type="tel"]')
    ) {
      send('form_submit');
    }
  }, true);
})();
