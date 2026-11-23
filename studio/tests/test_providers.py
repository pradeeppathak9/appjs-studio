"""Argument mapping and response parsing for each provider, with the SDK clients faked."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

from studio.providers import fal as fal_module
from studio.providers import openrouter
from studio.providers.base import (
    GenerationRequest,
    InputImage,
    MediaType,
    ProviderContentPolicyError,
    ProviderInvalidRequestError,
    ProviderUnavailableError,
    UnsupportedRequestError,
)
from studio.providers.errors import translate
from studio.providers.fake import FakeProvider
from studio.providers.fal import FalProvider
from studio.providers.gemini import GeminiProvider
from studio.providers.openai_images import OpenAIImagesProvider
from studio.providers.registry import NoProviderAvailableError, ProviderRegistry, UnknownProviderError
from tests.conftest import image_bytes

PNG = image_bytes((64, 48), fmt="PNG")


def req(**kw) -> GenerationRequest:
    base = {"job_id": "j1", "prompt": "a cat", "media_type": MediaType.IMAGE, "model": "m"}
    return GenerationRequest(**{**base, **kw})


@pytest.fixture
def photo(tmp_path) -> InputImage:
    p = tmp_path / "photo.jpg"
    p.write_bytes(image_bytes((300, 400)))
    return InputImage(p, "image/jpeg", 300, 400)


# ---- OpenAI ------------------------------------------------------------------------------------


class FakeImages:
    def __init__(self):
        self.calls = []

    async def generate(self, **kw):
        self.calls.append(("generate", kw))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(PNG).decode())] * kw["n"])

    async def edit(self, **kw):
        self.calls.append(("edit", kw))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(PNG).decode())])


async def test_openai_generate_maps_aspect_ratio_to_size():
    images = FakeImages()
    p = OpenAIImagesProvider("k", client=SimpleNamespace(images=images))
    out = await p.generate_image(
        req(model="gpt-image-2.5-flare", aspect_ratio="16:9", n=2, negative_prompt="dogs")
    )
    ((kind, kw),) = images.calls
    assert kind == "generate" and kw["size"] == "1536x864" and kw["n"] == 2
    assert kw["prompt"].endswith("Avoid: dogs")
    assert len(out) == 2 and out[0].mime_type == "image/png"


async def test_openai_edit_sends_input_images_and_follows_their_shape(photo):
    images = FakeImages()
    p = OpenAIImagesProvider("k", client=SimpleNamespace(images=images))
    await p.generate_image(req(aspect_ratio=None, input_images=[photo]))
    ((kind, kw),) = images.calls
    assert kind == "edit" and kw["size"] == "1056x1408"  # 3:4, nearest to 300x400
    name, data, mime = kw["image"][0]
    assert name == "photo.jpg" and mime == "image/jpeg" and data == photo.path.read_bytes()


# ---- Gemini ------------------------------------------------------------------------------------


class FakeInteractions:
    def __init__(self, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    async def create(self, **kw):
        self.calls.append(kw)
        if self.fail_first and len(self.calls) == 1:
            raise httpx.ConnectError("boom")
        if kw["response_format"]["type"] == "video":
            return SimpleNamespace(
                output_video=SimpleNamespace(data=base64.b64encode(b"mp4").decode(), mime_type="video/mp4")
            )
        return SimpleNamespace(
            output_image=SimpleNamespace(data=base64.b64encode(PNG).decode(), mime_type="image/png")
        )


def gemini(interactions) -> GeminiProvider:
    return GeminiProvider("k", client=SimpleNamespace(aio=SimpleNamespace(interactions=interactions)))


async def test_gemini_image_input_blocks_and_one_call_per_image(photo):
    calls = FakeInteractions()
    out = await gemini(calls).generate_image(req(n=2, aspect_ratio=None, input_images=[photo]))
    assert len(calls.calls) == 2 and len(out) == 2
    args = calls.calls[0]
    image_block, text_block = args["input"]
    assert image_block["type"] == "image" and image_block["mime_type"] == "image/jpeg"
    assert base64.b64decode(image_block["data"]) == photo.path.read_bytes()
    assert text_block == {"type": "text", "text": "a cat"}
    assert args["response_format"] == {"type": "image", "aspect_ratio": "3:4", "image_size": "1K"}
    assert (out[0].width, out[0].height) == (64, 48)


async def test_gemini_partial_results_succeed_with_fewer_images():
    out = await gemini(FakeInteractions(fail_first=True)).generate_image(req(n=2))
    assert len(out) == 1


async def test_gemini_video_sends_duration():
    calls = FakeInteractions()
    out = await gemini(calls).generate_video(
        req(media_type=MediaType.VIDEO, aspect_ratio="9:16", duration_seconds=6)
    )
    fmt = calls.calls[0]["response_format"]
    assert fmt == {"type": "video", "aspect_ratio": "9:16", "resolution": "720p", "duration": "6s"}
    assert out.content == b"mp4" and out.mime_type == "video/mp4"


# ---- fal ---------------------------------------------------------------------------------------


class FakeFal:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.uploads = []

    async def upload(self, data, content_type):
        self.uploads.append((data, content_type))
        return f"https://fal.media/up/{len(self.uploads)}"

    async def subscribe(self, endpoint, arguments):
        self.calls.append((endpoint, arguments))
        return self.result


@respx.mock
async def test_fal_text_to_image_downloads_outputs():
    respx.get("https://fal.media/out/1.png").mock(
        return_value=httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    )
    fal = FakeFal({"images": [{"url": "https://fal.media/out/1.png", "width": 64, "height": 48}]})
    async with httpx.AsyncClient() as http:
        p = FalProvider("k", http, client=fal)
        out = await p.generate_image(req(model="fal-ai/flux/dev", aspect_ratio="16:9", seed=7))
    endpoint, args = fal.calls[0]
    assert endpoint == "fal-ai/flux/dev" and args["image_size"] == "landscape_16_9" and args["seed"] == 7
    assert out[0].content == PNG


@respx.mock
async def test_fal_image_input_uploads_then_passes_urls(photo):
    respx.get("https://fal.media/out/1.png").mock(return_value=httpx.Response(200, content=PNG))
    fal = FakeFal({"images": [{"url": "https://fal.media/out/1.png"}]})
    async with httpx.AsyncClient() as http:
        p = FalProvider("k", http, client=fal)
        r = req(model="fal-ai/nano-banana/edit", aspect_ratio=None, input_images=[photo])
        p.validate(r)
        await p.generate_image(r)
    _, args = fal.calls[0]
    assert args["image_urls"] == ["https://fal.media/up/1"] and args["aspect_ratio"] == "3:4"
    assert fal.uploads[0][1] == "image/jpeg"


def test_fal_rejects_image_input_on_endpoints_not_set_up_for_it(photo):
    p = FalProvider("k", httpx.AsyncClient(), client=FakeFal({}))
    with pytest.raises(UnsupportedRequestError):
        p.validate(req(model="fal-ai/flux/dev", input_images=[photo]))


@respx.mock
async def test_fal_video_streams_to_a_temp_file(tmp_path):
    respx.get("https://fal.media/v.mp4").mock(return_value=httpx.Response(200, content=b"movie"))
    fal = FakeFal({"video": {"url": "https://fal.media/v.mp4"}})
    async with httpx.AsyncClient() as http:
        p = FalProvider("k", http, client=fal)
        p.temp_dir = tmp_path
        out = await p.generate_video(
            req(
                media_type=MediaType.VIDEO,
                model="fal-ai/kling-video/v3/pro/text-to-video",
                aspect_ratio="16:9",
                duration_seconds=5,
                negative_prompt="blur",
            )
        )
    _, args = fal.calls[0]
    assert args == {"prompt": "a cat", "aspect_ratio": "16:9", "duration": "5", "negative_prompt": "blur"}
    assert isinstance(out.content, Path) and out.content.read_bytes() == b"movie"


def test_fal_rejects_endpoints_not_enabled_in_config():
    cfg = fal_module.FalConfig.model_validate(
        {
            "models": [
                {"id": "fal-ai/flux/dev", "media": "image"},
                {"id": "fal-ai/other", "media": "image", "enabled": False},
            ]
        }
    )
    p = FalProvider("k", httpx.AsyncClient(), client=FakeFal({}), config=cfg)
    assert p.capabilities.known_image_models == ("fal-ai/flux/dev",) and not p.capabilities.video
    assert p.capabilities.default_image_model == "fal-ai/flux/dev"
    p.validate(req(model="fal-ai/flux/dev"))
    with pytest.raises(UnsupportedRequestError) as e:
        p.validate(req(model="fal-ai/other"))
    assert e.value.field == "model"


def test_fal_config_input_param_comes_from_yaml(tmp_path):
    f = tmp_path / "fal.yaml"
    f.write_text(
        "models:\n"
        "  - {id: fal-ai/x/edit, media: image, size_param: aspect_ratio,"
        " input: {param: source_urls, list: true, max: 3}}\n"
    )
    cfg = fal_module.load_config(f)
    p = FalProvider("k", httpx.AsyncClient(), client=FakeFal({}), config=cfg)
    assert p.capabilities.image_input_models == ("fal-ai/x/edit",) and p.capabilities.max_input_images == 3
    assert cfg.model("fal-ai/x/edit", "image").input.param == "source_urls"


@pytest.mark.parametrize(
    "bad",
    [
        "models: [{id: a, media: image}, {id: a, media: image}]",  # duplicate
        "default_image_model: nope\nmodels: [{id: a, media: image}]",  # default not enabled
        "image_aspect_ratios: ['2:1']\nmodels: [{id: a, media: image}]",  # no flux preset
        "models: [{id: a, media: audio}]",
        "models: [{id: a, media: image, typo: 1}]",
    ],
)
def test_fal_config_rejects_bad_files(tmp_path, bad):
    f = tmp_path / "fal.yaml"
    f.write_text(bad)
    with pytest.raises(ValueError, match="model config"):
        fal_module.load_config(f)


def test_packaged_model_configs_load():
    fal_cfg = fal_module.load_config()
    assert fal_cfg.default_image_model and fal_cfg.default_video_model
    or_cfg = openrouter.load_config()
    assert or_cfg.default_model in or_cfg.enabled_ids


# ---- OpenRouter --------------------------------------------------------------------------------

OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_CONFIG = openrouter.OpenRouterConfig.model_validate(
    {
        "aspect_ratios": ["1:1", "16:9", "3:4"],
        "models": [
            {"id": "google/gemini-2.5-flash-image", "image_input": True, "max_input_images": 2},
            {"id": "bfl/flux", "modalities": ["image"], "aspect_ratio": False},
            {"id": "openai/gpt-5-image", "enabled": False},
        ],
    }
)


def or_image(data: bytes = PNG, mime: str = "image/png") -> dict:
    url = f"data:{mime};base64," + base64.b64encode(data).decode()
    return {
        "id": "gen-1",
        "choices": [
            {"message": {"content": "", "images": [{"type": "image_url", "image_url": {"url": url}}]}}
        ],
    }


def router(http) -> openrouter.OpenRouterProvider:
    return openrouter.OpenRouterProvider("sk-or", http, OR_CONFIG)


def test_openrouter_capabilities_list_only_enabled_models():
    caps = router(httpx.AsyncClient()).capabilities
    assert caps.known_image_models == ("google/gemini-2.5-flash-image", "bfl/flux")
    assert caps.image_input_models == ("google/gemini-2.5-flash-image",)
    assert caps.default_image_model == "google/gemini-2.5-flash-image"
    assert caps.max_input_images == 2 and not caps.video
    json.dumps(caps.__dict__)


def test_openrouter_validate_enforces_config(photo):
    p = router(httpx.AsyncClient())
    p.validate(req(model="google/gemini-2.5-flash-image", input_images=[photo]))
    for bad in (
        req(model="openai/gpt-5-image"),  # disabled
        req(model="someone/else"),  # not listed
        req(model="bfl/flux", input_images=[photo]),  # no image input
        req(model="google/gemini-2.5-flash-image", input_images=[photo] * 3),  # over the cap
    ):
        with pytest.raises(UnsupportedRequestError):
            p.validate(bad)


@respx.mock
async def test_openrouter_sends_images_and_aspect_ratio(photo):
    route = respx.post(OR_URL).mock(return_value=httpx.Response(200, json=or_image()))
    async with httpx.AsyncClient() as http:
        out = await router(http).generate_image(
            req(model="google/gemini-2.5-flash-image", aspect_ratio=None, input_images=[photo], n=2)
        )
    assert route.call_count == 2 and len(out) == 2
    sent = json.loads(route.calls[0].request.content)
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-or"
    assert sent["modalities"] == ["image", "text"]
    assert sent["image_config"] == {"aspect_ratio": "3:4"}  # nearest to 300x400
    first, text = sent["messages"][0]["content"]
    assert first["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert text == {"type": "text", "text": "a cat"}
    assert out[0].content == PNG and out[0].mime_type == "image/png"
    assert (out[0].width, out[0].height) == (64, 48)


@respx.mock
async def test_openrouter_image_only_model_skips_aspect_ratio():
    route = respx.post(OR_URL).mock(return_value=httpx.Response(200, json=or_image()))
    async with httpx.AsyncClient() as http:
        await router(http).generate_image(req(model="bfl/flux", aspect_ratio="16:9"))
    sent = json.loads(route.calls[0].request.content)
    assert sent["modalities"] == ["image"] and "image_config" not in sent


@respx.mock
async def test_openrouter_downloads_url_outputs():
    body = or_image()
    body["choices"][0]["message"]["images"][0]["image_url"]["url"] = "https://cdn.example/x.png"
    respx.post(OR_URL).mock(return_value=httpx.Response(200, json=body))
    respx.get("https://cdn.example/x.png").mock(
        return_value=httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    )
    async with httpx.AsyncClient() as http:
        out = await router(http).generate_image(req(model="bfl/flux"))
    assert out[0].content == PNG


@respx.mock
@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (httpx.Response(429, json={"error": {"message": "rate limited"}}), ProviderUnavailableError),
        (
            httpx.Response(200, json={"error": {"code": 502, "message": "upstream down"}}),
            ProviderUnavailableError,
        ),
        (
            httpx.Response(
                200,
                json={"choices": [{"finish_reason": "content_filter", "message": {"content": "no"}}]},
            ),
            ProviderContentPolicyError,
        ),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": "here is a poem"}}]}),
            ProviderInvalidRequestError,
        ),
    ],
)
async def test_openrouter_errors(response, kind):
    respx.post(OR_URL).mock(return_value=response)
    async with httpx.AsyncClient() as http:
        with pytest.raises(kind):
            await router(http).generate_image(req(model="bfl/flux"))


@pytest.mark.parametrize(
    "raw",
    [
        {"default_model": "openai/gpt-5-image", "models": [{"id": "openai/gpt-5-image", "enabled": False}]},
        {"models": [{"id": "a", "modalities": ["text"]}]},
        {"aspect_ratios": ["wide"], "models": [{"id": "a"}]},
    ],
)
def test_openrouter_config_rejects_bad_values(raw):
    with pytest.raises(ValueError):
        openrouter.OpenRouterConfig.model_validate(raw)


def test_openrouter_needs_an_enabled_model():
    cfg = openrouter.OpenRouterConfig.model_validate({"models": [{"id": "a", "enabled": False}]})
    with pytest.raises(ValueError, match="no enabled models"):
        openrouter.OpenRouterProvider("k", httpx.AsyncClient(), cfg)


# ---- shared ------------------------------------------------------------------------------------


class StatusError(Exception):
    def __init__(self, status_code, msg="x"):
        super().__init__(msg)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (StatusError(429), ProviderUnavailableError),
        (StatusError(503), ProviderUnavailableError),
        (httpx.ConnectError("x"), ProviderUnavailableError),
        (StatusError(400, "blocked by safety system"), ProviderContentPolicyError),
        (StatusError(400, "bad size"), ProviderInvalidRequestError),
    ],
)
def test_error_translation(exc, kind):
    assert type(translate(exc, "p")) is kind


def test_registry_resolution():
    reg = ProviderRegistry({"fake": FakeProvider()})
    assert reg.resolve(MediaType.IMAGE, None, None).model == "fake-image-1"
    with pytest.raises(UnknownProviderError):
        reg.resolve(MediaType.IMAGE, "gemini", None)
    with pytest.raises(NoProviderAvailableError):
        ProviderRegistry({}).resolve(MediaType.IMAGE, None, None)


def test_base_validation():
    p = FakeProvider()
    with pytest.raises(UnsupportedRequestError):
        p.validate(req(n=9))
    with pytest.raises(UnsupportedRequestError):
        p.validate(req(media_type=MediaType.VIDEO, aspect_ratio="16:9", duration_seconds=7))
    p.validate(req(media_type=MediaType.VIDEO, aspect_ratio="16:9", duration_seconds=4))
    json.dumps(p.capabilities.__dict__)  # serialisable for /v1/providers
