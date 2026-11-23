"""Which AI providers an app's jobs run on: the app's own API key for a provider when it has one
(App settings → Provider API keys), the server's key from .env otherwise."""

from __future__ import annotations

from uuid import UUID

from creative.apps.service import AppService
from creative.providers.base import Provider
from creative.providers.registry import ProviderRegistry


class AppProviders:
    def __init__(self, registry: ProviderRegistry, apps: AppService):
        self.registry = registry
        self.apps = apps

    async def all(self, app_id: UUID | None) -> dict[str, Provider]:
        """Every provider the app can use, by name."""
        return self.registry.for_keys(await self.apps.provider_keys(app_id))

    async def get(self, app_id: UUID | None, name: str) -> Provider | None:
        keys = await self.apps.provider_keys(app_id)
        if name in keys:
            keyed = self.registry.keyed(name, keys[name])
            if keyed is not None:
                return keyed
        return self.registry.get(name)

    async def sources(self, app_id: UUID | None) -> dict[str, str]:
        """For the console: per provider, whose key the app's jobs use, "app" or "server"."""
        keys = await self.apps.provider_keys(app_id)
        out = {name: "server" for name in self.registry.providers if name != "fake"}
        out.update({name: "app" for name in keys})
        return out
