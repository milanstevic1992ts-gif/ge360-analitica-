# Architettura GE360 Analitica

## Obiettivo

Separare nettamente le piattaforme esterne dal modello interno. Facebook, Google o WordPress possono cambiare API senza costringerci a riscrivere dashboard e storico.

```
                           +----------------------+
Meta -------------------->|                      |
Google Business ---------->|                      |
GA4 ---------------------->|  CONNECTOR LAYER     |
Search Console ----------->|                      |
WordPress ---------------->|                      |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           | RAW / NORMALIZATION  |
                           +----------+-----------+
                                      |
                         +------------+-------------+
                         |                          |
                         v                          v
                metric_snapshots                events
                         |                          |
                         +------------+-------------+
                                      |
                                      v
                                   leads
                                      |
                                      v
                           +----------------------+
                           |   GE360 API / KPIs   |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           |      DASHBOARD       |
                           +----------------------+
```

## Modello dati

### metric_snapshots
Serie temporali numeriche recuperate dai provider.

Esempi:
- page_views
- impressions
- followers
- profile_views
- phone_clicks
- direction_requests
- organic_clicks

Ogni snapshot conserva provider, metrica, dimensione e timestamp.

### events
Azioni normalizzate.

Esempi:
- page_view
- whatsapp_click
- phone_click
- form_submit
- facebook_content_click
- google_business_action

### leads
Contatti con attribuzione quando disponibile.

Campi fondamentali:
- channel
- source
- landing_page
- campaign
- status
- value
- created_at

## Regola di normalizzazione

I payload originali non entrano direttamente nella UI.

Ogni connettore deve convertire i dati in nomi GE360 stabili. Se Meta rinomina una metrica, si modifica solo il connettore.

## Dashboard

La dashboard usa endpoint aggregati, non interroga direttamente i provider. Questo rende l'interfaccia veloce e disponibile anche quando un provider è temporaneamente offline.

## Sincronizzazione prevista

- metriche veloci: ogni 1-3 ore
- dati SEO: 1-2 volte al giorno
- WordPress contenuti: su richiesta o ogni 6 ore
- snapshot giornaliero consolidato
- retry con backoff
- log ultimo sync / ultimo errore

## Backup

Il database e la configurazione devono essere inclusi nel sistema di backup GE360. Le credenziali OAuth non vanno mai committate nel repository.

## Evoluzione database

SQLite è adatto al primo deployment e a una singola attività. Il codice dovrà mantenere un repository layer per poter passare a PostgreSQL senza cambiare API e frontend.
