"""Real provider calls; they cost money. Run with keys set: `uv run pytest -m smoke tests/smoke`.
Each test skips when its provider key isn't set."""

import os

import httpx
import pytest

from studio.config import Settings
from studio.providers.base import GenerationRequest, InputImage, MediaType
from studio.providers.registry import ProviderRegistry
from tests.conftest import image_bytes

pytestmark = pytest.mark.smoke


@pytest.fixture
async def registry(tmp_path):
    async with httpx.AsyncClient() as http:
        reg = ProviderRegistry.from_settings(Settings(), http, tmp_path)
        yield reg
        await reg.aclose()


@pytest.fixture
def photo(tmp_path) -> InputImage:
    p = tmp_path / "photo.jpg"
    p.write_bytes(image_bytes((768, 1024), color=(90, 140, 200)))
    return InputImage(p, "image/jpeg", 768, 1024)


def need(registry, name):
    p = registry.get(name)
    if p is None:
        pytest.skip(f"{name} key not set")
    return p


def req(model, **kw):
    return GenerationRequest(
        job_id="smoke",
        prompt="a red bicycle on a beach, watercolor",
        model=model,
        media_type=kw.pop("media_type", MediaType.IMAGE),
        **kw,
    )


@pytest.mark.parametrize("name", ["gemini", "openai", "fal", "openrouter"])
async def test_text_to_image(registry, name):
    p = need(registry, name)
    out = await p.generate_image(req(p.capabilities.default_image_model))
    assert out and out[0].content


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("gemini", None),
        ("openai", None),
        ("fal", "fal-ai/flux-pro/kontext"),
        ("fal", "fal-ai/nano-banana/edit"),
        ("openrouter", None),
    ],
)
async def test_image_input(registry, photo, name, model):
    p = need(registry, name)
    r = req(model or p.capabilities.image_input_models[0], aspect_ratio=None, input_images=[photo])
    p.validate(r)
    out = await p.generate_image(r)
    assert out and out[0].content


@pytest.mark.skipif(not os.environ.get("SMOKE_VIDEO"), reason="video is slow and costly; set SMOKE_VIDEO=1")
@pytest.mark.parametrize("name", ["gemini", "fal"])
async def test_text_to_video(registry, name):
    p = need(registry, name)
    out = await p.generate_video(
        req(
            p.capabilities.default_video_model,
            media_type=MediaType.VIDEO,
            aspect_ratio="16:9",
            duration_seconds=6 if name == "gemini" else 5,
        )
    )
    assert out.content
