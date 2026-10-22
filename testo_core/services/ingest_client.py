"""Client side of ``testo ingest --server``: upload JUnit XML to a Testosterone server.

Sends the files plus this job's CI provenance (provider, commit, branch, job)
to ``POST /api/v1/ingest``, where :mod:`testo_core.services.junit_ingest`
records them as a run in the team's shared history.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from testo_core.services.ci_provenance import detect_ci_provenance

UPLOAD_TIMEOUT_S = 120.0


class IngestUploadError(RuntimeError):
    """The server could not be reached, or refused the upload (message says why)."""


def client_run_metadata(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """This job's CI provenance and repository, as the upload's form fields."""
    source = os.environ if env is None else env
    provenance = detect_ci_provenance(source)
    metadata = provenance.to_metadata() if provenance else {}
    repository = (
        source.get("GITHUB_REPOSITORY")
        or source.get("CI_PROJECT_PATH")
        or source.get("BUILDKITE_REPO")
        or source.get("CIRCLE_PROJECT_REPONAME")
    )
    if repository:
        metadata["repository"] = repository
    return metadata


def upload_reports(
    *,
    server: str,
    token: str | None,
    cycle: str,
    files: list[Path],
    stage: str = "junit",
    tier: str = "unit",
    metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """POST *files* to *server*'s ingest endpoint; return the recorded run as JSON."""
    import requests

    url = f"{server.rstrip('/')}/api/v1/ingest"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = {"cycle": cycle, "stage": stage, "tier": tier, **dict(metadata or {})}
    with ExitStack() as stack:
        parts = [
            ("files", (path.name, stack.enter_context(path.open("rb")), "application/xml"))
            for path in files
        ]
        try:
            resp = requests.post(
                url, data=data, files=parts, headers=headers, timeout=UPLOAD_TIMEOUT_S
            )
        except requests.RequestException as exc:
            raise IngestUploadError(f"could not reach {url}: {exc}") from exc

    if resp.status_code != 201:
        raise IngestUploadError(f"{url} answered {resp.status_code}: {_error_message(resp)}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise IngestUploadError(f"{url} answered with something that is not JSON.") from exc
    if not isinstance(body, dict):
        raise IngestUploadError(f"{url} answered with unexpected JSON.")
    return body


def _error_message(resp: Any) -> str:
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:300] or "no details"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return str(body)[:300]
