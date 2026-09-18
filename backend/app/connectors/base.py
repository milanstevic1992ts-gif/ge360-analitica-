from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ConnectorResult:
    provider: str
    ok: bool
    metrics: list[dict[str, Any]]
    events: list[dict[str, Any]]
    message: str = ""


class Connector(ABC):
    provider: str

    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def sync(self) -> ConnectorResult:
        raise NotImplementedError
