# GE360 Analitica 0.5

Dashboard self-hosted per WordPress, Google, Facebook/Instagram, lead, SEO locale e AI locale Ollama/Qwen.

## Novità 0.5: configurazione Login-first

Il wizard non chiede più Page ID, Page Access Token, Instagram Account ID o ID Google come percorso normale.

### Google

Percorso consigliato:

1. Una sola volta crea un client OAuth **Applicazione Web** in Google Cloud.
2. Imposta come redirect:
   `http://127.0.0.1:8788/api/oauth/google/callback`
3. Scarica il JSON OAuth da Google Cloud.
4. In GE360: **Configurazione → Google → Importa JSON OAuth**.
5. Premi **Accedi con Google**.
6. Scegli il tuo account Google e autorizza.
7. GE360 cerca automaticamente:
   - proprietà Google Analytics;
   - siti Search Console;
   - account/sedi Google Business Profile.
8. Scegli dagli elenchi e salva.

Client ID e Client Secret manuali restano disponibili solo sotto **Configurazione Google avanzata**.

Google Business Profile può richiedere accesso/abilitazione specifica delle Business Profile APIs nel progetto Google Cloud.

### Facebook + Instagram

Percorso consigliato:

1. Una sola volta crea/seleziona una Meta App per GE360.
2. Configura Facebook Login e il redirect:
   `http://127.0.0.1:8788/api/oauth/meta/callback`
3. Inserisci App ID e App Secret una sola volta.
4. Premi **Accedi con Facebook**.
5. Autorizza GE360.
6. GE360 legge le Pagine amministrate dall'account.
7. Scegli la Pagina dall'elenco.
8. GE360 salva automaticamente:
   - Facebook Page ID;
   - Page Access Token;
   - Instagram Professional Account ID, se collegato.

Instagram deve essere un account professionale (Business/Creator) collegato alla Pagina Facebook per il flusso Facebook Login.

## WordPress

Il GE360 Tracker resta semplice:

- URL sito;
- Chiave GE360 Tracker;
- Salva e testa.

Le opzioni WordPress avanzate sono nascoste.

## AI locale

GE360 rileva Ollama e i modelli già presenti sul Linux. Non scarica Qwen e non usa API OpenAI/Anthropic.

## Dati e credenziali

Configurazione wizard:
`/var/lib/ge360-analitica/secrets/runtime_config.json`

Token Google:
`/var/lib/ge360-analitica/secrets/google_oauth.json`

I segreti vengono mascherati nelle API di stato e restano sul server.

## Aggiornamento Linux

Installa la nuova versione direttamente sopra quella precedente:

```bash
sudo apt install ./ge360-analitica_0.5.0_amd64.deb
```

Non disinstallare prima. Database, report, token e configurazione vengono mantenuti.

## Dashboard

`http://127.0.0.1:8788`

oppure:

```bash
ge360-open
```
