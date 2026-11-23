import base64

from openai import AsyncOpenAI

from creative.providers.base import (
    GeneratedAsset,
    GenerationRequest,
    Provider,
    ProviderCapabilities,
    ProviderInvalidRequestError,
)
from creative.providers.errors import translate

SIZES = {
    "1:1": "1024x1024",
    "16:9": "1536x864",
    "9:16": "864x1536",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "4:3": "1408x1056",
    "3:4": "1056x1408",
}
MODELS = ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2")


class OpenAIImagesProvider(Provider):
    capabilities = ProviderCapabilities(
        name="openai",
        image=True,
        video=False,
        default_image_model="gpt-image-2.5-flare",
        known_image_models=MODELS,
        max_images=8,
        image_aspect_ratios=tuple(SIZES),
        image_input=True,
        image_input_models=MODELS,
        max_input_images=8,
    )

    def __init__(self, api_key: str, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=api_key, timeout=170, max_retries=0)

    def build_arguments(self, req: GenerationRequest) -> dict:
        return {
            "model": req.model,
            "prompt": self.fold_negative(req.prompt, req.negative_prompt),
            "size": SIZES[self.resolved_aspect_ratio(req)],
            "n": req.n,
            "output_format": "png",
        }

    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]:
        args = self.build_arguments(req)
        try:
            if req.input_images:
                images = [(p.path.name, p.path.read_bytes(), p.mime_type) for p in req.input_images]
                result = await self.client.images.edit(image=images, **args)
            else:
                result = await self.client.images.generate(**args)
        except Exception as e:
            raise translate(e, "openai") from e
        width, height = (int(x) for x in args["size"].split("x"))
        assets = [
            GeneratedAsset(base64.b64decode(d.b64_json), "image/png", width, height)
            for d in (result.data or [])
            if d.b64_json
        ]
        if not assets:
            raise ProviderInvalidRequestError("openai: response had no images")
        return assets

    async def aclose(self) -> None:
        await self.client.close()
