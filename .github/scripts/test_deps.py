"""Unittests voor deps.py.

Draaien: python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import deps  # noqa: E402
from deps import BLOCKED, READY, READY_COMMENT, decide, next_link, parse_dependencies  # noqa: E402


class ParseDependenciesTest(unittest.TestCase):
    def test_standard_section(self):
        body = "## Afhankelijkheden\nDepends on #10, #28, #15\n\n## Definition of Done"
        self.assertEqual(parse_dependencies(body), [10, 15, 28])

    def test_none(self):
        self.assertEqual(parse_dependencies("## Afhankelijkheden\nGeen — direct op te pakken."), [])
        self.assertEqual(parse_dependencies(""), [])
        self.assertEqual(parse_dependencies(None), [])

    def test_case_insensitive_and_separators(self):
        self.assertEqual(parse_dependencies("depends on #1 and #2"), [1, 2])
        self.assertEqual(parse_dependencies("DEPENDS ON: #3 & #4; #5"), [3, 4, 5])
        self.assertEqual(parse_dependencies("Depends on #6 en #7"), [6, 7])
        self.assertEqual(parse_dependencies("Depends  on   #8 #9"), [8, 9])
        self.assertEqual(parse_dependencies("Depends on #1,#2 , and #3"), [1, 2, 3])

    def test_multiple_lines_deduplicated(self):
        body = "Depends on #4, #2\ntekst\nDepends on #2 and #9"
        self.assertEqual(parse_dependencies(body), [2, 4, 9])

    def test_ignores_other_references(self):
        body = "Zie #99 en #100.\nDepends on #5\nRaakt #77"
        self.assertEqual(parse_dependencies(body), [5])

    def test_stops_after_list(self):
        self.assertEqual(parse_dependencies("Depends on #5. Zie ook #6"), [5])
        self.assertEqual(parse_dependencies("Depends on #5 en verder #6"), [5])

    def test_self_reference_ignored(self):
        self.assertEqual(parse_dependencies("Depends on #3, #4", self_number=3), [4])


class DecideTest(unittest.TestCase):
    def test_all_closed_blocked_becomes_ready(self):
        t = decide({BLOCKED, "prio:M"}, [1, 2], {1: True, 2: True})
        self.assertIsNotNone(t)
        self.assertEqual((t.remove, t.add, t.comment), (BLOCKED, READY, READY_COMMENT))

    def test_all_closed_already_ready_noop(self):
        self.assertIsNone(decide({READY}, [1], {1: True}))

    def test_open_dep_ready_becomes_blocked(self):
        t = decide({READY}, [1, 2, 3], {1: True, 2: False, 3: False})
        self.assertEqual((t.remove, t.add), (READY, BLOCKED))
        self.assertEqual(t.open_deps, (2, 3))
        self.assertIn("#2, #3", t.comment)

    def test_open_dep_already_blocked_noop(self):
        self.assertIsNone(decide({BLOCKED}, [1], {1: False}))

    def test_unknown_dep_counts_as_open(self):
        self.assertIsNone(decide({BLOCKED}, [1, 2], {1: True}))
        t = decide({READY}, [1, 2], {1: True})
        self.assertEqual(t.open_deps, (2,))

    def test_manual_labels_untouched(self):
        for manual in ("status:in-progress", "status:needs-human", "status:needs-refinement"):
            with self.subTest(manual=manual):
                self.assertIsNone(decide({BLOCKED, manual}, [1], {1: True}))
                self.assertIsNone(decide({READY, manual}, [1], {1: False}))

    def test_no_deps_noop(self):
        self.assertIsNone(decide({BLOCKED}, [], {}))
        self.assertIsNone(decide({READY}, [], {}))

    def test_no_status_label_noop(self):
        self.assertIsNone(decide({"prio:M"}, [1], {1: True}))
        self.assertIsNone(decide({"prio:M"}, [1], {1: False}))


class NextLinkTest(unittest.TestCase):
    def test_parses_next(self):
        header = (
            '<https://api.github.com/r?page=2>; rel="next", '
            '<https://api.github.com/r?page=5>; rel="last"'
        )
        self.assertEqual(next_link(header), "https://api.github.com/r?page=2")

    def test_no_next(self):
        self.assertIsNone(next_link('<https://api.github.com/r?page=1>; rel="prev"'))
        self.assertIsNone(next_link(None))


class FakeGitHub:
    """In-memory vervanger van deps.GitHub."""

    def __init__(self, issues: dict[int, dict]):
        self.issues = issues  # number -> {state, body, labels:set}
        self.lookups: list[int] = []
        self.comments: list[tuple[int, str]] = []

    def open_issues(self):
        return [
            {"number": n, "body": i["body"], "labels": [{"name": l} for l in i["labels"]]}
            for n, i in self.issues.items()
            if i["state"] == "open"
        ]

    def is_closed(self, number):
        self.lookups.append(number)
        issue = self.issues.get(number)
        return bool(issue and issue["state"] == "closed")

    def apply(self, number, t):
        labels = self.issues[number]["labels"]
        labels.discard(t.remove)
        labels.add(t.add)
        self.comments.append((number, t.comment))


def _issue(state, labels, body=""):
    return {"state": state, "labels": set(labels), "body": body}


class RunScenarioTest(unittest.TestCase):
    def run_quiet(self, gh, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return deps.run(gh, dry_run)

    def make(self):
        return FakeGitHub(
            {
                1: _issue("open", [READY]),
                2: _issue("open", [BLOCKED], "Depends on #1"),
                3: _issue("open", [BLOCKED], "Depends on #1, #2"),
                4: _issue("open", ["status:in-progress"], "Depends on #1"),
            }
        )

    def test_close_then_reopen(self):
        gh = self.make()
        self.assertEqual(self.run_quiet(gh), 0)

        gh.issues[1]["state"] = "closed"
        self.assertEqual(self.run_quiet(gh), 1)
        self.assertEqual(gh.issues[2]["labels"], {READY})
        self.assertEqual(gh.issues[3]["labels"], {BLOCKED})  # #2 nog open
        self.assertEqual(gh.issues[4]["labels"], {"status:in-progress"})
        self.assertEqual(gh.comments, [(2, READY_COMMENT)])

        # Idempotent: tweede run verandert niets.
        self.assertEqual(self.run_quiet(gh), 0)

        gh.issues[1]["state"] = "open"
        self.assertEqual(self.run_quiet(gh), 1)
        self.assertEqual(gh.issues[2]["labels"], {BLOCKED})
        self.assertIn("#1", gh.comments[-1][1])

    def test_dry_run_changes_nothing(self):
        gh = self.make()
        gh.issues[1]["state"] = "closed"
        self.assertEqual(self.run_quiet(gh, dry_run=True), 1)
        self.assertEqual(gh.issues[2]["labels"], {BLOCKED})
        self.assertEqual(gh.comments, [])

    def test_lookups_cached_and_open_issues_not_fetched(self):
        gh = self.make()
        gh.issues[1]["state"] = "closed"
        self.run_quiet(gh, dry_run=True)
        # #1 gesloten -> één lookup ondanks twee verwijzingen; #2 is open en dus al bekend.
        self.assertEqual(gh.lookups, [1])


if __name__ == "__main__":
    unittest.main()
