# GE360 Analitica 0.4

Centro dati self-hosted per **WordPress, Google Analytics 4, Search Console, Google Business Profile, Facebook/Instagram, lead, SEO locale e AI locale Ollama/Qwen**.

La 0.4 introduce una **Configurazione guidata passo-passo** pensata per evitare modifiche manuali ai file di configurazione.

## Primo avvio / aggiornamento

Apri:

```
http://127.0.0.1:8788
```

Al primo avvio della 0.4 si apre automaticamente **Configurazione**.

Il wizard contiene 6 passaggi:

1. **Sistema**
   - controlla GE360
   - rileva Ollama
   - rileva i modelli locali già presenti
   - controlla configurazioni salvate

2. **AI Locale**
   - rileva Ollama su `127.0.0.1:11434`
   - mostra i modelli già installati
   - permette di scegliere Qwen o altro modello
   - testa e salva la scelta
   - non scarica modelli

3. **WordPress**
   - URL sito
   - username opzionale
   - Application Password opzionale
   - chiave GE360 Tracker
   - test reale della REST API e tracker

4. **Google**
   - Client ID
   - Client Secret
   - login OAuth
   - ricerca automatica proprietà GA4
   - ricerca automatica siti Search Console
   - ricerca automatica account/sedi Google Business Profile
   - selezione e salvataggio

5. **Facebook + Instagram**
   - Meta App ID
   - App Secret
   - Facebook Page ID
   - Page Access Token
   - rilevamento automatico dell'Instagram Professional Account collegato
   - import base di follower, media count e contenuti Instagram/Reel

6. **Verifica finale**
   - riepilogo stato
   - sincronizzazione completa
   - accesso alla dashboard

## Dove vengono salvate le credenziali

Il wizard salva la configurazione runtime in:

```
/var/lib/ge360-analitica/secrets/runtime_config.json
```

Il file viene creato dal servizio GE360 con permessi stretti.

Il refresh token Google resta in:

```
/var/lib/ge360-analitica/secrets/google_oauth.json
```

Le password e i token non vengono restituiti in chiaro dall'API di stato del wizard.

## Compatibilità con configurazioni precedenti

GE360 cerca i valori in questo ordine:

1. impostazioni salvate dal wizard;
2. variabili del file `/etc/ge360-analitica/ge360.env`;
3. valori predefiniti sicuri.

Quindi le configurazioni precedenti continuano a funzionare.

## Aggiornamento

La nuova versione si installa sopra quella esistente:

```bash
sudo apt install ./ge360-analitica_0.4.0_amd64.deb
```

Non disinstallare prima.

Restano persistenti:

- database;
- storico;
- report AI;
- token Google;
- configurazione wizard;
- file `ge360.env`.

Ollama e Qwen non vengono reinstallati e non vengono riscaricati.

## AI locale

```
WordPress / Google / Meta
          |
          v
      GE360 SQLite
          |
          v
     Ollama + Qwen
          |
          v
      report locale
          |
          +--> Copia per ChatGPT / Claude
```

GE360 usa:

- `GET /api/tags` per vedere i modelli Ollama già installati;
- `POST /api/chat` per i report.

## Facebook e Instagram

Il connettore Meta usa la Facebook Page come punto di accesso. Se alla Pagina è collegato un account Instagram Professional (Business/Creator), GE360 prova a rilevarlo automaticamente e importa:

- username;
- follower;
- media count;
- post;
- Reel;
- permalink e timestamp.

## Google

Il wizard usa un solo flusso OAuth per:

- Google Analytics;
- Search Console;
- Google Business Profile.

Dopo il login prova a scoprire automaticamente le risorse disponibili.

## Sicurezza

- dashboard e API solo su localhost;
- Ollama solo locale;
- nessuna API OpenAI/Anthropic;
- token salvati solo sul server;
- i segreti non vengono mostrati in chiaro dopo il salvataggio;
- aggiornamenti `.deb` non cancellano dati/configurazione.
