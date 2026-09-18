# GE360 Agent Bridge — ChatGPT via Codex CLI

GE360 Analitica usa **Codex CLI autenticato con ChatGPT** come agente AI principale.

Non viene usata una OpenAI API key dal progetto e non è previsto pagamento API per singola chiamata quando Codex è autenticato tramite il proprio account ChatGPT. Restano validi i limiti e le disponibilità del piano ChatGPT/Codex.

## Perché un bridge host-side

Il backend GE360 gira in Docker, mentre la sessione Codex è legata all'utente Linux e alle credenziali locali della CLI.

Per evitare di copiare credenziali dentro i container:

```
Dashboard
   |
   v
GE360 API (Docker)
   |
   | Unix socket /data/ge360-codex.sock
   v
GE360 Agent Bridge (Linux host, user service)
   |
   | subprocess
   v
codex exec --sandbox read-only
   |
   v
ChatGPT / Codex
```

Il socket Unix vive nella cartella `data/`, già montata dal backend Docker. Non viene aperta nessuna porta TCP per l'agente.

## Installazione Codex CLI

Su Linux:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

Poi:

```bash
codex
```

Alla prima esecuzione scegli **Sign in with ChatGPT** e completa il login nel browser.

In alternativa:

```bash
codex login
```

## Installazione bridge GE360

Dalla root del repository:

```bash
chmod +x agent_bridge/install.sh
./agent_bridge/install.sh
```

Controllo:

```bash
systemctl --user status ge360-codex-bridge.service
```

## Sicurezza

Le analisi GE360 usano:

```bash
codex exec --sandbox read-only --ask-for-approval never
```

Il bridge:

- non passa password o token dei connettori al modello;
- invia di default solo dati aggregati;
- non invia i payload completi dei lead;
- non permette scrittura sul progetto;
- non espone una porta di rete;
- non salva credenziali ChatGPT nel repository.

## API interna GE360

Il browser non parla direttamente con Codex.

La catena è:

```
POST /api/agent/ask
       |
       v
backend/app/agent.py
       |
       v
Unix socket
       |
       v
agent_bridge/app.py
       |
       v
codex exec
```

Questo ci permette in futuro di cambiare agente senza riscrivere dashboard, database o connettori.
