# GE360 Analitica

Centro dati self-hosted per riunire in un'unica dashboard i dati di **Facebook/Meta, Google Business Profile, WordPress, Google Analytics 4 e Google Search Console**.

## Obiettivo

GE360 Analitica non vuole essere l'ennesima dashboard con cinque riquadri separati. L'obiettivo è costruire un modello dati comune che permetta di leggere il percorso completo:

```
Sorgente -> contenuto/pagina -> visita -> azione -> lead
```

Esempi:

- Google Search -> pagina "Ristrutturazione bagno Trieste" -> WhatsApp -> richiesta preventivo
- Facebook Reel -> visita sito -> click telefono -> lead
- Google Business Profile -> chiamata -> contatto

## Principi

- self-hosted su Linux
- Docker first
- dati storici conservati localmente
- SQLite in partenza, PostgreSQL-ready
- connettori indipendenti e sostituibili
- API-first
- dashboard veloce e leggibile
- niente dipendenza da servizi SaaS per visualizzare i dati
- integrazione futura con Ollama/Qwen/Jarvis

## Avvio rapido

```bash
cp .env.example .env
docker compose up --build
```

Dashboard: http://localhost:8788  
API: http://localhost:8787  
API docs: http://localhost:8787/docs

## Moduli previsti

| Modulo | Stato |
|---|---|
| Dashboard unificata | MVP |
| Database storico | MVP |
| Demo connector | MVP |
| WordPress REST API | scaffolding |
| Meta / Facebook Pages | scaffolding |
| Google Business Profile | scaffolding |
| Google Analytics 4 | scaffolding |
| Search Console | scaffolding |
| Funnel e attribuzione | MVP |
| Alert / insight | MVP |
| Ollama / Qwen | roadmap |

## Ispirazione progettuale

Il progetto prende spunti architetturali e UX da Plausible, PostHog, Mixpost, Metabase, Apache Superset e Matomo, ma l'implementazione di GE360 Analitica è originale e mirata a una singola attività locale.

Vedi [docs/INSPIRATION.md](docs/INSPIRATION.md) e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
