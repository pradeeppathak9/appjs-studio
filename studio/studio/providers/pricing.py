"""What each model costs us, from `prices.yaml` next to this module. The console uses it to show a
template's cost per run and a suggested credit cost; nothing is billed from these numbers."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from studio.providers.model_config import CONFIG_DIR, load_yaml_config

DEFAULT_PRICES_PATH = CONFIG_DIR / "prices.yaml"


class ModelPrice(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usd: float = Field(ge=0)
    unit: Literal["image", "second"] = "image"
    note: str | None = None


class PriceList(BaseModel):
    checked: str = Field(description="when the prices were last checked (YYYY-MM-DD)")
    credit_usd: float = Field(gt=0, description="model cost one credit should cover, in US dollars")
    models: list[ModelPrice] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> PriceList:
        seen: set[tuple[str, str]] = set()
        for m in self.models:
            key = (m.provider, m.model)
            if key in seen:
                raise ValueError(f"duplicate price for {m.provider} {m.model}")
            seen.add(key)
        return self


@cache
def load_prices(path: Path = DEFAULT_PRICES_PATH) -> PriceList:
    return load_yaml_config(PriceList, path)
