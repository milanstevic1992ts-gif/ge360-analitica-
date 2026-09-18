from datetime import date, timedelta


def _trend(days: int = 30) -> list[dict]:
    today = date.today()
    points = []
    for i in range(days):
        day = today - timedelta(days=days - i - 1)
        visits = 68 + ((i * 13) % 31) + int(i * 0.9)
        interactions = 21 + ((i * 7) % 17) + int(i * 0.35)
        leads = 1 + (i % 4 == 0) + (i % 9 == 0)
        points.append(
            {
                "date": day.isoformat(),
                "visits": visits,
                "interactions": interactions,
                "leads": int(leads),
            }
        )
    return points


def dashboard(period: str = "30d") -> dict:
    return {
        "mode": "demo",
        "period": period,
        "kpis": [
            {"key": "visibility", "label": "Visibilità", "value": 18640, "change": 12.4, "format": "number"},
            {"key": "interactions", "label": "Interazioni", "value": 1284, "change": 18.1, "format": "number"},
            {"key": "site_visits", "label": "Visite sito", "value": 2396, "change": 23.0, "format": "number"},
            {"key": "leads", "label": "Lead", "value": 42, "change": 9.8, "format": "number"},
        ],
        "trend": _trend(30),
        "sources": [
            {"name": "Google Search", "visits": 1018, "leads": 19},
            {"name": "Google Business", "visits": 493, "leads": 11},
            {"name": "Facebook", "visits": 417, "leads": 7},
            {"name": "Diretto", "visits": 306, "leads": 4},
            {"name": "Altro", "visits": 162, "leads": 1},
        ],
        "funnel": [
            {"label": "Impression", "value": 18640},
            {"label": "Visite", "value": 2396},
            {"label": "Azioni", "value": 311},
            {"label": "Lead", "value": 42},
        ],
        "top_content": [
            {"title": "Ristrutturazione bagno Trieste", "type": "Pagina", "views": 684, "leads": 14},
            {"title": "Posa piastrelle su piastrelle", "type": "Articolo", "views": 451, "leads": 8},
            {"title": "Reel: preparazione fondo", "type": "Facebook", "views": 3980, "leads": 6},
            {"title": "Cartongesso a Trieste", "type": "Pagina", "views": 289, "leads": 5},
        ],
        "insights": [
            {
                "severity": "positive",
                "title": "Google porta i lead più qualificati",
                "text": "Search + Business generano la maggior parte dei lead del periodo demo.",
            },
            {
                "severity": "info",
                "title": "Il contenuto bagno converte bene",
                "text": "La pagina bagno è il contenuto con più lead attribuiti nel dataset demo.",
            },
            {
                "severity": "warning",
                "title": "Connettori reali non configurati",
                "text": "Collega le API per sostituire i dati demo con metriche reali.",
            },
        ],
    }
