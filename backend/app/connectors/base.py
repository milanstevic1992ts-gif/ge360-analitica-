from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorResult:
    provider: str
    ok: bool
    metrics: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    content_items: list[dict[str, Any]] = field(default_factory=list)
    # Righe Search Console data+query+pagina+dispositivo (tabella dedicata).
    search_rows: list[dict[str, Any]] = field(default_factory=list)
    # Recensioni (Google Business): tabella dedicata, aggiornate per review_id.
    reviews: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    message: str = ""


class Connector(ABC):
    provider: str

    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        raise NotImplementedError
