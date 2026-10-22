"""Quarantine: failures of listed tests don't fail their stage.

After a stage exits with returncode ``1`` (the "some tests failed" code of
pytest, Behave, Jest, go test and most runners), the executor reads the
stage's Allure ``*-result.json`` files. When every failed or broken test
matches a ``quarantine:`` rule, the stage counts as passed for the exit code.
The tests still ran and their failures stay in the results, run record,
reports and Compare; the stage just records which ones were waived.

Anything else keeps failing the stage: an unquarantined failure, a returncode
other than ``1`` (timeouts, crashes, collection errors), or a failed stage
with no failed test in its results. Rules are ``fnmatch`` globs matched
against each test's ``name`` and ``fullName``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from testo_core.config.schema import QuarantineRule

# The only returncode a quarantine can waive: "tests ran and some failed".
WAIVABLE_RETURNCODE = 1

_FAILED = frozenset({"failed", "broken"})


@dataclass(frozen=True)
class QuarantineVerdict:
    # Failed tests that matched a rule, sorted, one entry per test name.
    quarantined: tuple[str, ...]
    # Failed tests that matched no rule; any of these keeps the stage failing.
    unquarantined: tuple[str, ...]

    @property
    def waives_stage(self) -> bool:
        return bool(self.quarantined) and not self.unquarantined


def matching_rule(
    rules: tuple[QuarantineRule, ...], *, name: str, full_name: str = ""
) -> QuarantineRule | None:
    """The first rule whose glob matches ``name`` or ``full_name``."""
    for rule in rules:
        if fnmatchcase(name, rule.test) or (full_name and fnmatchcase(full_name, rule.test)):
            return rule
    return None


def failed_tests(results_dir: Path) -> list[tuple[str, str]]:
    """``(name, fullName)`` of every failed or broken test in an Allure results dir."""
    out: list[tuple[str, str]] = []
    if not results_dir.is_dir():
        return out
    for path in sorted(results_dir.rglob("*-result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or str(data.get("status") or "").lower() not in _FAILED:
            continue
        full_name = str(data.get("fullName") or "")
        out.append((str(data.get("name") or full_name or path.stem), full_name))
    return out


def evaluate(rules: tuple[QuarantineRule, ...], results_dir: Path) -> QuarantineVerdict:
    """Split a stage's failed tests into quarantined and not."""
    quarantined: set[str] = set()
    unquarantined: set[str] = set()
    for name, full_name in failed_tests(results_dir):
        if matching_rule(rules, name=name, full_name=full_name) is not None:
            quarantined.add(name)
        else:
            unquarantined.add(name)
    return QuarantineVerdict(
        quarantined=tuple(sorted(quarantined)), unquarantined=tuple(sorted(unquarantined))
    )
