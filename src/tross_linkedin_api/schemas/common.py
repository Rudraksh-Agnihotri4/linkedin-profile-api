"""Shared strict public schema primitives."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import ConfigDict, StringConstraints


STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    validate_by_name=True,
    validate_by_alias=True,
)
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PartialDate = Annotated[
    str,
    StringConstraints(
        pattern=re.compile(
            r"^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$"
        )
    ),
]
