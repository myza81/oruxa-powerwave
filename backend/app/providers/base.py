"""Provider abstraction and registry.

Ported near-verbatim from powerwave's app/providers/base/{base_provider,
provider_manager,provider_registry,exceptions}.py (commit 3156392),
consolidated into one module -- the split into four tiny files added no
value here and this project prefers the smaller module count (see
docs/project-memory/MIGRATION_PLAN.md Sec 1, "Reuse classification: A").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.domain import DisturbanceRecord


class ProviderError(Exception):
    """Base class for all provider-layer errors."""


class ProviderNotFoundError(ProviderError):
    """No registered provider is compatible with the given path."""


class ProviderLoadError(ProviderError):
    """A provider raised an unexpected exception during load()."""


class DuplicateProviderError(ProviderError):
    """A provider with the same name is already registered."""


class BaseProvider(ABC):
    """Abstract contract that every ingestion provider must satisfy.

    Providers must remain isolated from API/storage systems. They must
    never return parser-specific structures -- only DisturbanceRecord.
    """

    provider_name: str = "base"

    @abstractmethod
    def can_load(self, path: Path) -> bool:
        """Return True if this provider can handle the given file path."""

    @abstractmethod
    def load(self, path: Path) -> DisturbanceRecord:
        """Parse the file at *path* and return a normalized DisturbanceRecord."""


class ProviderRegistry:
    """Ordered collection of registered providers.

    Maintains insertion order so that find() returns the first compatible
    provider in registration sequence -- enabling priority-based resolution.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        if provider.provider_name in self._providers:
            raise DuplicateProviderError(
                f"Provider '{provider.provider_name}' is already registered."
            )
        self._providers[provider.provider_name] = provider

    def unregister(self, name: str) -> None:
        if name not in self._providers:
            raise ProviderError(f"Provider '{name}' is not registered.")
        del self._providers[name]

    def find(self, path: Path) -> BaseProvider | None:
        for provider in self._providers.values():
            if provider.can_load(path):
                return provider
        return None

    def names(self) -> list[str]:
        return list(self._providers.keys())

    def get_all(self) -> list[BaseProvider]:
        return list(self._providers.values())

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, name: str) -> bool:
        return name in self._providers


class ProviderManager:
    """Orchestrates provider registration, discovery, and file loading.

    Provider discovery follows insertion order -- the first registered
    provider whose can_load() returns True is selected.
    """

    def __init__(self) -> None:
        self._registry = ProviderRegistry()

    def register_provider(self, provider: BaseProvider) -> None:
        if not isinstance(provider, BaseProvider):
            raise ProviderError(
                f"Expected a BaseProvider subclass, got {type(provider).__name__!r}."
            )
        self._registry.register(provider)

    def unregister_provider(self, name: str) -> None:
        self._registry.unregister(name)

    def available_providers(self) -> list[str]:
        return self._registry.names()

    def find_provider(self, path: Path) -> BaseProvider:
        provider = self._registry.find(path)
        if provider is None:
            raise ProviderNotFoundError(
                f"No registered provider can load '{path}'. "
                f"Registered providers: {self.available_providers()}"
            )
        return provider

    def load(self, path: Path) -> DisturbanceRecord:
        """Discover the compatible provider and return a DisturbanceRecord.

        Raises:
            ProviderNotFoundError: if no provider is compatible with *path*.
            ProviderLoadError: if the selected provider raises during load().
        """
        provider = self.find_provider(path)
        try:
            return provider.load(path)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderLoadError(
                f"Provider '{provider.provider_name}' failed to load '{path}': {exc}"
            ) from exc
