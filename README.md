# GE360 Analitica 0.6.4

Dashboard self-hosted per WordPress, Google, Facebook/Instagram, lead, SEO locale e AI locale Ollama/Qwen.

## Novità 0.6.4: elenco completo Pagine Facebook

GE360 ora percorre automaticamente la paginazione di `/me/accounts` fino a trovare tutte le Pagine Facebook autorizzate, con un limite di sicurezza di 20 chiamate API o 1000 Pagine totali.

- deduplica per Page ID;
- ordinamento alfabetico;
- ricerca immediata nel wizard;
- lista scrollabile fino a circa 550 px;
- indicazione dell'account Instagram professionale collegato;
- nessun Page Access Token viene inviato al frontend.

## Facebook Login senza App Secret obbligatorio

Il percorso normale Meta è stato semplificato:

1. In Meta for Developers crea/seleziona l'app GE360.
2. In GE360 vai in **Configurazione → Facebook + Instagram**.
3. Inserisci soltanto il **Meta App ID**.
4. Premi **Accedi con Facebook**.
5. Il login viene aperto tramite il Facebook JavaScript SDK ufficiale.
6. GE360 valida il token contro Graph API.
7. GE360 mostra il profilo Facebook utilizzato.
8. GE360 legge le Pagine disponibili tramite `/me/accounts`.
9. Scegli la Pagina.
10. Se alla Pagina è collegato un account Instagram professionale Business/Creator, GE360 lo rileva e lo associa automaticamente.

Il normale login non richiede di copiare:
- App Secret;
- Page ID;
- Page Access Token;
- Instagram Account ID.

L'App Secret resta disponibile soltanto in **Configurazione Meta avanzata** per un eventuale flusso OAuth server e conversione token long-lived.

### Permessi richiesti

GE360 richiede attualmente:

- `pages_show_list`
- `pages_read_engagement`
- `read_insights`
- `instagram_basic`
- `instagram_manage_insights`

L'account Instagram deve essere professionale e collegato alla Pagina Facebook per il flusso Instagram API with Facebook Login.

## Tailscale / HTTPS

GE360 continua ad ascoltare sul loopback locale:

`http://127.0.0.1:8788`

Tailscale Serve può pubblicare il frontend all'interno della tailnet tramite HTTPS.

Quando GE360 viene aperto da un hostname Tailscale HTTPS (`*.ts.net`), la 0.6 registra automaticamente l'origine corrente come `GE360_PUBLIC_ORIGIN` e mantiene coerente anche il callback Meta avanzato:

`https://<host-tailnet>/api/oauth/meta/callback`

Nel passaggio **Sistema** è presente anche il comando **Registra indirizzo corrente**.

GE360 non usa Funnel e non rende automaticamente pubblico il server su Internet.

## Google

Il flusso Google resta quello della 0.5:

1. crea un client OAuth **Applicazione Web** in Google Cloud;
2. autorizza:
   `http://127.0.0.1:8788/api/oauth/google/callback`
3. scarica il JSON OAuth;
4. in GE360 usa **Importa JSON OAuth**;
5. premi **Accedi con Google**;
6. GE360 prova a trovare Analytics, Search Console e Google Business Profile.

## WordPress

Per il plugin GE360 Tracker servono normalmente:

- URL del sito;
- chiave GE360 Tracker.

Le opzioni WordPress avanzate restano nascoste nel wizard.

## AI locale

GE360 rileva Ollama e i modelli già presenti sul Linux. Non scarica Qwen automaticamente e non richiede API OpenAI/Anthropic.

## Dati e credenziali

Configurazione persistente:

`/var/lib/ge360-analitica/secrets/runtime_config.json`

Token Google:

`/var/lib/ge360-analitica/secrets/google_oauth.json`

I token Meta e Google non vengono restituiti in chiaro dall'API di stato.

## Aggiornamento Linux

Installa la nuova versione sopra quella precedente:

```bash
sudo apt install ./ge360-analitica_0.6.4_amd64.deb
```

Non disinstallare prima. Database, report e configurazione persistente vengono conservati.

## Dashboard

Locale:

`http://127.0.0.1:8788`

oppure:

```bash
ge360-open
```

Se Tailscale Serve è configurato, usa preferibilmente il relativo URL HTTPS per Facebook Login.
