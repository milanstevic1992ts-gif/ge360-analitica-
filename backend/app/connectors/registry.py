import os
from dataclasses import dataclass

from .ga4 import GA4Connector
from .google_business import GoogleBusinessConnector
from .meta import MetaConnector
from .search_console import SearchConsoleConnector
from .wordpress import WordPressConnector


@dataclass
class ConnectorDiagnostic:
    provider: str
    configured: bool
    implementation: str
    required_env: list[str]


def diagnostics() -> list[ConnectorDiagnostic]:
    wordpress = WordPressConnector()
    ga4 = GA4Connector()
    search_console = SearchConsoleConnector()
    google_business = GoogleBusinessConnector()
    meta = MetaConnector()

    return [
        ConnectorDiagnostic(
            provider="wordpress",
            configured=wordpress.configured(),
            implementation="active",
            required_env=["WORDPRESS_BASE_URL"],
        ),
        ConnectorDiagnostic(
            provider="meta",
            configured=meta.configured(),
            implementation="active",
            required_env=["META_PAGE_ACCESS_TOKEN", "META_PAGE_ID"],
        ),
        ConnectorDiagnostic(
            provider="google_business",
            configured=google_business.configured(),
            implementation="active",
            required_env=[
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "GOOGLE_REFRESH_TOKEN",
                "GOOGLE_BUSINESS_LOCATION_NAME",
            ],
        ),
        ConnectorDiagnostic(
            provider="ga4",
            configured=ga4.configured(),
            implementation="active",
            required_env=[
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "GOOGLE_REFRESH_TOKEN",
                "GA4_PROPERTY_ID",
            ],
        ),
        ConnectorDiagnostic(
            provider="search_console",
            configured=search_console.configured(),
            implementation="active",
            required_env=[
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "GOOGLE_REFRESH_TOKEN",
                "SEARCH_CONSOLE_SITE_URL",
            ],
        ),
    ]
