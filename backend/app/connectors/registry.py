import os
from dataclasses import dataclass

from .wordpress import WordPressConnector


@dataclass
class ConnectorDiagnostic:
    provider: str
    configured: bool
    implementation: str
    required_env: list[str]


def diagnostics() -> list[ConnectorDiagnostic]:
    wordpress = WordPressConnector()

    return [
        ConnectorDiagnostic(
            provider="wordpress",
            configured=wordpress.configured(),
            implementation="active",
            required_env=["WORDPRESS_BASE_URL"],
        ),
        ConnectorDiagnostic(
            provider="meta",
            configured=bool(os.getenv("META_PAGE_ACCESS_TOKEN") and os.getenv("META_PAGE_ID")),
            implementation="scaffold",
            required_env=["META_PAGE_ACCESS_TOKEN", "META_PAGE_ID"],
        ),
        ConnectorDiagnostic(
            provider="google_business",
            configured=bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
            implementation="scaffold",
            required_env=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_BUSINESS_ACCOUNT_ID"],
        ),
        ConnectorDiagnostic(
            provider="ga4",
            configured=bool(os.getenv("GA4_PROPERTY_ID") and os.getenv("GOOGLE_CLIENT_ID")),
            implementation="scaffold",
            required_env=["GA4_PROPERTY_ID", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        ),
        ConnectorDiagnostic(
            provider="search_console",
            configured=bool(os.getenv("SEARCH_CONSOLE_SITE_URL") and os.getenv("GOOGLE_CLIENT_ID")),
            implementation="scaffold",
            required_env=["SEARCH_CONSOLE_SITE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        ),
    ]
