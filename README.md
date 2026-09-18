# GE360 Analitica

Centro dati self-hosted per riunire in un'unica dashboard i dati di **Facebook/Meta, Google Business Profile, WordPress, Google Analytics 4 e Google Search Console**, mantenendo ChatGPT come interfaccia intelligente tramite plugin MCP.

## Obiettivo

GE360 Analitica costruisce un modello dati comune per leggere il percorso:

```
Sorgente -> contenuto/pagina -> visita -> azione -> lead
```

Esempi:

- Google Search -> pagina servizio -> WhatsApp -> richiesta preventivo
- Facebook -> visita sito -> telefono -> contatto
- Google Business Profile -> click sito/chiamata -> visita/azione

## Principi

- self-hosted su Linux
- Docker first
- dati storici conservati localmente
- SQLite in partenza, PostgreSQL-ready
- connettori indipendenti e sostituibili
- API-first
- dashboard veloce e responsive
- sincronizzazione automatica
- nessun modello AI incorporato
- ChatGPT resta la chat e usa GE360 tramite strumenti MCP read-only

## Avvio rapido

```bash
cp .env.example .env
docker compose up -d --build
```

Dashboard: http://127.0.0.1:8788  
API: http://127.0.0.1:8787  
API docs: http://127.0.0.1:8787/docs

## Stato moduli

| Modulo | Stato |
|---|---|
| Dashboard live + fallback demo | Attivo |
| SQLite storico metriche/eventi/lead | Attivo |
| Sync automatico | Attivo |
| WordPress contenuti | Attivo |
| GE360 Tracker WordPress | Attivo, da installare sul sito |
| GA4 | Implementato, richiede collegamento Google |
| Search Console | Implementato, richiede collegamento Google |
| Google Business Profile | Implementato, richiede accesso API Google |
| Meta / Facebook Page | Implementato, richiede Page token e Page ID |
| Funnel / attribuzione | Attivo |
| Opportunity Radar | Attivo |
| Anomaly Watch | Attivo |
| Local SEO Radar | Attivo |
| ChatGPT / GE360 MCP Plugin | Attivo |
| Backup / export report | Roadmap |

## WordPress tracker

Il repository contiene un plugin WordPress privacy-first che registra:

- page view
- click WhatsApp
- click telefono
- click email
- invio moduli
- CTA esplicitamente marcate

Non registra nome, email, telefono, contenuto dei moduli, IP o user-agent.

GitHub Actions genera automaticamente `ge360-tracker.zip`.

## Google

GE360 usa un unico flusso OAuth locale per:

- Google Analytics 4
- Search Console
- Google Business Profile Performance API

La dashboard espone **Collega Google** e salva il refresh token solo sul server locale.

## Meta

Il connettore usa Graph API versionata e metriche Page Insights moderne, provandole singolarmente per evitare che una metrica rimossa blocchi l'intera sincronizzazione.

## ChatGPT

GE360 non chiama un modello via API.

```
ChatGPT -> plugin GE360 -> MCP locale -> API GE360 -> SQLite
```

Vedi [docs/CHATGPT_MCP.md](docs/CHATGPT_MCP.md).

## Ispirazione progettuale

Il progetto prende spunti architetturali e UX da Plausible, PostHog, Mixpost, Metabase, Apache Superset e Matomo, ma l'implementazione di GE360 Analitica è specifica per questo progetto.

Vedi anche [docs/INSPIRATION.md](docs/INSPIRATION.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) e [docs/ROADMAP.md](docs/ROADMAP.md).
