# ChatGPT + GE360 Analitica

## Obiettivo

GE360 non incorpora un modello e non usa una OpenAI API key.

L'intelligenza resta in **ChatGPT**. GE360 espone invece strumenti read-only tramite Model Context Protocol (MCP).

```
Utente
  |
  v
ChatGPT (Chat / Work)
  |
  | plugin GE360 Analitica
  v
MCP stdio locale
  |
  v
mcp_server/server.py
  |
  v
data/ge360.db (read-only)
```

## Esperienza utente

L'uso previsto è la normale conversazione ChatGPT.

Esempi:

- "Analizza GE360 negli ultimi 30 giorni."
- "Quale sorgente mi sta portando più lead?"
- "Confronta questa settimana con la precedente."
- "Ci sono anomalie?"
- "Quali dati mancano per capire meglio le conversioni?"

ChatGPT decide quali strumenti GE360 chiamare e poi risponde nella conversazione.

## Perché questa architettura

- nessuna OpenAI API key nel progetto;
- nessun clone della UI ChatGPT;
- nessun modello locale obbligatorio;
- nessun Codex CLI;
- il modello e la conversazione restano quelli selezionati in ChatGPT;
- GE360 rimane un sistema analytics indipendente;
- l'integrazione è read-only per progettazione.

## Strumenti MCP iniziali

### ge360_status
Stato del database e dei connettori.

### ge360_metrics
Metriche normalizzate per provider, nome e periodo.

### ge360_events_summary
Eventi aggregati per tipo e sorgente.

### ge360_leads_summary
Lead aggregati per canale e sorgente.

### ge360_recent_leads
Campi esclusivamente analitici dei lead recenti. Nessun payload grezzo.

### ge360_compare_periods
Confronta una metrica tra periodo corrente e precedente.

## Preparazione locale

Dalla root del repository:

```bash
chmod +x scripts/setup-chatgpt-plugin.sh
./scripts/setup-chatgpt-plugin.sh
```

Lo script crea `.venv` e installa l'SDK MCP.

## Plugin

La root contiene:

- `plugin.json`: identità del plugin;
- `mcp.json`: server MCP stdio;
- `skills/ge360-analitica/SKILL.md`: istruzioni analitiche;
- `mcp_server/server.py`: strumenti read-only.

Il plugin locale MCP è pensato per ChatGPT Desktop. La disponibilità dell'importazione locale e del Developer Mode dipende dal piano/account e dalla versione di ChatGPT.

## Sicurezza

Il database viene aperto con SQLite `mode=ro`.

Il server non espone strumenti per:

- modificare lead;
- cambiare metriche;
- scrivere nel database;
- leggere password;
- leggere token OAuth;
- eseguire comandi arbitrari.

Le credenziali dei connettori rimangono fuori dagli strumenti MCP.

## Futuro

Quando il database reale sarà popolato, possiamo aggiungere:

- `ge360_opportunity_radar`
- `ge360_local_seo_summary`
- `ge360_content_performance`
- `ge360_anomalies`
- `ge360_attribution_paths`

La logica statistica deterministica rimane in GE360; ChatGPT interpreta e spiega i risultati.
