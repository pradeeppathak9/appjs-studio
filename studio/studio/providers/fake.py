"""Deterministic provider for tests and local runs. Prompt keywords:
FAIL_TRANSIENT       every attempt fails with a retryable error
FAIL_TRANSIENT:<k>   the first k attempts of a job fail, then it succeeds
FAIL_POLICY          fails with content_policy (never retried)
SLEEP:<seconds>      waits before answering
Image inputs are flipped and tinted so tests can tell the output from the input.
Video comes back as an animated GIF (no ffmpeg needed)."""

import asyncio
import hashlib
import io
import re
from collections import Counter

from PIL import Image, ImageDraw, ImageOps

from studio.providers.base import (
    GeneratedAsset,
    GenerationRequest,
    Provider,
    ProviderCapabilities,
    ProviderContentPolicyError,
    ProviderUnavailableError,
)

RATIOS = ("1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16")
_calls: Counter[str] = Counter()


def _size(ratio: str, base: int = 256) -> tuple[int, int]:
    a, b = (int(x) for x in ratio.split(":"))
    return (base, round(base * b / a)) if a >= b else (round(base * a / b), base)


def _color(seed: str) -> tuple[int, int, int]:
    h = hashlib.sha256(seed.encode()).digest()
    return h[0], h[1], h[2]


class FakeProvider(Provider):
    capabilities = ProviderCapabilities(
        name="fake",
        image=True,
        video=True,
        default_image_model="fake-image-1",
        default_video_model="fake-video-1",
        known_image_models=("fake-image-1", "fake-image-2"),
        known_video_models=("fake-video-1",),
        max_images=4,
        image_aspect_ratios=RATIOS,
        video_aspect_ratios=("16:9", "9:16"),
        video_durations=(2, 4),
        supports_negative_prompt=True,
        supports_seed=True,
        image_input=True,
        image_input_models=("fake-image-1", "fake-image-2"),
        max_input_images=4,
    )

    async def _behave(self, req: GenerationRequest) -> None:
        _calls[req.job_id] += 1
        if m := re.search(r"SLEEP:(\d+(?:\.\d+)?)", req.prompt):
            await asyncio.sleep(float(m.group(1)))
        if "FAIL_POLICY" in req.prompt:
            raise ProviderContentPolicyError("fake: prompt rejected by policy")
        if m := re.search(r"FAIL_TRANSIENT(?::(\d+))?", req.prompt):
            limit = int(m.group(1)) if m.group(1) else None
            if limit is None or _calls[req.job_id] <= limit:
                raise ProviderUnavailableError(f"fake: transient failure #{_calls[req.job_id]}")

    def _image(self, req: GenerationRequest, i: int) -> GeneratedAsset:
        ratio = self.resolved_aspect_ratio(req)
        size = _size(ratio)
        seed = f"{req.model}|{req.prompt}|{req.seed}|{i}"
        if req.input_images:
            with Image.open(req.input_images[0].path) as src:
                img = ImageOps.fit(ImageOps.mirror(src.convert("RGB")), size)
            tint = Image.new("RGB", size, _color(seed))
            img = Image.blend(img, tint, 0.35)
        else:
            img = Image.new("RGB", size, _color(seed))
        ImageDraw.Draw(img).text((8, 8), f"fake #{i}", fill=(255, 255, 255))
        out = io.BytesIO()
        img.save(out, "PNG")
        return GeneratedAsset(out.getvalue(), "image/png", size[0], size[1], metadata={"fake": True})

    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]:
        await self._behave(req)
        return [self._image(req, i) for i in range(req.n)]

    async def generate_video(self, req: GenerationRequest) -> GeneratedAsset:
        await self._behave(req)
        size = _size(self.resolved_aspect_ratio(req), 160)
        frames = [Image.new("RGB", size, _color(f"{req.prompt}|{f}")) for f in range(8)]
        out = io.BytesIO()
        frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=250, loop=0)
        duration = float(req.duration_seconds or 2)
        return GeneratedAsset(out.getvalue(), "image/gif", size[0], size[1], duration, {"fake": True})
