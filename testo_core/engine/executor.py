"""Pure subprocess wrapper used by :mod:`testo_core.engine.orchestrator`.

Responsibilities:

* Resolve the per-stage artifacts layout (``<artifacts>/<plan>/<stage>/``).
* Ask the framework adapter for the argv to launch.
* Spawn the subprocess with stderr merged into stdout for deterministic
  ordering, and tee everything through :class:`LogBuffer`.
* Enforce ``timeout_s`` by sending SIGTERM, then SIGKILL after a short grace.
* Return a :class:`StageResult` describing the outcome.

No Docker, no SSH, no DB.  Future backends (Docker, remote runner) will live
under ``testo_core/engine/backends/`` and adapt to the same return type.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from testo_core.config.schema import Stage
from testo_core.engine.log_buffer import LogBuffer, drain_stream_into_buffer, merged_env
from testo_core.engine.result import StageResult
from testo_core.frameworks.base import FrameworkAdapter, get_adapter
from testo_core.reporting.paths import plan_artifacts_dir, safe_child_path

_TERMINATE_GRACE_S: float = 5.0
_DEFAULT_TAIL_LINES: int = 200

logger = logging.getLogger(__name__)


def _import_junit(
    stage: Stage,
    *,
    target_repo: Path,
    patterns: tuple[str, ...],
    results_dir: Path,
    log_path: Path,
    started_at: float,
) -> None:
    """Post-stage hook: turn the stage's JUnit XML into Allure results.

    Best-effort by design (like the BehaveX report hook): the process exit
    code already decides pass/fail, so a missing or malformed report is
    logged to ``run.log`` rather than raised.
    """
    from testo_core.reporting.junit_import import import_junit_reports

    try:
        imported = import_junit_reports(
            target_repo=target_repo,
            patterns=patterns,
            results_dir=results_dir,
            tool=stage.name,
            not_before=started_at,
        )
        lines = [
            f"[testo] junit_xml: imported {imported.tests} test(s) "
            f"from {len(imported.files)} file(s) matching {list(patterns)}"
        ]
        lines += [f"[testo] junit_xml: skipped malformed report {err}" for err in imported.errors]
    except Exception as exc:  # noqa: BLE001 — never let reporting fail a stage
        logger.warning("junit_xml import failed for stage %s", stage.name, exc_info=True)
        lines = [f"[testo] junit_xml: import failed: {exc}"]
    _append_run_log(log_path, lines)


def _finish_behavex_reports(stage_root: Path, results_dir: Path, *, log_path: Path) -> str | None:
    """Post-stage hook: export BehaveX's ``report.json`` to Allure, and make sure ``report.html`` exists.

    The adapter runs BehaveX without ``--formatter`` so it writes its HTML report;
    the Allure results come from ``report.json`` here. The HTML fallback only does
    work when a stage passed its own ``--formatter`` (BehaveX then skips the HTML).
    Best-effort like :func:`_import_junit`, but the first failure is returned so
    the caller can put it on ``StageResult.error`` (exit code unchanged).
    """
    from testo_core.reporting.behavex_allure import export_behavex_allure_results
    from testo_core.reporting.native_reports import ensure_behavex_report_html

    errors: list[str] = []
    try:
        exported = export_behavex_allure_results(stage_root / "behave_reports", results_dir)
        if exported is not None:
            _append_run_log(
                log_path, [f"[testo] behavex: exported {exported} scenario(s) to Allure"]
            )
    except Exception as exc:  # noqa: BLE001 — BehaveX's formatter raises arbitrary types
        logger.warning("BehaveX Allure export failed in %s", stage_root, exc_info=True)
        errors.append(f"BehaveX Allure export failed: {exc}")
    try:
        ensure_behavex_report_html(stage_root, raise_errors=True)
    except Exception as exc:  # noqa: BLE001 — BehaveX's generator raises arbitrary types
        # native_reports already logged the traceback; here it only becomes stage evidence.
        logger.debug("BehaveX HTML report generation failed in %s", stage_root, exc_info=True)
        errors.append(f"BehaveX HTML report generation failed: {exc}")
    if errors:
        _append_run_log(log_path, [f"[testo] {message}" for message in errors])
    return errors[0] if errors else None


def _append_run_log(log_path: Path, lines: list[str]) -> None:
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n".join(lines) + "\n")
    except OSError:
        logger.warning("could not append to %s", log_path, exc_info=True)


def run_stage(
    stage: Stage,
    *,
    plan_name: str,
    artifacts_root: Path,
    parent_env: Mapping[str, str] | None = None,
    on_chunk: Callable[[bytes], None] | None = None,
    tail_lines: int = _DEFAULT_TAIL_LINES,
) -> StageResult:
    """Execute one stage and return a :class:`StageResult`."""
    adapter: FrameworkAdapter = get_adapter(stage.framework)
    plan_root = plan_artifacts_dir(artifacts_root, plan_name)
    stage_root = safe_child_path(plan_root, stage.name, label="stage name")
    results_dir = (stage_root / "allure-results" / adapter.results_subdir()).resolve()
    stage_root.mkdir(parents=True, exist_ok=True)
    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    log_path = (stage_root / "run.log").resolve()

    target_repo: Path | None = None
    try:
        target_repo = stage.target_repo.expanduser().resolve()
        return _run_resolved_stage(
            stage,
            target_repo=target_repo,
            adapter=adapter,
            artifacts_root=artifacts_root,
            stage_root=stage_root,
            results_dir=results_dir,
            log_path=log_path,
            parent_env=parent_env,
            on_chunk=on_chunk,
            tail_lines=tail_lines,
        )
    except Exception as exc:
        logger.exception("stage %s crashed inside the executor", stage.name)
        now = time.time()
        return StageResult(
            stage_name=stage.name,
            framework=stage.framework,
            tier=stage.tier,
            returncode=4,
            started_at=now,
            finished_at=now,
            duration_s=0.0,
            log_path=None,
            artifacts_dir=stage_root,
            command=(),
            output_tail="",
            error=f"internal error: {exc}",
            internal_failure=True,
            target_repo=target_repo,
        )


def _run_resolved_stage(
    stage: Stage,
    *,
    target_repo: Path,
    adapter: FrameworkAdapter,
    artifacts_root: Path,
    stage_root: Path,
    results_dir: Path,
    log_path: Path,
    parent_env: Mapping[str, str] | None,
    on_chunk: Callable[[bytes], None] | None,
    tail_lines: int,
) -> StageResult:
    argv = adapter.build_argv(
        target_repo=target_repo,
        results_dir=results_dir,
        stage_args=stage.args,
        workers=stage.workers,
    )

    env = merged_env(parent_env if parent_env is not None else os.environ, stage.extra_env)
    env.setdefault("TESTO_LAST_TEST_TYPE", stage.framework)
    env.setdefault("TESTO_ARTIFACTS_ROOT", str(artifacts_root.expanduser().resolve()))
    env["TESTO_SHARED_ALLURE_RESULTS_DIR"] = str(results_dir)
    adapter_env = getattr(adapter, "extra_env", None)
    if adapter_env is not None:
        for key, value in adapter_env().items():
            env.setdefault(key, value)
    # Env that depends on the stage's paths (e.g. where Playwright writes its reports).
    stage_env = getattr(adapter, "stage_env", None)
    if stage_env is not None:
        for key, value in stage_env(target_repo=target_repo, results_dir=results_dir).items():
            env.setdefault(key, value)

    started_at = time.time()
    returncode: int
    timed_out = False
    error: str | None = None

    with LogBuffer(log_path=log_path, on_chunk=on_chunk) as buffer:
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv is built by trusted adapters
                argv,
                cwd=str(target_repo),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                close_fds=True,
            )
        except FileNotFoundError as exc:
            error = f"executable not found: {exc.filename or argv[0]}"
            finished_at = time.time()
            return _failure_result(
                stage=stage,
                started_at=started_at,
                finished_at=finished_at,
                error=error,
                log_path=log_path,
                results_dir=results_dir,
                argv=argv,
                buffer=buffer,
                tail_lines=tail_lines,
                returncode=127,
                target_repo=target_repo,
            )

        assert proc.stdout is not None  # noqa: S101 — we asked for a pipe
        reader = threading.Thread(
            target=drain_stream_into_buffer,
            args=(proc.stdout, buffer),
            name=f"testo-log-reader-{stage.name}",
            daemon=True,
        )
        reader.start()

        try:
            returncode = proc.wait(timeout=stage.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            error = f"stage exceeded timeout_s={stage.timeout_s}"
            _terminate(proc)
            # Timeout contract: rc 124 regardless of the signal the process
            # died from (docs/CLI Commands/Troubleshooting and Error Codes.md).
            returncode = 124

        reader.join(timeout=2.0)
        finished_at = time.time()
        output_tail = buffer.tail(max_lines=tail_lines)

    if stage.framework == "behavex":
        report_error = _finish_behavex_reports(stage_root, results_dir, log_path=log_path)
        # A timeout/launch error is the more important message; keep it.
        error = error or report_error

    junit_patterns: tuple[str, ...] = stage.junit_xml or getattr(adapter, "default_junit_xml", ())
    if junit_patterns:
        _import_junit(
            stage,
            target_repo=target_repo,
            patterns=junit_patterns,
            results_dir=results_dir,
            log_path=log_path,
            started_at=started_at,
        )

    duration = max(0.0, finished_at - started_at)
    return StageResult(
        stage_name=stage.name,
        framework=stage.framework,
        tier=stage.tier,
        returncode=int(returncode),
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration,
        log_path=log_path,
        artifacts_dir=stage_root,
        command=tuple(argv),
        output_tail=output_tail,
        timed_out=timed_out,
        error=error,
        target_repo=target_repo,
    )


def _terminate(proc: subprocess.Popen[bytes]) -> int:
    """Try SIGTERM, then SIGKILL.  Returns the final returncode."""
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        try:
            return proc.wait(timeout=_TERMINATE_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait()
    except (ProcessLookupError, OSError):
        return -1


def _failure_result(
    *,
    stage: Stage,
    started_at: float,
    finished_at: float,
    error: str,
    log_path: Path,
    results_dir: Path,
    argv: list[str],
    buffer: LogBuffer,
    tail_lines: int,
    returncode: int,
    target_repo: Path,
) -> StageResult:
    return StageResult(
        stage_name=stage.name,
        framework=stage.framework,
        tier=stage.tier,
        returncode=int(returncode),
        started_at=started_at,
        finished_at=finished_at,
        duration_s=max(0.0, finished_at - started_at),
        log_path=log_path,
        artifacts_dir=results_dir.parent,
        command=tuple(argv),
        output_tail=buffer.tail(max_lines=tail_lines),
        timed_out=False,
        error=error,
        target_repo=target_repo,
    )
