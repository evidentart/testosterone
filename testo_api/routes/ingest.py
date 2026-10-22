"""``POST /api/v1/ingest``: record uploaded JUnit XML as a run (``testo ingest --server``)."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from testo_api.models import IngestResponse
from testo_api.ui import ui_dir
from testo_core.config.errors import ConfigError, ConfigValidationError
from testo_core.config.loader import load_config_or_defaults
from testo_core.services.junit_ingest import (
    MAX_FILE_BYTES,
    clean_run_metadata,
    ingest_uploaded_reports,
)

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse, status_code=201)
def ingest_reports(
    request: Request,
    files: list[UploadFile],
    cycle: str = Form(...),
    stage: str = Form("junit"),
    tier: str = Form("unit"),
    ci_provider: str | None = Form(None),
    ci_pipeline_id: str | None = Form(None),
    ci_job_id: str | None = Form(None),
    ci_commit_sha: str | None = Form(None),
    ci_ref_name: str | None = Form(None),
    repository: str | None = Form(None),
) -> IngestResponse:
    """Record JUnit XML files as one run of *cycle*. Nothing in the upload is executed.

    ``exit_code`` follows ``testo run``: 0 when every test passed or was skipped,
    1 when one failed. Needs ``Authorization: Bearer <TESTO_API_TOKEN>`` when the
    server has a token set, like every other write.
    """
    try:
        cfg = load_config_or_defaults()
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=f"config error: {exc}") from exc

    reports: list[tuple[str, bytes]] = []
    for upload in files:
        # Read one byte past the limit so an oversized file is rejected, not truncated.
        content = upload.file.read(MAX_FILE_BYTES + 1)
        reports.append((upload.filename or "report.xml", content))

    metadata = clean_run_metadata(
        {
            "ci_provider": ci_provider,
            "ci_pipeline_id": ci_pipeline_id,
            "ci_job_id": ci_job_id,
            "ci_commit_sha": ci_commit_sha,
            "ci_ref_name": ci_ref_name,
            "repository": repository,
        }
    )
    try:
        outcome = ingest_uploaded_reports(
            cfg=cfg,
            cycle=cycle.strip(),
            reports=reports,
            stage=stage.strip(),
            tier=tier.strip().lower(),
            run_metadata=metadata,
        )
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = str(request.base_url).rstrip("/")
    return IngestResponse(
        run_id=outcome.run_id,
        cycle=outcome.cycle,
        exit_code=outcome.exit_code,
        tests=outcome.tests,
        passed=outcome.passed,
        failed=outcome.failed,
        skipped=outcome.skipped,
        # A page link only when this process serves the UI (the team server does).
        run_url=f"{base}/runs/{outcome.run_id}" if outcome.run_id and ui_dir() else None,
    )
