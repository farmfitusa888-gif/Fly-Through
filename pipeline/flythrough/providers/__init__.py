"""Provider profiles and payload validation.

A profile is the provider's own input schema, recorded from the provider,
stored as data. It exists so a payload can be checked against what the API
actually accepts WITHOUT a network call and without spending a credit.

That matters more here than it looks. Payload drift is silent: a renamed field
or a float where an integer is required produces a rejected job, which reaches
the customer as a failed render they already paid for and reaches the operator
looking exactly like a provider outage. Catching it in a test costs nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


class PayloadInvalid(ValueError):
    """The payload would be rejected by the provider. Raised before submitting."""


def load(model: str, mode: str) -> dict:
    p = HERE / f"openart-{model}-{mode}.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"no recorded schema for {model}/{mode}. Record one with "
            f"openart_model_form_get before submitting jobs against it -- "
            f"guessing a payload shape is how a paid render fails.")
    return json.loads(p.read_text())


def _check_frame(name: str, value, spec: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(value, dict):
        return [f"{name} must be an object"]
    missing = [k for k in spec["required"] if k not in value]
    if missing:
        errs.append(f"{name} is missing {missing}")
    if spec.get("additionalProperties") is False:
        extra = [k for k in value if k not in spec["required"] + ["metadata"]]
        if extra:
            errs.append(f"{name} has unknown keys {extra}")
    if value.get("type") != spec["type_const"]:
        errs.append(f"{name}.type must be {spec['type_const']!r}")
    if not str(value.get("url", "")).strip():
        errs.append(f"{name}.url is empty")
    return errs


def validate(params: dict, profile: dict) -> None:
    """Raise PayloadInvalid listing everything wrong, not just the first thing.

    All of it at once: fixing one field, resubmitting and discovering the next
    is how a debugging session becomes four rejected jobs.
    """
    errs: list[str] = []
    fields = profile["fields"]

    for key in profile["required"]:
        if key not in params:
            errs.append(f"missing required field {key!r}")

    if profile.get("additionalProperties") is False:
        extra = [k for k in params if k not in fields]
        if extra:
            errs.append(f"unknown fields {sorted(extra)} -- "
                        f"the provider rejects these outright")

    for key, value in params.items():
        spec = fields.get(key)
        if spec is None:
            continue
        kind = spec["type"]
        if kind == "frame":
            if value is None and spec.get("nullable"):
                continue
            errs.extend(_check_frame(key, value, profile["frame"]))
        elif kind == "integer":
            # bool is a subclass of int in Python; the provider does not agree.
            if isinstance(value, bool) or not isinstance(value, int):
                errs.append(f"{key} must be an integer, got "
                            f"{type(value).__name__} ({value!r})")
            elif not (spec["minimum"] <= value <= spec["maximum"]):
                errs.append(f"{key} must be {spec['minimum']}-{spec['maximum']}, "
                            f"got {value}")
        elif kind == "string":
            if not isinstance(value, str):
                errs.append(f"{key} must be a string, got {type(value).__name__}")
            elif "enum" in spec and value not in spec["enum"]:
                errs.append(f"{key} must be one of {spec['enum']}, got {value!r}")
        elif kind == "boolean":
            if not isinstance(value, bool):
                errs.append(f"{key} must be a boolean, got {type(value).__name__}")

    if errs:
        raise PayloadInvalid("; ".join(errs))
