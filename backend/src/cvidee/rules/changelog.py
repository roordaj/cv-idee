"""Packaged rule changelog summaries, generated from docs/regels/*.md."""

import json
import re
from importlib.resources import files
from pathlib import Path


def parse_changelogs(directory: Path) -> dict[str, dict[str, list[str]]]:
    result = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_"):
            continue
        section = path.read_text().partition("## Wijzigingen")[2]
        versions: dict[str, list[str]] = {}
        version = None
        for line in section.splitlines():
            match = re.match(r"### (\d+\.\d+\.\d+)\b", line)
            if match:
                version = match[1]
                versions[version] = []
            elif version and line.startswith("- "):
                versions[version].append(line[2:])
        result[path.stem] = versions
    return result


def changes_since(rule_id: str, before: str, after: str) -> list[str]:
    data = json.loads(files("cvidee.rules").joinpath("changelog.json").read_text())

    def version(value: str) -> tuple[int, ...]:
        return tuple(int(part) for part in value.split("."))

    try:
        return [
            text
            for key, entries in sorted(
                data.get(rule_id, {}).items(), key=lambda item: version(item[0])
            )
            if version(before) < version(key) <= version(after)
            for text in entries
        ]
    except ValueError:
        return []


if __name__ == "__main__":
    import sys

    Path(sys.argv[2]).write_text(
        json.dumps(parse_changelogs(Path(sys.argv[1])), ensure_ascii=False, indent=2) + "\n"
    )
