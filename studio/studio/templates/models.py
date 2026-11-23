import re

from pydantic import BaseModel, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")


class InputSlot(BaseModel):
    name: str
    label: str = ""
    required: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("slot names use letters, digits and _ (max 40), starting with a letter")
        return v


class Variable(BaseModel):
    name: str
    label: str = ""
    default: str = ""
    max_length: int = Field(100, ge=1, le=1000)
    choices: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("variable names use letters, digits and _ (max 40), starting with a letter")
        return v


class TemplateParams(BaseModel):
    aspect_ratio: str = "auto"  # "auto" = follow the first input image
    n: int = Field(1, ge=1, le=8)
    seed: int | None = None
    duration_seconds: int | None = None


class TemplateFields(BaseModel):
    """Everything a version stores; the body of create (plus slug) and update (plus base_version)."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    media_type: str = Field("image", pattern="^(image|video)$")
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    allowed_models: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1, max_length=8000)
    negative_prompt: str | None = Field(None, max_length=4000)
    params: TemplateParams = Field(default_factory=TemplateParams)
    inputs: list[InputSlot] = Field(default_factory=list, max_length=8)
    variables: list[Variable] = Field(default_factory=list, max_length=20)
    reference_uploads: list[str] = Field(default_factory=list, max_length=8)
    cover_upload: str | None = None  # an upload shown as the template's picture in apps and the console
    note: str | None = Field(None, max_length=500)


class TemplateCreate(TemplateFields):
    slug: str
    # credits a signed-in app user pays per run (not versioned); None = 1 on create
    credit_cost: int | None = Field(None, ge=0, le=10_000)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug: 3-64 lower-case letters, digits and dashes; no dash at the ends")
        return v


class TemplateUpdate(TemplateFields):
    base_version: int
    credit_cost: int | None = Field(None, ge=0, le=10_000)  # None = unchanged
