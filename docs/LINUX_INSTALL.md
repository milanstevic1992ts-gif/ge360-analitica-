# GE360 Analitica — installazione Linux

## Pacchetto consigliato

Per Debian/Ubuntu x86_64 usare:

```
ge360-analitica_0.2.0_amd64.deb
```

Installazione:

```bash
sudo apt install ./ge360-analitica_0.2.0_amd64.deb
```

Dopo l'installazione:

- servizio: `ge360-analitica.service`
- dashboard: `http://127.0.0.1:8788`
- configurazione: `/etc/ge360-analitica/ge360.env`
- database: `/var/lib/ge360-analitica/ge360.db`
- segreti OAuth: `/var/lib/ge360-analitica/secrets/`
- applicazione: `/opt/ge360-analitica/`

## Comandi utili

Versione:

```bash
ge360-analitica version
```

Apri dashboard:

```bash
ge360-open
```

Stato servizio:

```bash
systemctl status ge360-analitica
```

Log:

```bash
journalctl -u ge360-analitica -f
```

Riavvio:

```bash
sudo systemctl restart ge360-analitica
```

## Configurazione

Modificare:

```bash
sudo nano /etc/ge360-analitica/ge360.env
```

Poi:

```bash
sudo systemctl restart ge360-analitica
```

## ChatGPT

Il pacchetto include anche la parte plugin ChatGPT/MCP.

Preparazione runtime MCP, eseguita come utente desktop normale:

```bash
ge360-chatgpt-setup
```

Plugin installato in:

```
/opt/ge360-analitica/chatgpt-plugin
```

GE360 MCP usa la dashboard/API locale su `127.0.0.1:8788`.

## Aggiornamenti

Installare un nuovo `.deb` sopra la versione precedente:

```bash
sudo apt install ./ge360-analitica_VERSIONE_amd64.deb
```

Il database in `/var/lib/ge360-analitica` e il file configurazione in `/etc/ge360-analitica` non vengono sostituiti durante un normale aggiornamento.

## Disinstallazione

```bash
sudo apt remove ge360-analitica
```

La rimozione del pacchetto non cancella automaticamente il database in `/var/lib/ge360-analitica`.

## Pacchetto portabile

GitHub Actions genera anche:

```
ge360-analitica-linux-amd64-0.2.0.tar.gz
```

È pensato per diagnostica, backup o installazioni manuali. Per Debian è preferibile il `.deb`.
