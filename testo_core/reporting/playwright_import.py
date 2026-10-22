"""Convert Playwright Test's JSON report into Allure ``*-result.json`` files.

JUnit (see :mod:`testo_core.reporting.junit_import`) keeps only the last
attempt of each test. Playwright's ``json`` reporter keeps everything, so this
importer also records:

- **retries**: one Allure result per test (so totals count tests, not
  attempts), with every attempt as a step carrying its own status, duration,
  error and attachments. A test that passed on retry is ``passed`` with
  ``statusDetails.flaky`` set, which Allure shows as flaky.
- **attachments**: traces (``trace.zip``), screenshots, videos, ``error-context.md``
  and ``testInfo.attach()`` bodies are copied next to the result as Allure
  attachments, so ``testo report allure`` shows them.
- **projects and tags**: the Playwright project (``chromium``, ``api``...) is a
  parameter and part of the test's identity; ``@tags`` become Allure tags.

Status mapping (Playwright test status -> Allure):

    expected     -> passed (skipped if the test was skipped)
    flaky        -> passed, flaky
    skipped      -> skipped
    unexpected   -> failed (broken if the last attempt was interrupted)

Attachments are read from disk only inside ``attachments_root``. Playwright
writes absolute paths; when a report was produced elsewhere (a CI artifact
downloaded to a laptop) the path's tail is looked up under that root instead.
A file outside the root, missing, or over ``max_attachment_bytes`` is skipped.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_MAX_TRACE_CHARS = 20_000
_DEFAULT_MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_ATTEMPT_STATUS = {
    "passed": "passed",
    "failed": "failed",
    "timedOut": "failed",
    "skipped": "skipped",
    "interrupted": "broken",
}


@dataclass(frozen=True)
class PlaywrightFileResults:
    results: list[dict]
    flaky: int
    attachments: int
    notes: tuple[str, ...]


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = _ANSI.sub("", text).strip()
    if len(text) > _MAX_TRACE_CHARS:
        text = text[:_MAX_TRACE_CHARS] + "\n… (truncated)"
    return text or None


def _start_ms(value: Any, fallback_ms: int) -> int:
    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            pass
    return fallback_ms


def _ms(value: Any) -> int:
    try:
        return max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        return 0


def _error_details(attempt: dict) -> dict[str, Any]:
    error = attempt.get("error") if isinstance(attempt.get("error"), dict) else None
    if error is None:
        errors = attempt.get("errors") or []
        error = errors[0] if errors and isinstance(errors[0], dict) else None
    if error is None:
        return {}
    message = _clean(error.get("message"))
    trace = _clean(error.get("stack")) or message
    details: dict[str, Any] = {}
    if message:
        details["message"] = message.splitlines()[0]
    if trace:
        details["trace"] = trace
    return details


class _Attachments:
    """Copies attachment files/bodies into ``results_dir``, bounded by root and size."""

    def __init__(self, results_dir: Path, root: Path | None, max_bytes: int) -> None:
        self.results_dir = results_dir
        self.root = root
        self.max_bytes = max_bytes
        self.count = 0
        self.skipped: list[str] = []

    def _locate(self, raw: str) -> Path | None:
        if self.root is None:
            return None
        path = Path(raw)
        candidates = [path] if path.is_absolute() else [self.root / path]
        # A report made on another machine: look for its tail under root.
        parts = path.parts
        for depth in (3, 2, 1):
            if len(parts) >= depth:
                candidates.append(self.root / Path(*parts[-depth:]))
                candidates.append(self.root / "test-results" / Path(*parts[-depth:]))
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file() and (resolved == self.root or self.root in resolved.parents):
                return resolved
        return None

    def add(self, attachment: dict) -> dict | None:
        name = str(attachment.get("name") or "attachment")
        content_type = str(attachment.get("contentType") or "application/octet-stream")
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
        raw_path = attachment.get("path")
        source = None
        if isinstance(raw_path, str) and raw_path:
            source = self._locate(raw_path)
            if source is None:
                self.skipped.append(
                    f"{name}: {Path(raw_path).name} not found under the report root"
                )
                return None
            if source.stat().st_size > self.max_bytes:
                self.skipped.append(f"{name}: {source.name} is over the size limit")
                return None
            ext = source.suffix or ext
        target = f"{uuid.uuid4()}-attachment{ext}"
        if source is not None:
            shutil.copyfile(source, self.results_dir / target)
        else:
            body = attachment.get("body")
            if not isinstance(body, str):
                return None
            try:
                data = base64.b64decode(body, validate=True)
            except (binascii.Error, ValueError):
                data = body.encode("utf-8")
            if len(data) > self.max_bytes:
                self.skipped.append(f"{name}: body is over the size limit")
                return None
            (self.results_dir / target).write_bytes(data)
        self.count += 1
        return {"name": name, "source": target, "type": content_type}


def _test_status(test: dict, attempts: list[dict]) -> tuple[str, bool]:
    """Allure status for a Playwright test, and whether it was flaky."""
    outcome = test.get("status")
    last = _ATTEMPT_STATUS.get(str(attempts[-1].get("status")), "broken") if attempts else "skipped"
    if outcome == "flaky":
        return "passed", True
    if outcome == "skipped":
        return "skipped", False
    if outcome == "expected":
        return ("skipped" if last == "skipped" else "passed"), False
    # unexpected: failed, timed out, interrupted, or a test.fail() that passed.
    return ("broken" if last == "broken" else "failed"), False


def _walk(suite: dict, titles: tuple[str, ...]):
    for spec in suite.get("specs") or []:
        yield titles, spec
    for child in suite.get("suites") or []:
        yield from _walk(child, (*titles, str(child.get("title") or "")))


def _results_for_report(
    report: dict, *, tool: str, fallback_ms: int, attachments: _Attachments
) -> tuple[list[dict], int]:
    results: list[dict] = []
    flaky_count = 0
    for top in report.get("suites") or []:
        file_title = str(top.get("file") or top.get("title") or "")
        for titles, spec in _walk(top, ()):
            spec_title = str(spec.get("title") or "(unnamed)")
            tags = [str(t).lstrip("@") for t in spec.get("tags") or []]
            for test in spec.get("tests") or []:
                project = str(test.get("projectName") or "")
                attempts = [a for a in test.get("results") or [] if isinstance(a, dict)]
                status, flaky = _test_status(test, attempts)
                flaky_count += flaky
                path = " › ".join(t for t in (file_title, *titles, spec_title) if t)
                full_name = f"{path} [{project}]" if project else path

                steps: list[dict] = []
                clock = (
                    _start_ms(attempts[0].get("startTime"), fallback_ms)
                    if attempts
                    else fallback_ms
                )
                start = clock
                for attempt in attempts:
                    a_start = _start_ms(attempt.get("startTime"), clock)
                    a_stop = a_start + _ms(attempt.get("duration"))
                    clock = a_stop
                    step: dict = {
                        "name": f"Attempt {_ms(attempt.get('retry')) + 1}",
                        "status": _ATTEMPT_STATUS.get(str(attempt.get("status")), "broken"),
                        "stage": "finished",
                        "start": a_start,
                        "stop": a_stop,
                        "attachments": [
                            added
                            for raw in attempt.get("attachments") or []
                            if isinstance(raw, dict) and (added := attachments.add(raw))
                        ],
                    }
                    if details := _error_details(attempt):
                        step["statusDetails"] = details
                    steps.append(step)

                result: dict = {
                    "uuid": str(uuid.uuid4()),
                    "historyId": hashlib.sha256(f"{tool}:{full_name}".encode()).hexdigest(),
                    "name": spec_title,
                    "fullName": full_name,
                    "status": status,
                    "stage": "finished",
                    "start": start,
                    "stop": max(start, clock),
                    "labels": [
                        {"name": "suite", "value": file_title},
                        *([{"name": "subSuite", "value": " › ".join(titles)}] if titles else []),
                        {"name": "framework", "value": "playwright"},
                        {"name": "language", "value": "javascript"},
                        *[{"name": "tag", "value": tag} for tag in tags],
                    ],
                    "parameters": [
                        *([{"name": "project", "value": project}] if project else []),
                        {"name": "attempts", "value": str(len(attempts))},
                    ],
                    "steps": steps,
                }
                # Last attempt's attachments also go on the test, where Allure shows them first.
                if steps and steps[-1]["attachments"]:
                    result["attachments"] = steps[-1]["attachments"]
                details = {}
                failing = next(
                    (s for s in reversed(steps) if s["status"] in ("failed", "broken")), None
                )
                if status in ("failed", "broken") and failing is not None:
                    details.update(failing.get("statusDetails") or {})
                    if not details:
                        details["message"] = f"Attempt ended {attempts[-1].get('status')}"
                elif status == "failed" and attempts:
                    details["message"] = "Expected to fail, but passed"
                if flaky:
                    details["flaky"] = True
                    retried = next((s for s in steps if s["status"] != "passed"), None)
                    if retried is not None and "statusDetails" in retried:
                        details["message"] = "Passed on retry. " + retried["statusDetails"].get(
                            "message", ""
                        )
                skip_reason = next(
                    (
                        a.get("description")
                        for a in test.get("annotations") or []
                        if isinstance(a, dict) and a.get("type") in ("skip", "fixme")
                    ),
                    None,
                )
                if status == "skipped" and skip_reason:
                    details["message"] = str(skip_reason)
                if details:
                    result["statusDetails"] = details
                results.append(result)
    return results, flaky_count


def playwright_results_for_file(
    path: Path,
    *,
    tool: str,
    results_dir: Path,
    attachments_root: Path | None,
    max_attachment_bytes: int = _DEFAULT_MAX_ATTACHMENT_BYTES,
) -> PlaywrightFileResults:
    """Allure result dicts for one Playwright JSON report; attachments are written to ``results_dir``.

    ``attachments_root`` bounds which files may be copied (``None``: inline
    bodies only, never files). A file that isn't a Playwright report raises
    :class:`ValueError`; skipped attachments and the report's own top-level
    errors come back in ``notes``.
    """
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON ({exc})") from exc
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        raise ValueError("not a Playwright JSON report (no 'suites' list)")

    results_dir.mkdir(parents=True, exist_ok=True)
    root = attachments_root.expanduser().resolve() if attachments_root is not None else None
    attachments = _Attachments(results_dir, root, max_attachment_bytes)
    stats = report.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    fallback_ms = _start_ms(stats.get("startTime"), int(path.stat().st_mtime * 1000))
    results, flaky = _results_for_report(
        report, tool=tool, fallback_ms=fallback_ms, attachments=attachments
    )
    notes = [
        f"report error: {(_clean(e.get('message')) or 'error').splitlines()[0]}"
        for e in report.get("errors") or []
        if isinstance(e, dict)
    ]
    notes += [f"attachment skipped: {s}" for s in attachments.skipped]
    return PlaywrightFileResults(
        results=results, flaky=flaky, attachments=attachments.count, notes=tuple(notes)
    )
