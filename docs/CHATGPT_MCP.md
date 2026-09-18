# ChatGPT + GE360 Analitica

## Architettura

GE360 non incorpora un modello e non usa una OpenAI API key.

L'intelligenza resta nella normale conversazione **ChatGPT**. Il plugin GE360 espone strumenti read-only tramite MCP e interroga la API locale del gestionale.

```
Utente
  |
  v
ChatGPT Desktop
  |
  | plugin GE360 Analitica
  v
MCP stdio locale
  |
  v
mcp_server/server.py
  |
  | HTTP solo localhost
  v
http://127.0.0.1:8787
  |
  v
GE360 API -> SQLite
```

Questa separazione è intenzionale: la copia del plugin installata da ChatGPT può vivere nella propria cache, mentre i dati rimangono nel gestionale GE360 in esecuzione.

## Esperienza

Esempi di richieste:

- "Analizza GE360 negli ultimi 30 giorni."
- "Quale sorgente mi sta portando più lead?"
- "Confronta questa settimana con la precedente."
- "Trova pagine visitate che non stanno convertendo."
- "Ci sono anomalie negli ultimi 7 giorni?"
- "Come stanno andando le query locali con Trieste?"

ChatGPT sceglie gli strumenti GE360 necessari e risponde nella conversazione.

## Strumenti MCP

- `ge360_status`: quantità dati, aggiornamenti e connettori.
- `ge360_metrics`: metriche normalizzate.
- `ge360_events_summary`: eventi per tipo e sorgente.
- `ge360_leads_summary`: lead aggregati.
- `ge360_recent_leads`: soli campi analitici, nessun payload personale.
- `ge360_compare_periods`: confronto deterministico fra periodi.
- `ge360_opportunity_radar`: traffico alto con conversione debole.
- `ge360_content_performance`: pagina -> azioni -> lead.
- `ge360_anomalies`: variazioni rilevanti rispetto al periodo precedente.
- `ge360_local_seo`: query Search Console che contengono località/parole specifiche.

Tutti gli strumenti sono dichiarati read-only.

## Preparazione Linux

Dalla root del repository:

```bash
chmod +x scripts/setup-chatgpt-plugin.sh
./scripts/setup-chatgpt-plugin.sh
docker compose up -d --build
```

Lo script crea l'ambiente MCP in:

```
~/.local/share/ge360-analitica/mcp-venv
```

L'ambiente è esterno alla cache del plugin ChatGPT, quindi una reinstallazione del plugin non lo distrugge.

## Rete

Docker pubblica:

- API: `127.0.0.1:8787`
- dashboard: `127.0.0.1:8788`

Non vengono aperte porte su tutte le interfacce di rete.

## Plugin

La root contiene:

- `plugin.json`: identità e presentazione;
- `mcp.json`: server MCP stdio;
- `scripts/run-mcp.sh`: launcher stabile;
- `skills/ge360-analitica/SKILL.md`: strategia di analisi;
- `mcp_server/server.py`: strumenti ChatGPT.

## Sicurezza e privacy

Il plugin:

- non riceve token OAuth dei connettori;
- non espone password;
- non offre tool di scrittura;
- non restituisce `payload_json` dei lead;
- usa la API GE360 locale;
- lascia le formule statistiche deterministiche nel backend;
- lascia a ChatGPT la spiegazione e il ragionamento sui risultati.

La disponibilità dell'importazione di plugin locali, Developer Mode e delle superfici desktop dipende dal piano/account e dalla versione di ChatGPT.
