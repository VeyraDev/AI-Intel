"""Base generator: generate(context) uses context['updates'] and writes reports."""
from abc import ABC, abstractmethod


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, context: dict) -> None:
        """Generate output from context (e.g. updates) and persist via storage."""
        raise NotImplementedError
