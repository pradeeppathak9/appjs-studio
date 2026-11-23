"""`{{name}}` substitution. No expressions, no template engine."""

import re

from creative.errors import ValidationFailed
from creative.templates.models import Variable

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def placeholders(text: str | None) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER.findall(text or "")))


def clean_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace("{{", "").replace("}}", "")


def resolve_values(variables: list[Variable], given: dict[str, object] | None) -> dict[str, str]:
    given = dict(given or {})
    known = {v.name for v in variables}
    unknown = sorted(set(given) - known)
    errors = [{"field": f"variables.{n}", "message": "unknown variable"} for n in unknown]
    values: dict[str, str] = {}
    for var in variables:
        raw = given.get(var.name, var.default)
        if not isinstance(raw, str | int | float):
            errors.append({"field": f"variables.{var.name}", "message": "must be a string"})
            continue
        value = clean_value(str(raw))
        if len(value) > var.max_length:
            errors.append(
                {"field": f"variables.{var.name}", "message": f"at most {var.max_length} characters"}
            )
        elif var.choices and value not in var.choices:
            errors.append(
                {"field": f"variables.{var.name}", "message": f"must be one of {', '.join(var.choices)}"}
            )
        values[var.name] = value
    if errors:
        raise ValidationFailed("invalid variables", details=errors)
    return values


def render(text: str | None, values: dict[str, str]) -> str | None:
    if text is None:
        return None
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), text)
