"""Write the OpenAPI contract to ``api/openapi.json`` (``make openapi``).

Usage: ``python -m cvidee.api.openapi [output-path]``. The spec does not depend on the
environment (stub flag, tokens), so CI can regenerate it and diff against the committed file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from cvidee.config import Settings
from cvidee.main import create_app


def openapi_spec() -> dict[str, Any]:
    """The OpenAPI document of the application."""
    return create_app(Settings.model_validate({})).openapi()


def render() -> str:
    return json.dumps(openapi_spec(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else Path("../api/openapi.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
