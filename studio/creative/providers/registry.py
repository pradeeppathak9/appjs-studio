from __future__ import annotations

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


class ProviderRegistry:
    def __init__(self, providers: dict[str, Provider], defaults: dict[MediaType, str | None] | None = None):
        self.providers = providers
        self.defaults = defaults or {}

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient, temp_dir: Path) -> ProviderRegistry:
        providers: dict[str, Provider] = {}
        if settings.google_api_key:
            from creative.providers.gemini import GeminiProvider

            providers["gemini"] = GeminiProvider(settings.google_api_key.get_secret_value())
        if settings.openai_api_key:
            from creative.providers.openai_images import OpenAIImagesProvider

            providers["openai"] = OpenAIImagesProvider(settings.openai_api_key.get_secret_value())
        if settings.fal_key:
            from creative.providers import fal as fal_module

            fal = fal_module.FalProvider(
                settings.fal_key.get_secret_value(),
                http,
                config=fal_module.load_config(settings.fal_models_file),
            )
            fal.temp_dir = temp_dir
            providers["fal"] = fal
        if settings.openrouter_api_key:
            from creative.providers import openrouter

            providers["openrouter"] = openrouter.OpenRouterProvider(
                settings.openrouter_api_key.get_secret_value(),
                http,
                openrouter.load_config(settings.openrouter_models_file),
                base_url=settings.openrouter_base_url,
            )
        if settings.enable_fake_provider:
            from creative.providers.fake import FakeProvider

            providers["fake"] = FakeProvider()
        return cls(
            providers,
            {
                MediaType.IMAGE: settings.default_image_provider,
                MediaType.VIDEO: settings.default_video_provider,
            },
        )

    def get(self, name: str) -> Provider | None:
        return self.providers.get(name)

    def list(self) -> list[Provider]:
        return [self.providers[n] for n in ORDER if n in self.providers]

    def resolve(self, media_type: MediaType, provider: str | None, model: str | None) -> Resolved:
        if provider:
            p = self.providers.get(provider)
            if p is None:
                configured = ", ".join(self.providers) or "none"
                raise UnknownProviderError(
                    f"provider {provider!r} is not configured (configured: {configured})", "provider"
                )
            if not getattr(p.capabilities, media_type.value):
                raise UnsupportedRequestError(
                    f"{provider} does not generate {media_type.value}", "media_type"
                )
        else:
            default = self.defaults.get(media_type)
            p = self.providers.get(default) if default else None
            if p is None or not getattr(p.capabilities, media_type.value):
                p = next((x for x in self.list() if getattr(x.capabilities, media_type.value)), None)
            if p is None:
                raise NoProviderAvailableError(f"no configured provider generates {media_type.value}")
        caps = p.capabilities
        default_model = (
            caps.default_image_model if media_type == MediaType.IMAGE else caps.default_video_model
        )
        return Resolved(p, model or default_model or "")

    async def aclose(self) -> None:
        for p in self.providers.values():
            await p.aclose()
