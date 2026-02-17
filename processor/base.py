"""Base processor: process(items) -> processed list."""
from abc import ABC, abstractmethod


class BaseProcessor(ABC):
    @abstractmethod
    def process(self, context: dict) -> None:
        """Process context['updates'] in place or replace. Input/output via context."""
        raise NotImplementedError
