"""Provider router — resolves the active LLM provider from settings."""

from backend.config import ProviderSettings, get_logger
from backend.providers.base import LLMProvider
from backend.providers.ollama import OllamaProvider

log = get_logger(__name__)

_FACTORIES: dict[str, type] = {
    "ollama": OllamaProvider,
}


class ProviderRouter:
    def __init__(self, settings: ProviderSettings) -> None:
        self._settings = settings
        self._provider: LLMProvider | None = None

    def get(self) -> LLMProvider:
        """Return the currently active provider, creating it on first call."""
        if self._provider is None:
            self._provider = self._create(self._settings.active)
        return self._provider

    async def switch(self, name: str) -> LLMProvider:
        """Switch to a different provider, closing the current one."""
        if self._provider is not None:
            await self.close()
        self._settings.active = name
        self._provider = self._create(name)
        log.info("Switched provider to %s", name)
        return self._provider

    def _create(self, name: str) -> LLMProvider:
        if name not in _FACTORIES:
            raise ValueError(
                f"Unknown provider '{name}'. Available: {list(_FACTORIES.keys())}"
            )
        # Get provider-specific settings
        provider_settings = getattr(self._settings, name)
        log.info("Creating provider: %s", name)
        return _FACTORIES[name](provider_settings)

    async def close(self) -> None:
        if self._provider is not None and hasattr(self._provider, "close"):
            await self._provider.close()
        self._provider = None
