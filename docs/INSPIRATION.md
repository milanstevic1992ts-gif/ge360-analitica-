# Ispirazione

GE360 Analitica usa idee di prodotto e pattern generali osservati in progetti open source maturi. Non copia il loro codice.

## Plausible
Da prendere:
- overview immediata
- pochi KPI leggibili
- selettore periodo globale
- top pages e sorgenti senza rumore

## PostHog
Da prendere:
- eventi come unità comune
- funnel
- conversioni
- attribuzione
- confronto tra periodi
- alert e insight

## Mixpost
Da prendere:
- connettori social indipendenti
- stato connessioni
- account multipli
- sincronizzazione separata per provider

## Metabase / Apache Superset
Da prendere:
- filtri globali
- drill-down
- grafici riutilizzabili
- viste salvate
- separazione dataset / visualizzazione

## Matomo
Da prendere:
- proprietà locale dei dati
- storico indipendente dalle piattaforme
- privacy e controllo self-hosted

## Regola GE360

Un provider esterno non deve definire il nostro database. Ogni connettore traduce i dati nel modello GE360:

```
provider -> raw snapshot -> normalized metric/event -> dashboard
```

Questo permette di cambiare API, aggiungere nuove piattaforme e conservare lo storico anche quando una metrica viene rimossa dal provider.
