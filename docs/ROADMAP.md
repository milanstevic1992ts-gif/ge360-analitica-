# Roadmap

## Fase 0 — Fondazione
- [x] Docker Compose
- [x] FastAPI
- [x] SQLite
- [x] dashboard React responsive
- [x] dataset demo
- [x] modello metriche / eventi / lead
- [x] stato connettori

## Fase 1 — WordPress + lead tracking
- [ ] collegamento WordPress REST API
- [ ] inventario pagine/articoli
- [ ] endpoint tracking leggero GE360
- [ ] click WhatsApp
- [ ] click telefono
- [ ] invio richiesta preventivo
- [ ] UTM / referrer
- [ ] landing page iniziale

## Fase 2 — Google
- [ ] OAuth Google
- [ ] Google Analytics 4
- [ ] Search Console
- [ ] Google Business Profile
- [ ] recensioni
- [ ] chiamate / click sito / indicazioni quando disponibili via API
- [ ] query SEO locale

## Fase 3 — Meta
- [ ] OAuth Meta
- [ ] Facebook Page
- [ ] contenuti e performance
- [ ] Reel / post
- [ ] engagement
- [ ] traffico verso il sito
- [ ] gestione graceful delle metriche non più disponibili

## Fase 4 — Intelligence

### Opportunity Radar
Trova pagine o contenuti con:
- tanto traffico ma pochi lead
- tante impression ma CTR basso
- crescita rapida
- calo improvviso

### Anomaly Watch
Confronta oggi / 7 giorni / 30 giorni e segnala variazioni insolite.

### Content Pulse
Unifica pagina WordPress + post/reel social + traffico + lead prodotti.

### Local SEO Radar
Monitora query che contengono Trieste, quartieri, servizi e intenzioni commerciali.

### Lead attribution
Percorso:
```
source -> campaign/content -> landing page -> action -> lead
```

## Fase 5 — ChatGPT come interfaccia intelligente
- [x] architettura MCP read-only
- [x] GE360 come fonte dati/tool per ChatGPT
- [ ] plugin/app GE360 Analitica in ChatGPT
- [ ] strumenti summary / sorgenti / contenuti / lead / connettori
- [ ] briefing automatico
- [ ] domande in linguaggio naturale
- [ ] "cosa è migliorato?"
- [ ] "cosa è peggiorato?"
- [ ] "quale contenuto dovrei rifare?"
- [ ] spiegazione basata sempre sui dati e non su supposizioni
- [ ] conversazioni gestite direttamente in ChatGPT
- [ ] eventuale fallback locale solo se utile

## Fase 6 — Operatività
- [ ] scheduler sync
- [ ] backup
- [ ] audit log
- [ ] export CSV
- [ ] export PDF report
- [ ] notifiche
- [ ] health dashboard
