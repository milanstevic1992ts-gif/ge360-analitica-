# Roadmap

## Fase 0 — Fondazione
- [x] Docker Compose
- [x] FastAPI
- [x] SQLite
- [x] dashboard React responsive
- [x] fallback demo
- [x] dashboard live
- [x] modello metriche / eventi / lead / contenuti
- [x] stato connettori
- [x] deduplica dati storici
- [x] sincronizzazione incrementale

## Fase 1 — WordPress + lead tracking
- [x] connettore WordPress REST API
- [x] inventario pagine/articoli
- [x] plugin GE360 Tracker
- [x] page view
- [x] click WhatsApp
- [x] click telefono
- [x] invio moduli
- [x] UTM / referrer
- [x] attribuzione landing page
- [x] endpoint REST protetto per sync
- [x] cursore incrementale / deduplica
- [x] ZIP installabile via GitHub Actions
- [ ] installazione tracker sul sito reale
- [ ] verifica eventi reali raccolti

## Fase 2 — Google
- [x] OAuth Google lato GE360
- [x] salvataggio refresh token locale
- [x] Google Analytics 4 Data API
- [x] Search Console API
- [x] Google Business Profile Performance API
- [x] chiamate / click sito / indicazioni / impression Business Profile
- [x] keyword mensili Google Business
- [x] query SEO locale
- [ ] creare/configurare credenziali OAuth Google reali
- [ ] collegare property GA4
- [ ] collegare property Search Console
- [ ] collegare location Google Business
- [ ] valutare recensioni Google in modulo separato

## Fase 3 — Meta
- [x] connettore Facebook Page
- [x] Graph API versionata
- [x] Page Insights resilienti a metriche rimosse
- [x] catalogo post Facebook
- [x] gestione graceful metriche non disponibili
- [ ] OAuth Meta guidato
- [ ] collegare Page ID e Page access token reali
- [ ] post-level performance / Reel
- [ ] Instagram Professional se collegato

## Fase 4 — Intelligence deterministica
- [x] Opportunity Radar
- [x] Anomaly Watch
- [x] Content Performance
- [x] Local SEO Radar
- [x] Lead attribution
- [x] confronti fra periodi
- [x] KPI live
- [x] insight dashboard basati sui dati
- [ ] scoring opportunità più evoluto
- [ ] attribuzione multi-touch

## Fase 5 — ChatGPT come interfaccia intelligente
- [x] architettura MCP read-only
- [x] GE360 come fonte dati/tool per ChatGPT
- [x] plugin GE360 Analitica
- [x] manifesti plugin/MCP validati in CI
- [x] skill GE360
- [x] strumenti status / metriche / lead / contenuti / anomalie / SEO
- [x] marketplace locale repository
- [ ] installazione effettiva nel ChatGPT Desktop dell'host Linux
- [ ] test conversazioni su dati reali
- [ ] briefing automatici basati su GE360

## Fase 6 — Operatività
- [x] scheduler sync automatico
- [x] sync manuale da dashboard
- [x] porte API/dashboard limitate a localhost
- [x] CI backend/frontend/MCP/plugin/WordPress
- [ ] backup automatico SQLite + secrets
- [ ] audit log
- [ ] export CSV
- [ ] export PDF report
- [ ] notifiche
- [ ] health dashboard avanzata
