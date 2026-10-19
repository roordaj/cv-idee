#!/usr/bin/env python3
"""Remove the registry image from a copied manifest so Supervisor builds it locally."""

from __future__ import annotations

import re
import sys
from pathlib import Path

IMAGE_LINE = re.compile(r"(?m)^image: .+\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: prepare-addon-local.py ADDON_CONFIG", file=sys.stderr)
        return 2

    config = Path(sys.argv[1])
    content = config.read_text(encoding="utf-8")
    updated, count = IMAGE_LINE.subn("", content)
    if count != 1:
        print(f"Expected one image field in {config}", file=sys.stderr)
        return 1

    config.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
