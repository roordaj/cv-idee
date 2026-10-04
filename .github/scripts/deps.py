#!/usr/bin/env python3
"""Synchroniseer `status:blocked` / `status:ready` met de `Depends on #n`-regels.

Voor elk open issue (geen pull requests) in de repository:

* Bevat het issue `status:in-progress`, `status:needs-human` of
  `status:needs-refinement`, dan blijft het ongemoeid.
* Zonder `Depends on #...`-regel gebeurt er niets.
* Alle afhankelijkheden gesloten en label `status:blocked` aanwezig
  -> `status:blocked` eraf, `status:ready` erbij, plus een comment.
* Minstens één afhankelijkheid open en label `status:ready` aanwezig
  -> `status:ready` eraf, `status:blocked` erbij, plus een comment met
  de open afhankelijkheden.

Het script is idempotent: een tweede run zonder wijzigingen doet niets.
Alleen Python 3.12 stdlib; praat direct met de GitHub REST API.

Omgevingsvariabelen:
    GITHUB_TOKEN        token met `issues: write`
    GITHUB_REPOSITORY   `owner/repo`
    DRY_RUN=1           alleen tonen wat er zou veranderen, niets schrijven
    GITHUB_API_URL      optioneel, standaard https://api.github.com

Lokaal draaien (dry-run):
    DRY_RUN=1 GITHUB_TOKEN=... GITHUB_REPOSITORY=roordaj/cv-idee \\
        python3 .github/scripts/deps.py

Unittests:
    python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

READY = "status:ready"
BLOCKED = "status:blocked"
MANUAL_LABELS = frozenset(
    {"status:in-progress", "status:needs-human", "status:needs-refinement"}
)

READY_COMMENT = "Alle afhankelijkheden zijn gesloten — klaar om op te pakken."

# `Depends on #1, #2 and #3` / `depends on: #4 & #5` / `Depends on #6 en #7`
_DEPENDS_RE = re.compile(
    r"depends\s+on\s*:?\s*"
    r"(#\d+(?:(?:\s*(?:,|;|&|\band\b|\ben\b))*\s*#\d+)*)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"#(\d+)")


# --------------------------------------------------------------------------
# Pure functies (unit-getest)
# --------------------------------------------------------------------------


def parse_dependencies(body: str | None, self_number: int | None = None) -> list[int]:
    """Geef de gesorteerde, unieke issuenummers uit alle `Depends on`-regels."""
    if not body:
        return []
    numbers: set[int] = set()
    for match in _DEPENDS_RE.finditer(body):
        numbers.update(int(n) for n in _NUMBER_RE.findall(match.group(1)))
    if self_number is not None:
        numbers.discard(self_number)
    return sorted(numbers)


@dataclass(frozen=True)
class Transition:
    """Een labelwissel voor één issue."""

    remove: str
    add: str
    comment: str
    open_deps: tuple[int, ...] = field(default=())


def blocked_comment(open_deps: list[int] | tuple[int, ...]) -> str:
    refs = ", ".join(f"#{n}" for n in open_deps)
    return f"Nog open afhankelijkheden: {refs} — terug naar `{BLOCKED}`."


def decide(
    labels: set[str] | frozenset[str],
    deps: list[int],
    is_closed: dict[int, bool],
) -> Transition | None:
    """Bepaal de benodigde overgang, of None als er niets hoeft te gebeuren.

    `is_closed` mapt issuenummer -> True als gesloten. Onbekende nummers
    gelden (conservatief) als open.
    """
    if labels & MANUAL_LABELS or not deps:
        return None
    open_deps = tuple(n for n in deps if not is_closed.get(n, False))
    if not open_deps:
        if BLOCKED in labels:
            return Transition(remove=BLOCKED, add=READY, comment=READY_COMMENT)
        return None
    if READY in labels:
        return Transition(
            remove=READY,
            add=BLOCKED,
            comment=blocked_comment(open_deps),
            open_deps=open_deps,
        )
    return None


# --------------------------------------------------------------------------
# GitHub REST API
# --------------------------------------------------------------------------


class GitHub:
    def __init__(self, token: str, repo: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.base = f"{api_url.rstrip('/')}/repos/{repo}"

    def request(self, method: str, path: str, payload: object | None = None):
        url = path if path.startswith("http") else f"{self.base}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return (json.loads(body) if body else None), resp.headers

    def open_issues(self) -> list[dict]:
        issues: list[dict] = []
        url: str | None = "/issues?state=open&per_page=100"
        while url:
            page, headers = self.request("GET", url)
            issues.extend(i for i in page if "pull_request" not in i)
            url = next_link(headers.get("Link"))
        return issues

    def is_closed(self, number: int) -> bool:
        try:
            issue, _ = self.request("GET", f"/issues/{number}")
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return False  # onbekend/verwijderd: conservatief als open
            raise
        return issue["state"] == "closed"

    def apply(self, number: int, t: Transition) -> None:
        label = urllib.parse.quote(t.remove, safe="")
        try:
            self.request("DELETE", f"/issues/{number}/labels/{label}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        self.request("POST", f"/issues/{number}/labels", {"labels": [t.add]})
        self.request("POST", f"/issues/{number}/comments", {"body": t.comment})


def next_link(link_header: str | None) -> str | None:
    """Haal de `rel="next"`-URL uit een GitHub Link-header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part)
        if m:
            return m.group(1)
    return None


# --------------------------------------------------------------------------
# Hoofdprogramma
# --------------------------------------------------------------------------


def run(gh: GitHub, dry_run: bool) -> int:
    issues = gh.open_issues()
    # Cache: alle open issues zijn al bekend; de rest wordt op aanvraag opgehaald.
    closed_cache: dict[int, bool] = {i["number"]: False for i in issues}

    changes = 0
    for issue in sorted(issues, key=lambda i: i["number"]):
        number = issue["number"]
        deps = parse_dependencies(issue.get("body"), self_number=number)
        if not deps:
            continue
        labels = {lbl["name"] for lbl in issue.get("labels", [])}
        if labels & MANUAL_LABELS:
            continue  # geen API-calls nodig
        for dep in deps:
            if dep not in closed_cache:
                closed_cache[dep] = gh.is_closed(dep)
        t = decide(labels, deps, closed_cache)
        if t is None:
            continue
        changes += 1
        prefix = "[dry-run] " if dry_run else ""
        print(f"{prefix}#{number}: {t.remove} -> {t.add} ({t.comment})")
        if not dry_run:
            gh.apply(number, t)

    print(
        f"{len(issues)} open issues bekeken, {len(closed_cache)} issuestatussen in "
        f"cache, {changes} wijziging(en){' (dry-run)' if dry_run else ''}."
    )
    return changes


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GITHUB_TOKEN en GITHUB_REPOSITORY zijn verplicht.", file=sys.stderr)
        return 2
    dry_run = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}
    gh = GitHub(token, repo, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    run(gh, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
