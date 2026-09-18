# GE360 Analitica

Centro dati self-hosted per riunire in un'unica dashboard **WordPress, Google Analytics 4, Search Console, Google Business Profile, Meta/Facebook, lead e SEO locale**.

La versione 0.3 introduce **GE360 Intelligence locale** con Ollama/Qwen.

## Architettura

```
WordPress / Google / Meta
          |
          v
      GE360 SQLite
          |
          +--> dashboard e analisi deterministiche
          |
          v
     Ollama + Qwen
          |
          v
  report locale dettagliato
          |
          +--> copia manuale per ChatGPT / Claude
```

GE360 non usa API OpenAI/Anthropic e non scarica modelli AI.

## AI locale

GE360 usa l'Ollama già installato sul computer.

Endpoint predefinito:

```
http://127.0.0.1:11434
```

Dalla pagina **AI Locale** puoi:

- rilevare automaticamente Ollama;
- vedere tutti i modelli già installati;
- selezionare Qwen o un altro modello;
- salvare la configurazione nel database GE360;
- testare il modello;
- generare un brief rapido;
- generare un report approfondito;
- conservare lo storico dei report;
- copiare il report;
- generare e copiare un prompt completo per ChatGPT/Claude;
- scaricare il report Markdown.

**GE360 non esegue `ollama pull` e non riscarica Qwen.**

## Aggiornamento Linux

Se hai già GE360 installato, il nuovo pacchetto si installa sopra la versione precedente:

```bash
sudo apt install ./ge360-analitica_0.3.0_amd64.deb
```

Restano invariati:

- database: `/var/lib/ge360-analitica/ge360.db`
- token e segreti: `/var/lib/ge360-analitica/secrets/`
- configurazione: `/etc/ge360-analitica/ge360.env`
- report AI memorizzati nel database.

Non devi disinstallare prima GE360 e non devi reinstallare Ollama/Qwen.

## Dashboard

Dopo l'installazione:

```
http://127.0.0.1:8788
```

oppure:

```bash
ge360-open
```

## Moduli

| Modulo | Stato |
|---|---|
| Panoramica | Attivo |
| Acquisizione | Attivo |
| Contenuti | Attivo |
| Lead | Attivo |
| SEO locale | Attivo |
| Connettori | Attivo |
| AI Locale Ollama/Qwen | Attivo |
| Report AI + storico | Attivo |
| Copia per ChatGPT/Claude | Attivo |
| WordPress Tracker | Attivo |
| GA4 | Implementato, richiede collegamento |
| Search Console | Implementato, richiede collegamento |
| Google Business Profile | Implementato, richiede collegamento |
| Meta/Facebook Page | Implementato, richiede collegamento |
| Sync automatico | Attivo |
| Opportunity Radar | Attivo |
| Anomaly Watch | Attivo |

## WordPress Tracker

Il plugin companion registra in modo privacy-first:

- page view;
- click WhatsApp;
- click telefono;
- click email;
- invio moduli;
- CTA;
- UTM/referrer.

Non registra nome, email, telefono, contenuto dei moduli, IP o user-agent.

## Sicurezza

- dashboard e API bindate a localhost;
- Ollama accettato solo su localhost/127.0.0.1;
- nessuna API key AI;
- niente invio automatico di dati a ChatGPT o Claude;
- copia verso modelli esterni solo su azione manuale dell'utente.

## Ollama API

GE360 usa:

- `GET /api/tags` per rilevare i modelli installati;
- `POST /api/chat` con `stream:false` per generare l'analisi.

La logica statistica rimane in GE360; il modello locale interpreta dati già strutturati.
