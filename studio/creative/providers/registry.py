from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from creative.config import Settings
from creative.providers.base import MediaType, Provider, UnsupportedRequestError

ORDER = ("gemini", "openai", "fal", "openrouter", "fake")


class UnknownProviderError(UnsupportedRequestError):
    pass


class NoProviderAvailableError(Exception):
    pass


@dataclass
class Resolved:
    provider: Provider
    model: str


# A provider built for one app's own key; at most this many are kept (oldest closed first).
KEYED_CACHE_SIZE = 64
KEYED = ("gemini", "openai", "fal", "openrouter")  # providers an app can bring its own key for

ProviderFactory = Callable[[str, str], Provider | None]


def make_factory(settings: Settings, http: httpx.AsyncClient, temp_dir: Path) -> ProviderFactory:
    """`factory(name, api_key)` builds a provider the same way for the server's key and an app's."""

    def factory(name: str, api_key: str) -> Provider | None:
        if name == "gemini":
            from creative.providers.gemini import GeminiProvider

            return GeminiProvider(api_key)
        if name == "openai":
            from creative.providers.openai_images import OpenAIImagesProvider

            return OpenAIImagesProvider(api_key)
        if name == "fal":
            from creative.providers import fal as fal_module

            config = fal_module.load_config(settings.fal_models_file)
            fal = fal_module.FalProvider(api_key, http, config=config)
            fal.temp_dir = temp_dir
            return fal
        if name == "openrouter":
            from creative.providers import openrouter

            return openrouter.OpenRouterProvider(
                api_key,
                http,
                openrouter.load_config(settings.openrouter_models_file),
                base_url=settings.openrouter_base_url,
            )
        return None

    return factory


class ProviderRegistry:
    def __init__(
        self,
        providers: dict[str, Provider],
        defaults: dict[MediaType, str | None] | None = None,
        factory: ProviderFactory | None = None,
    ):
        self.providers = providers  # built from the server's keys (.env)
        self.defaults = defaults or {}
        self.factory = factory
        self._keyed: OrderedDict[tuple[str, str], Provider] = OrderedDict()
        # evicted from the cache but maybe still running a job: closed at shutdown, not mid-request
        self._closing: list[Provider] = []

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient, temp_dir: Path) -> ProviderRegistry:
        factory = make_factory(settings, http, temp_dir)
        server_keys = {
            "gemini": settings.google_api_key,
            "openai": settings.openai_api_key,
            "fal": settings.fal_key,
            "openrouter": settings.openrouter_api_key,
        }
        providers: dict[str, Provider] = {}
        for name, key in server_keys.items():
            if key:
                provider = factory(name, key.get_secret_value())
                if provider is not None:
                    providers[name] = provider
        if settings.enable_fake_provider:
            from creative.providers.fake import FakeProvider

            providers["fake"] = FakeProvider()
        return cls(
            providers,
            {
                MediaType.IMAGE: settings.default_image_provider,
                MediaType.VIDEO: settings.default_video_provider,
            },
            factory,
        )

    def keyed(self, name: str, api_key: str) -> Provider | None:
        """The provider `name` using `api_key` (an app's own key), built once and reused."""
        if self.factory is None or name not in KEYED:
            return None
        cache_key = (name, hashlib.sha256(api_key.encode()).hexdigest())
        provider = self._keyed.get(cache_key)
        if provider is None:
            provider = self.factory(name, api_key)
            if provider is None:
                return None
            self._keyed[cache_key] = provider
            while len(self._keyed) > KEYED_CACHE_SIZE:
                _, old = self._keyed.popitem(last=False)
                self._closing.append(old)
        else:
            self._keyed.move_to_end(cache_key)
        return provider

    def for_keys(self, app_keys: dict[str, str]) -> dict[str, Provider]:
        """Every provider an app can use: its own key where it has one, the server's otherwise."""
        out = dict(self.providers)
        for name, key in app_keys.items():
            provider = self.keyed(name, key)
            if provider is not None:
                out[name] = provider
        return out

    def get(self, name: str) -> Provider | None:
        return self.providers.get(name)

    def list(self) -> list[Provider]:
        return [self.providers[n] for n in ORDER if n in self.providers]

    def resolve(
        self,
        media_type: MediaType,
        provider: str | None,
        model: str | None,
        providers: dict[str, Provider] | None = None,
    ) -> Resolved:
        """Pick the provider and model for a request. `providers` is the set to choose from (an app's,
        from `for_keys`); the server's own by default."""
        available = self.providers if providers is None else providers
        if provider:
            p = available.get(provider)
            if p is None:
                configured = ", ".join(available) or "none"
                raise UnknownProviderError(
                    f"provider {provider!r} is not configured (configured: {configured})", "provider"
                )
            if not getattr(p.capabilities, media_type.value):
                raise UnsupportedRequestError(
                    f"{provider} does not generate {media_type.value}", "media_type"
                )
        else:
            default = self.defaults.get(media_type)
            p = available.get(default) if default else None
            if p is None or not getattr(p.capabilities, media_type.value):
                ordered = [available[n] for n in ORDER if n in available]
                p = next((x for x in ordered if getattr(x.capabilities, media_type.value)), None)
            if p is None:
                raise NoProviderAvailableError(f"no configured provider generates {media_type.value}")
        caps = p.capabilities
        default_model = (
            caps.default_image_model if media_type == MediaType.IMAGE else caps.default_video_model
        )
        return Resolved(p, model or default_model or "")

    async def aclose(self) -> None:
        for p in [*self.providers.values(), *self._keyed.values(), *self._closing]:
            await p.aclose()
        self._keyed.clear()
        self._closing.clear()
