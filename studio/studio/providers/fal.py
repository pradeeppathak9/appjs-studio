"""fal.ai: queue-based endpoints (`AsyncClient.subscribe`). Outputs are URLs, downloaded here.
Input images are uploaded to fal storage first (`AsyncClient.upload`), then passed by URL.

Which endpoints may be used, and how each takes input images, is set in a YAML file (`fal.yaml`
next to this module, or FAL_MODELS_FILE). Only endpoints with `enabled: true` pass validation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import fal_client
import httpx
from pydantic import BaseModel, Field, model_validator

from studio.providers.base import (
    GeneratedAsset,
    GenerationRequest,
    MediaType,
    Provider,
    ProviderCapabilities,
    ProviderInvalidRequestError,
    UnsupportedRequestError,
)
from studio.providers.errors import translate
from studio.providers.model_config import CONFIG_DIR, check_aspect_ratios, check_unique, load_yaml_config

DEFAULT_CONFIG_PATH = CONFIG_DIR / "fal.yaml"
FLUX_SIZES = {
    "1:1": "square_hd",
    "4:3": "landscape_4_3",
    "16:9": "landscape_16_9",
    "3:4": "portrait_4_3",
    "9:16": "portrait_16_9",
}


# ---- config ------------------------------------------------------------------------------------


class FalInput(BaseModel, extra="forbid"):
    param: str = Field(min_length=1)
    list: bool = False
    max: int = Field(default=1, ge=1)


class FalModel(BaseModel, extra="forbid"):
    id: str = Field(min_length=1)
    media: Literal["image", "video"]
    enabled: bool = True
    label: str | None = None
    size_param: Literal["image_size", "aspect_ratio"] = "image_size"
    input: FalInput | None = None


class FalConfig(BaseModel, extra="forbid"):
    default_image_model: str | None = None
    default_video_model: str | None = None
    max_images: int = Field(default=4, ge=1, le=10)
    image_aspect_ratios: list[str] = Field(default_factory=lambda: list(FLUX_SIZES), min_length=1)
    video_aspect_ratios: list[str] = Field(default_factory=lambda: ["16:9", "9:16", "1:1"])
    video_durations: list[int] = Field(default_factory=list)
    models: list[FalModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> FalConfig:
        check_unique([m.id for m in self.models])
        check_aspect_ratios(self.image_aspect_ratios + self.video_aspect_ratios)
        for m in self.enabled("image"):
            if m.size_param == "image_size":
                missing = [r for r in self.image_aspect_ratios if r not in FLUX_SIZES]
                if missing:
                    raise ValueError(
                        f"{m.id} uses size_param image_size, which has no preset for {', '.join(missing)}"
                    )
            if m.input is not None and m.input.list is False and m.input.max != 1:
                raise ValueError(f"{m.id}: input.max must be 1 when input.list is false")
        for media in ("image", "video"):
            key = f"default_{media}_model"
            ids = [m.id for m in self.enabled(media)]
            default = getattr(self, key)
            if default is not None and default not in ids:
                raise ValueError(f"{key} {default!r} is not an enabled {media} model")
            if default is None and ids:
                setattr(self, key, ids[0])
        return self

    def enabled(self, media: str) -> list[FalModel]:
        return [m for m in self.models if m.enabled and m.media == media]

    def model(self, model_id: str, media: str) -> FalModel | None:
        return next((m for m in self.enabled(media) if m.id == model_id), None)


def load_config(path: Path | None = None) -> FalConfig:
    return load_yaml_config(FalConfig, path or DEFAULT_CONFIG_PATH)


# ---- provider ----------------------------------------------------------------------------------


class FalProvider(Provider):
    def __init__(
        self,
        api_key: str,
        http: httpx.AsyncClient,
        client: fal_client.AsyncClient | None = None,
        config: FalConfig | None = None,
    ):
        config = config or load_config()
        images, videos = config.enabled("image"), config.enabled("video")
        if not images and not videos:
            raise ValueError("fal config has no enabled models")
        self.config = config
        self.client = client or fal_client.AsyncClient(key=api_key)
        self.http = http
        self.temp_dir: Path | None = None
        inputs = [m for m in images if m.input is not None]
        self.capabilities = ProviderCapabilities(
            name="fal",
            image=bool(images),
            video=bool(videos),
            default_image_model=config.default_image_model,
            default_video_model=config.default_video_model,
            known_image_models=tuple(m.id for m in images),
            known_video_models=tuple(m.id for m in videos),
            max_images=config.max_images,
            image_aspect_ratios=tuple(config.image_aspect_ratios),
            video_aspect_ratios=tuple(config.video_aspect_ratios),
            video_durations=tuple(config.video_durations),
            supports_negative_prompt=False,
            supports_seed=True,
            image_input=bool(inputs),
            image_input_models=tuple(m.id for m in inputs),
            max_input_images=max((m.input.max for m in inputs if m.input), default=0),
        )

    def validate(self, req: GenerationRequest) -> None:
        super().validate(req)
        model = self.config.model(req.model, req.media_type.value)
        if model is None:
            allowed = ", ".join(m.id for m in self.config.enabled(req.media_type.value))
            raise UnsupportedRequestError(
                f"fal {req.media_type.value} endpoint {req.model!r} is not enabled (enabled: {allowed})",
                "model",
            )
        if req.input_images:
            if model.input is None:
                raise UnsupportedRequestError(
                    f"fal endpoint {req.model} is not set up for input images", "model"
                )
            if len(req.input_images) > model.input.max:
                raise UnsupportedRequestError(
                    f"{req.model} takes at most {model.input.max} input images", "inputs"
                )

    async def build_arguments(self, req: GenerationRequest) -> dict:
        ratio = self.resolved_aspect_ratio(req)
        if req.media_type == MediaType.VIDEO:
            args: dict = {"prompt": req.prompt, "aspect_ratio": ratio}
            if req.duration_seconds:
                args["duration"] = str(req.duration_seconds)
            if req.negative_prompt:
                args["negative_prompt"] = req.negative_prompt
            return args
        model = self.config.model(req.model, "image")
        if model is None:
            raise ProviderInvalidRequestError(f"fal image endpoint {req.model!r} is not enabled")
        args = {
            "prompt": self.fold_negative(req.prompt, req.negative_prompt),
            "num_images": req.n,
            "output_format": "png",
        }
        if model.size_param == "aspect_ratio":
            args["aspect_ratio"] = ratio
        else:
            args["image_size"] = FLUX_SIZES[ratio]
        if req.seed is not None:
            args["seed"] = req.seed
        if req.input_images:
            if model.input is None:
                raise ProviderInvalidRequestError(f"fal endpoint {req.model} is not set up for input images")
            urls = [await self.client.upload(i.path.read_bytes(), i.mime_type) for i in req.input_images]
            args[model.input.param] = urls if model.input.list else urls[0]
        return args

    async def _run(self, req: GenerationRequest) -> dict:
        try:
            return await self.client.subscribe(req.model, arguments=await self.build_arguments(req))
        except Exception as e:
            raise translate(e, "fal") from e

    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]:
        result = await self._run(req)
        assets = []
        for img in result.get("images") or []:
            try:
                resp = await self.http.get(img["url"], timeout=60)
                resp.raise_for_status()
            except Exception as e:
                raise translate(e, "fal download") from e
            mime = img.get("content_type") or resp.headers.get("content-type", "image/png")
            assets.append(GeneratedAsset(resp.content, mime, img.get("width"), img.get("height")))
        if not assets:
            raise ProviderInvalidRequestError("fal: response had no images")
        return assets

    async def generate_video(self, req: GenerationRequest) -> GeneratedAsset:
        result = await self._run(req)
        video = result.get("video") or {}
        if not video.get("url"):
            raise ProviderInvalidRequestError("fal: response had no video")
        assert self.temp_dir is not None, "temp_dir is set by the registry"
        dest = self.temp_dir / f"{req.job_id}.mp4.download"
        try:
            async with self.http.stream("GET", video["url"], timeout=300) as resp:
                resp.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1 << 20):
                        f.write(chunk)
        except Exception as e:
            dest.unlink(missing_ok=True)
            raise translate(e, "fal download") from e
        return GeneratedAsset(
            dest,
            video.get("content_type") or "video/mp4",
            duration_seconds=float(req.duration_seconds) if req.duration_seconds else None,
        )
