"""Google Gemini via the Interactions API (google-genai >= 2.x, `client.aio.interactions.create`).

Input is a list of content blocks: the images first, then the prompt text. Image output comes back
as `interaction.output_image` (base64 `data` + `mime_type`), video as `interaction.output_video`."""

import asyncio
import base64

from google import genai

from studio.media.images import image_size
from studio.providers.base import (
    GeneratedAsset,
    GenerationRequest,
    MediaType,
    Provider,
    ProviderCapabilities,
    ProviderInvalidRequestError,
)
from studio.providers.errors import translate

IMAGE_MODELS = (
    "gemini-nano-banana-2.1",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-3-pro-image",
)
VIDEO_MODELS = ("gemini-omni-1.1-flash",)


class GeminiProvider(Provider):
    capabilities = ProviderCapabilities(
        name="gemini",
        image=True,
        video=True,
        default_image_model="gemini-nano-banana-2.1",
        default_video_model="gemini-omni-1.1-flash",
        known_image_models=IMAGE_MODELS,
        known_video_models=VIDEO_MODELS,
        max_images=4,
        image_aspect_ratios=("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"),
        video_aspect_ratios=("16:9", "9:16"),
        video_durations=(),  # any; sent as "<n>s" (format to confirm with a real key)
        image_input=True,
        image_input_models=IMAGE_MODELS,
        max_input_images=4,
    )

    def __init__(self, api_key: str, client: genai.Client | None = None):
        self.client = client or genai.Client(api_key=api_key)

    def build_arguments(self, req: GenerationRequest) -> dict:
        blocks: list[dict] = [
            {
                "type": "image",
                "data": base64.b64encode(img.path.read_bytes()).decode(),
                "mime_type": img.mime_type,
            }
            for img in req.input_images
        ]
        blocks.append({"type": "text", "text": self.fold_negative(req.prompt, req.negative_prompt)})
        ratio = self.resolved_aspect_ratio(req)
        if req.media_type == MediaType.IMAGE:
            fmt: dict = {"type": "image", "aspect_ratio": ratio, "image_size": "1K"}
        else:
            fmt = {"type": "video", "aspect_ratio": ratio, "resolution": "720p"}
            if req.duration_seconds:
                fmt["duration"] = f"{req.duration_seconds}s"
        return {"model": req.model, "input": blocks, "response_format": fmt}

    async def _create(self, args: dict):
        try:
            return await self.client.aio.interactions.create(**args)
        except Exception as e:
            raise translate(e, "gemini") from e

    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]:
        args = self.build_arguments(req)
        # The Interactions API has no `n`: one call per image.
        results = await asyncio.gather(*(self._create(args) for _ in range(req.n)), return_exceptions=True)
        assets, errors = [], []
        for r in results:
            if isinstance(r, BaseException):
                errors.append(r)
                continue
            out = r.output_image
            if out is None or not out.data:
                errors.append(ProviderInvalidRequestError("gemini: response had no image"))
                continue
            data = base64.b64decode(out.data)
            w, h = image_size(data) or (None, None)
            assets.append(GeneratedAsset(data, out.mime_type or "image/jpeg", w, h))
        if not assets:
            raise errors[0]
        return assets

    async def generate_video(self, req: GenerationRequest) -> GeneratedAsset:
        r = await self._create(self.build_arguments(req))
        out = r.output_video
        if out is None or not getattr(out, "data", None):
            raise ProviderInvalidRequestError("gemini: response had no video")
        return GeneratedAsset(
            base64.b64decode(out.data),
            getattr(out, "mime_type", None) or "video/mp4",
            duration_seconds=float(req.duration_seconds) if req.duration_seconds else None,
        )
