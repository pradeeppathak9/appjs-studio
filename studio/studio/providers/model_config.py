"""Loading the per-provider YAML files that list which models may be used (`openrouter.yaml`,
`fal.yaml`, next to this module). Each file is validated into a pydantic model at startup, so a bad
file stops the server instead of failing jobs later."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

CONFIG_DIR = Path(__file__).parent


def check_aspect_ratios(ratios: list[str]) -> None:
    for r in ratios:
        a, _, b = r.partition(":")
        if not (a.isdigit() and b.isdigit() and int(a) and int(b)):
            raise ValueError(f"aspect ratio {r!r} is not W:H")


def check_unique(ids: list[str]) -> None:
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate model ids: {', '.join(dupes)}")


def load_yaml_config[T: BaseModel](cls: type[T], path: Path) -> T:
    try:
        raw = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as e:
        raise ValueError(f"model config {path}: {e}") from e
