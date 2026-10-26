from abc import ABC, abstractmethod
from typing import Iterator
from ..models import RawDocument


class Connector(ABC):
    """Every intake channel implements fetch() and yields RawDocument objects.
    The pipeline never cares where a file came from."""
    name: str = "base"

    @abstractmethod
    def fetch(self) -> Iterator[RawDocument]:
        ...
