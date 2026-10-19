#!/usr/bin/env python3
"""Update the Home Assistant add-on version from a semantic version or v-prefixed tag."""

from __future__ import annotations

import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "addon" / "config.yaml"
VERSION_LINE = re.compile(r'(?m)^version: "[^"\n]+"$')
SEMVER = re.compile(r"(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: set-addon-version.py VERSION", file=sys.stderr)
        return 2

    match = SEMVER.fullmatch(sys.argv[1])
    if match is None:
        print("Version must be MAJOR.MINOR.PATCH, optionally prefixed with v", file=sys.stderr)
        return 2

    version = ".".join(match.groups())
    content = CONFIG.read_text(encoding="utf-8")
    updated, count = VERSION_LINE.subn(f'version: "{version}"', content)
    if count != 1:
        print(f"Expected one version field in {CONFIG}", file=sys.stderr)
        return 1

    CONFIG.write_text(updated, encoding="utf-8")
    print(f"Set add-on version to {version} in {CONFIG.relative_to(CONFIG.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
