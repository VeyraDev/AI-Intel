"""Base collectors: SignalCollector (modify list, no Updates) and ContentCollector (return Update list)."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.update import Update


class BaseCollector(ABC):
    """Base for all collectors."""

    @abstractmethod
    def collect(self, context: dict) -> None:
        """Run collection. Context is shared pipeline state."""
        raise NotImplementedError


class SignalCollector(BaseCollector):
    """Modifies recommendation list (e.g. bloggers.json). Does not return Update list."""

    def collect(self, context: dict) -> None:
        """Override: update bloggers.json or other state; do not append to context['updates']."""
        raise NotImplementedError


class ContentCollector(BaseCollector):
    """Fetches content and returns list of Update for the pipeline."""

    def collect(self, context: dict) -> None:
        """Override: fetch data, append Update objects to context['updates']."""
        raise NotImplementedError
