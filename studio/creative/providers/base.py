from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class InputImage:
    path: Path
    mime_type: str
    width: int
    height: int
    role: str = "input"  # "input" (the caller's) or "reference" (attached to a template)


@dataclass
class GenerationRequest:
    job_id: str
    prompt: str
    media_type: MediaType
    model: str
    aspect_ratio: str | None = "1:1"  # None = follow the first input image
    n: int = 1
    duration_seconds: int | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    input_images: list[InputImage] = field(default_factory=list)


@dataclass
class GeneratedAsset:
    content: bytes | Path
    mime_type: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    image: bool
    video: bool
    default_image_model: str | None = None
    default_video_model: str | None = None
    known_image_models: tuple[str, ...] = ()
    known_video_models: tuple[str, ...] = ()
    max_images: int = 1
    image_aspect_ratios: tuple[str, ...] = ("1:1",)
    video_aspect_ratios: tuple[str, ...] = ()
    video_durations: tuple[int, ...] = ()  # empty = provider picks
    supports_negative_prompt: bool = False
    supports_seed: bool = False
    image_input: bool = False
    image_input_models: tuple[str, ...] = ()
    max_input_images: int = 0


class ProviderError(Exception):
    code = "provider_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    retryable = True


class ProviderInvalidRequestError(ProviderError):
    code = "invalid_request"


class ProviderContentPolicyError(ProviderError):
    code = "content_policy"


class ProviderOperationTimeout(ProviderError):
    code = "timeout"


class UnsupportedRequestError(Exception):
    """A request the provider can't serve; raised at submit time (422)."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def nearest_aspect_ratio(width: int, height: int, choices: tuple[str, ...]) -> str:
    target = width / height

    def ratio(r: str) -> float:
        a, b = r.split(":")
        return int(a) / int(b)

    return min(choices, key=lambda r: abs(ratio(r) - target))


class Provider(abc.ABC):
    capabilities: ProviderCapabilities

    @property
    def name(self) -> str:
        return self.capabilities.name

    def validate(self, req: GenerationRequest) -> None:
        caps = self.capabilities
        if req.media_type == MediaType.IMAGE:
            if not caps.image:
                raise UnsupportedRequestError(f"{caps.name} does not generate images", "media_type")
            if not 1 <= req.n <= caps.max_images:
                raise UnsupportedRequestError(f"n must be 1..{caps.max_images} for {caps.name}", "n")
            if req.aspect_ratio is not None and req.aspect_ratio not in caps.image_aspect_ratios:
                raise UnsupportedRequestError(
                    f"aspect_ratio must be one of {', '.join(caps.image_aspect_ratios)}", "aspect_ratio"
                )
            if req.duration_seconds is not None:
                raise UnsupportedRequestError("duration_seconds is only for video", "duration_seconds")
        else:
            if not caps.video:
                raise UnsupportedRequestError(f"{caps.name} does not generate video", "media_type")
            if req.n != 1:
                raise UnsupportedRequestError("n must be 1 for video", "n")
            if req.aspect_ratio is not None and req.aspect_ratio not in caps.video_aspect_ratios:
                raise UnsupportedRequestError(
                    f"aspect_ratio must be one of {', '.join(caps.video_aspect_ratios)}", "aspect_ratio"
                )
            if (
                req.duration_seconds is not None
                and caps.video_durations
                and req.duration_seconds not in caps.video_durations
            ):
                durations = ", ".join(map(str, caps.video_durations))
                raise UnsupportedRequestError(
                    f"duration_seconds must be one of {durations}", "duration_seconds"
                )
        if req.negative_prompt and not caps.supports_negative_prompt:
            # Folded into the prompt by providers that lack the parameter; see _fold_negative.
            pass
        if req.seed is not None and not caps.supports_seed:
            raise UnsupportedRequestError(f"{caps.name} does not support seed", "seed")
        if req.input_images:
            if not caps.image_input:
                raise UnsupportedRequestError(f"{caps.name} does not take input images", "provider")
            if len(req.input_images) > caps.max_input_images:
                raise UnsupportedRequestError(
                    f"{caps.name} takes at most {caps.max_input_images} input images", "inputs"
                )

    def resolved_aspect_ratio(self, req: GenerationRequest) -> str:
        choices = (
            self.capabilities.image_aspect_ratios
            if req.media_type == MediaType.IMAGE
            else self.capabilities.video_aspect_ratios
        )
        if req.aspect_ratio:
            return req.aspect_ratio
        if req.input_images:
            first = req.input_images[0]
            return nearest_aspect_ratio(first.width, first.height, choices)
        return "1:1" if "1:1" in choices else choices[0]

    @staticmethod
    def fold_negative(prompt: str, negative: str | None) -> str:
        return f"{prompt}\n\nAvoid: {negative}" if negative else prompt

    @abc.abstractmethod
    async def generate_image(self, req: GenerationRequest) -> list[GeneratedAsset]: ...

    async def generate_video(self, req: GenerationRequest) -> GeneratedAsset:
        raise ProviderInvalidRequestError(f"{self.name} does not generate video")

    async def aclose(self) -> None:
        return None
