# GE360 Tracker per WordPress

Plugin companion di GE360 Analitica.

Raccoglie:

- page view
- click WhatsApp
- click telefono
- click email
- invio moduli
- CTA marcate con `data-ge360-track="cta"`

Non salva:

- nome
- email
- telefono
- testo inviato nei moduli
- indirizzo IP
- user-agent

## Sincronizzazione

Il server Linux legge gli eventi da:

```
GET /wp-json/ge360/v1/events
X-GE360-Key: <chiave>
```

La chiave viene generata all'attivazione e si trova in:

**WordPress → Impostazioni → GE360 Tracker**

Copiarla nel server:

```
WORDPRESS_GE360_KEY=...
```

Il server usa un cursore incrementale `after_id`, quindi non deve riscaricare tutto a ogni sincronizzazione.
