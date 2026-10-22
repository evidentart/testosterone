"""GitHub Actions wrapper around ``testo run --ci``.

Runs one cycle, echoes the NDJSON event stream, and turns the final
``plan_finished`` event into step outputs (``exit_code``, ``status``,
``summary_json``, ``summary_path``).

With the run persisted, it also renders the run as Markdown
(``testo report markdown``) for the job summary and, when asked, for one
pull request comment per cycle that later runs edit in place; prints failing
tests as annotations on the diff (``testo report annotations``); sends a Slack
or Teams alert when a webhook secret is given (``testo notify``); and, when
asked, opens one issue per newly flaky test (``testo flaky --new``). All of
it is best-effort: a failure there is a warning, never a changed exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_COMMENT_EVENTS = {"pull_request", "pull_request_target"}


def _parse_bool(value: str, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def build_command(*, config_path: str, cycle: str, ci_mode: bool, persist: bool) -> list[str]:
    cmd = ["testo", "run"]
    if config_path:
        cmd += ["--config", config_path]
    if cycle:
        cmd += ["--cycle", cycle]
    if ci_mode:
        cmd.append("--ci")
    if not persist:
        cmd.append("--no-persist")
    return cmd


def _extract_summary(stdout: str, *, fallback_exit_code: int) -> dict[str, Any]:
    """Return the last NDJSON object carrying an ``exit_code`` (``plan_finished`` or ``error``)."""
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "exit_code" in payload:
            return payload
    return {
        "event": "error",
        "error": "Unable to parse a plan_finished event from testo output.",
        "exit_code": int(fallback_exit_code),
    }


def _status_from_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return "success"
    if exit_code == 1:
        return "failure"
    if exit_code == 2:
        return "invalid_input"
    if exit_code == 3:
        return "infra_failure"
    return "internal_error"


def _write_github_outputs(path: Path, *, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")


def _warn(message: str) -> None:
    print(f"::warning title=testo::{message}", file=sys.stderr)


def render_markdown(*, cycle: str, env: dict[str, str]) -> str | None:
    """``testo report markdown`` for the run that just finished, or ``None``."""
    cmd = ["testo", "report", "markdown"]
    if cycle and cycle != "all":
        cmd += ["--cycle", cycle]
    server, repo, run_id = (
        env.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    )
    if server and repo and run_id:
        cmd += ["--run-url", f"{server}/{repo}/actions/runs/{run_id}"]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)  # noqa: S603
    if proc.returncode != 0 or not proc.stdout.strip():
        _warn(f"could not render the run summary: {proc.stderr.strip() or proc.returncode}")
        return None
    return proc.stdout


def pull_request_number(env: dict[str, str]) -> int | None:
    """The pull request this workflow run belongs to, from the event payload."""
    if env.get("GITHUB_EVENT_NAME") not in _COMMENT_EVENTS:
        return None
    try:
        event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        return int(event["pull_request"]["number"])
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _github(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> Any:
    request = urllib.request.Request(  # noqa: S310 - the GitHub API URL comes from the runner
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read() or b"null")


def upsert_pr_comment(*, markdown: str, number: int, token: str, env: dict[str, str]) -> str:
    """Edit this cycle's earlier comment on the pull request, or post a new one."""
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    base = f"{api}/repos/{env['GITHUB_REPOSITORY']}/issues"
    marker = markdown.splitlines()[0]
    for page in range(1, 11):
        comments = _github("GET", f"{base}/{number}/comments?per_page=100&page={page}", token)
        for comment in comments:
            if str(comment.get("body") or "").startswith(marker):
                _github("PATCH", f"{base}/comments/{comment['id']}", token, {"body": markdown})
                return "updated"
        if len(comments) < 100:
            break
    _github("POST", f"{base}/{number}/comments", token, {"body": markdown})
    return "created"


def publish_summary(*, cycle: str, job_summary: bool, comment: bool, env: dict[str, str]) -> None:
    if not (job_summary or comment):
        return
    markdown = render_markdown(cycle=cycle, env=env)
    if markdown is None:
        return
    step_summary = env.get("GITHUB_STEP_SUMMARY")
    if job_summary and step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as fh:
            fh.write(markdown)
    if not comment:
        return
    number = pull_request_number(env)
    token = env.get("TESTO_GITHUB_TOKEN", "")
    if number is None or not token:
        return
    try:
        upsert_pr_comment(markdown=markdown, number=number, token=token, env=env)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        # A fork's pull request gets a read-only token: say so, keep the job's result.
        _warn(f"could not comment on pull request #{number} ({exc}); it needs pull-requests: write")


def _testo(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["testo", *cmd], check=False, capture_output=True, text=True, env=env
    )


def _run_url(env: dict[str, str]) -> str | None:
    server, repo, run_id = (
        env.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    )
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None


def annotate(*, cycle: str, config_path: str, env: dict[str, str]) -> None:
    """Print ``testo report annotations`` so GitHub puts failing tests on the diff."""
    cmd = ["report", "annotations", "--cycle", cycle]
    if env.get("GITHUB_WORKSPACE"):
        cmd += ["--workspace", env["GITHUB_WORKSPACE"]]
    if config_path:
        cmd += ["--config", config_path]
    proc = _testo(cmd, env)
    if proc.returncode != 0:
        _warn(f"could not annotate failing tests: {proc.stderr.strip() or proc.returncode}")
        return
    sys.stdout.write(proc.stdout)


def notify(*, cycle: str, when: str, env: dict[str, str]) -> None:
    """``testo notify`` to every chat whose webhook secret was passed in."""
    channels = [
        c for c in ("slack", "teams") if env.get(f"TESTO_{c.upper()}_WEBHOOK_URL", "").strip()
    ]
    if not channels:
        return
    cmd = ["notify", "--cycle", cycle, "--when", when or "failure"]
    for channel in channels:
        cmd += ["--to", channel]
    run_url = _run_url(env)
    if run_url:
        cmd += ["--run-url", run_url]
    proc = _testo(cmd, env)
    if proc.returncode != 0:
        _warn(f"could not send the chat alert: {proc.stderr.strip() or proc.returncode}")


FLAKY_LABEL = "flaky-test"


def flaky_issue_title(*, name: str, cycle: str) -> str:
    return f"Flaky test: {name} ({cycle})"


def _flaky_issue_body(test: dict[str, Any], *, cycle: str, run_url: str | None) -> str:
    marks = {"passed": "✅", "failed": "❌", "broken": "❌"}
    history = "".join(marks.get(str(s), "·") for s in test.get("history") or [])
    lines = [
        f"`{test.get('name')}` in cycle `{cycle}` started flipping between passing and failing.",
        "",
        f"- Last {test.get('runs')} runs: {test.get('passed')} passed, {test.get('failed')} failed,"
        f" {test.get('flips')} flips",
        f"- History, oldest to newest: {history}",
    ]
    if run_url:
        lines.append(f"- Found by [this workflow run]({run_url})")
    lines += [
        "",
        f"Check it locally with `testo flaky --cycle {cycle}`. Close this issue once it is fixed.",
        "",
        "<sub>Opened by [Testosterone](https://github.com/taltal-beep/testosterone)</sub>",
    ]
    return "\n".join(lines)


def open_flaky_issues(*, cycle: str, token: str, env: dict[str, str]) -> None:
    """One issue per test the latest run made flaky, unless an open issue already has its title."""
    proc = _testo(["flaky", "--cycle", cycle, "--new", "--json"], env)
    if proc.returncode != 0:
        _warn(f"could not check for flaky tests: {proc.stderr.strip() or proc.returncode}")
        return
    tests = json.loads(proc.stdout or "{}").get("flaky") or []
    if not tests or not token:
        return
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    base = f"{api}/repos/{env['GITHUB_REPOSITORY']}/issues"
    try:
        existing: set[str] = set()
        for page in range(1, 11):
            issues = _github("GET", f"{base}?state=open&per_page=100&page={page}", token)
            existing |= {str(i.get("title")) for i in issues}
            if len(issues) < 100:
                break
        for test in tests:
            title = flaky_issue_title(name=str(test.get("name")), cycle=cycle)
            if title in existing:
                continue
            body = _flaky_issue_body(test, cycle=cycle, run_url=_run_url(env))
            _github("POST", base, token, {"title": title, "body": body, "labels": [FLAKY_LABEL]})
            existing.add(title)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        _warn(f"could not open flaky test issues ({exc}); it needs issues: write")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Testosterone cycle in GitHub Actions.")
    parser.add_argument("--config-path", default="")
    parser.add_argument("--cycle", default="")
    parser.add_argument("--ci-mode", default="true")
    parser.add_argument("--persist", default="true")
    parser.add_argument("--summary-path", default="")
    parser.add_argument("--job-summary", default="true")
    parser.add_argument("--comment-on-pr", default="false")
    parser.add_argument("--annotations", default="true")
    parser.add_argument("--notify-when", default="failure")
    parser.add_argument("--flaky-issues", default="false")
    args = parser.parse_args(argv)

    persist = _parse_bool(args.persist, default=True)
    cmd = build_command(
        config_path=str(args.config_path or "").strip(),
        cycle=str(args.cycle or "").strip(),
        ci_mode=_parse_bool(args.ci_mode, default=True),
        persist=persist,
    )

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=os.environ.copy())  # noqa: S603
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    summary = _extract_summary(proc.stdout or "", fallback_exit_code=int(proc.returncode))
    summary_json = json.dumps(summary, separators=(",", ":"), ensure_ascii=True)

    summary_path_arg = str(args.summary_path or "").strip()
    if not summary_path_arg:
        runner_temp = os.getenv("RUNNER_TEMP", ".")
        summary_path = Path(runner_temp) / "testo-summary.json"
    else:
        summary_path = Path(summary_path_arg)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_json + "\n", encoding="utf-8")

    outputs = {
        "exit_code": str(proc.returncode),
        "summary_json": summary_json,
        "summary_path": str(summary_path),
        "status": _status_from_exit_code(int(proc.returncode)),
    }
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        _write_github_outputs(Path(github_output), values=outputs)

    # Everything below reads the run back from the run history, which --no-persist skips.
    if persist:
        env = os.environ.copy()
        publish_summary(
            cycle=str(args.cycle or "").strip(),
            job_summary=_parse_bool(args.job_summary, default=True),
            comment=_parse_bool(args.comment_on_pr, default=False),
            env=env,
        )
        cycle = str(args.cycle or "").strip()
        if not cycle or cycle == "all":
            cycle = str(summary.get("plan") or "")
        if cycle:
            if _parse_bool(args.annotations, default=True):
                annotate(cycle=cycle, config_path=str(args.config_path or "").strip(), env=env)
            notify(cycle=cycle, when=str(args.notify_when or "").strip(), env=env)
            if _parse_bool(args.flaky_issues, default=False):
                open_flaky_issues(cycle=cycle, token=env.get("TESTO_GITHUB_TOKEN", ""), env=env)

    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
