"""OpenRouter: image generation through the chat completions API (`POST /chat/completions` with
`modalities`). Input images go in as data-URL `image_url` content parts before the prompt text.
Generated images come back in `choices[0].message.images[].image_url.url` as data URLs (or plain
URLs, which are downloaded). One image per call, so `n` > 1 makes parallel calls.

Which models may be used is set in a YAML file (`openrouter.yaml` next to this module, or
OPENROUTER_MODELS_FILE). Only models with `enabled: true` pass validation."""

from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from studio.media.images import image_size
from studio.providers.base import (
    GeneratedAsset,
    GenerationRequest,
    Provider,
    ProviderCapabilities,
    ProviderContentPolicyError,
    ProviderError,
    ProviderInvalidRequestError,
    UnsupportedRequestError,
)
from studio.providers.errors import translate
from studio.providers.model_config import CONFIG_DIR, check_aspect_ratios, check_unique, load_yaml_config

DEFAULT_CONFIG_PATH = CONFIG_DIR / "openrouter.yaml"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
POLICY_FINISH_REASONS = ("content_filter", "safety", "prohibited_content", "image_safety", "blocklist")


# ---- config ------------------------------------------------------------------------------------


class OpenRouterModel(BaseModel, extra="forbid"):
    id: str = Field(min_length=1)
    enabled: bool = True
    label: str | None = None
    modalities: list[Literal["image", "text"]] = Field(default_factory=lambda: ["image", "text"])
    image_input: bool = False
    max_input_images: int = Field(default=4, ge=0)
    aspect_ratio: bool = True

    @model_validator(mode="after")
    def _outputs_images(self) -> OpenRouterModel:
        if "image" not in self.modalities:
            raise ValueError(f"model {self.id}: modalities must include 'image'")
        return self


class OpenRouterConfig(BaseModel, extra="forbid"):
    default_model: str | None = None
    max_images: int = Field(default=4, ge=1, le=10)
    aspect_ratios: list[str] = Field(default_factory=lambda: ["1:1"], min_length=1)
    models: list[OpenRouterModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> OpenRouterConfig:
        check_unique([m.id for m in self.models])
        check_aspect_ratios(self.aspect_ratios)
        enabled = self.enabled_ids
        if self.default_model is not None and self.default_model not in enabled:
            raise ValueError(f"default_model {self.default_model!r} is not an enabled model")
        if self.default_model is None and enabled:
            self.default_model = enabled[0]
        return self

    @property
    def enabled_models(self) -> list[OpenRouterModel]:
        return [m for m in self.models if m.enabled]

    @property
    def enabled_ids(self) -> list[str]:
        return [m.id for m in self.enabled_models]

    def model(self, model_id: str) -> OpenRouterModel | None:
        return next((m for m in self.enabled_models if m.id == model_id), None)


def load_config(path: Path | None = None) -> OpenRouterConfig:
    return load_yaml_config(OpenRouterConfig, path or DEFAULT_CONFIG_PATH)


# ---- provider ----------------------------------------------------------------------------------


class OpenRouterProvider(Provider):
    def __init__(
        self,
        api_key: str,
        http: httpx.AsyncClient,
        config: OpenRouterConfig | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 170,
    ):
        config = config or load_config()
        if not config.enabled_models:
            raise ValueError("openrouter config has no enabled models")
        self.api_key = api_key
        self.http = http
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        enabled = config.enabled_models
        input_models = tuple(m.id for m in enabled if m.image_input)
        self.capabilities = ProviderCapabilities(
            name="openrouter",
            image=True,
            video=False,
            default_image_model=config.default_model,
            known_image_models=tuple(m.id for m in enabled),
            max_images=config.max_images,
            image_aspect_ratios=tuple(config.aspect_ratios),
            image_input=bool(input_models),
            image_input_models=input_models,
            max_input_images=max((m.max_input_images for m in enabled if m.image_input), default=0),
        )

    def validate(self, req: GenerationRequest) -> None:
        super().validate(req)
        model = self.config.model(req.model)
        if model is None:
            allowed = ", ".join(self.config.enabled_ids)
            raise UnsupportedRequestError(
                f"openrouter model {req.model!r} is not enabled (enabled: {allowed})", "model"
            )
        if req.input_images:
            if not model.image_input:
                raise UnsupportedRequestError(f"{req.model} does not take input images", "model")
            if len(req.input_images) > model.max_input_images:
                raise UnsupportedRequestError(
                    f"{req.model} takes at most {model.max_input_images} input images", "inputs"
                )

    def build_payload(self, req: GenerationRequest) -> dict:
        model = self.config.model(req.model)
        if model is None:
            raise ProviderInvalidRequestError(f"openrouter model {req.model!r} is not enabled")
        content: list[dict] = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.mime_type};base64," + base64.b64encode(img.path.read_bytes()).decode()
                },
            }
            for img in req.input_images
        ]
        content.append({"type": "text", "text": self.fold_negative(req.prompt, req.negative_prompt)})
        payload: dict = {
            "model": req.model,
            "messages": [{"role": "user", "content": content}],
            "modalities": list(model.modalities),
        }
        if model.aspect_ratio:
            payload["image_config"] = {"aspect_ratio": self.resolved_aspect_ratio(req)}
        if req.seed is not None:
            payload["seed"] = req.seed
        return payload

    async def _complete(self, payload: dict) -> dict:
        try:
            resp = await self.http.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Title": "AppJs Studio",
                },
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            raise translate(e, "openrouter") from e
        # Upstream failures can arrive as HTTP 200 with an `error` object.
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            code = err.get("code") if isinstance(err, dict) else None
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise translate(_StatusError(f"{message}", code if isinstance(code, int) else None), "openrouter")
        return body

    async def _decode(self, url: str) -> tuple[bytes, str]:
        if url.startswith("data:"):
            header, _, data = url.partition(",")
            mime = header[5:].split(";")[0] or "image/png"
            try:
                return base64.b64decode(data), mime
            except (binascii.Error, ValueError) as e:
                raise ProviderInvalidRequestError("openrouter: image was not valid base64") from e
        try:
            resp = await self.http.get(url, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            raise translate(e, "openrouter download") from e
        return resp.content, resp.headers.get("content-type", "image/png").split(";")[0]

    async def _one(self, payload: dict) -> GeneratedAsset:
        body = await self._complete(payload)
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        images = message.get("images") or []
        if not images:
            reasons = f"{choice.get('finish_reason')} {choice.get('native_finish_reason')}".lower()
            text = (message.get("content") or message.get("refusal") or "")[:300]
            detail = f"openrouter: response had no image ({text or reasons.strip()})"
            if any(r in reasons for r in POLICY_FINISH_REASONS):
                raise ProviderContentPolicyError(detail)
            raise ProviderInvalidRequestError(detail)
        url = (images[0].get("image_url") or {}).get("url") or ""
        data, mime = await self._decode(url)
        w, h = image_size(data) or (None, None)
        return GeneratedAsset(data, mime, w, h, metadata={"openrouter_id": body.get("id")})

    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]:
        payload = self.build_payload(req)
        results = await asyncio.gather(*(self._one(payload) for _ in range(req.n)), return_exceptions=True)
        assets = [r for r in results if isinstance(r, GeneratedAsset)]
        if not assets:
            first = next(r for r in results if isinstance(r, BaseException))
            raise first if isinstance(first, ProviderError) else translate(first, "openrouter")
        return assets


class _StatusError(Exception):
    """Carries an in-body error code to `translate`, which reads `status_code`."""

    def __init__(self, message: str, status_code: int | None):
        super().__init__(message)
        self.status_code = status_code
