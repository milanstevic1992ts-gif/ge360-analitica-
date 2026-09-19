"""Tipi di evento del tracker GE360 e loro significato."""

# Azioni di contatto: sono le uniche che contano come "interazioni" o conversioni.
CONVERSION_EVENTS = (
    "whatsapp_click",
    "phone_click",
    "form_submit",
    "email_click",
    "cta_click",
)

# Contatti diretti (senza CTA generiche): usati per i percorsi verso il lead.
CONTACT_EVENTS = ("whatsapp_click", "phone_click", "form_submit", "email_click")

# Segnali di comportamento: utili all'analisi, mai conteggiati come conversioni.
BEHAVIOR_EVENTS = (
    "scroll_depth",
    "page_engagement",
    "form_start",
    "outbound_click",
    "file_download",
    "rage_click",
    "web_vital",
    "page_404",
)


def sql_list(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


CONVERSION_SQL = sql_list(CONVERSION_EVENTS)
CONTACT_SQL = sql_list(CONTACT_EVENTS)
