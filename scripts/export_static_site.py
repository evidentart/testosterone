#!/usr/bin/env python3
"""Freeze the Testo API into JSON files so the React UI can run without a backend.

GitLab Pages (and any other static host) serves files, not processes, so the
FastAPI app cannot be published there. This script calls every read-only
endpoint the UI uses *in-process* — through ``TestClient``, against the same
``create_app()`` the real server runs — and writes each response body to a file
under ``<out>/data/``. The frontend, built with ``VITE_STATIC_DATA_BASE``,
installs a fetch shim that maps API requests onto those files
(``frontend/src/lib/static-backend.ts``), so payloads are the real ones rather
than fixtures invented for the demo.

Allure/native HTML reports already live under ``static/history/<run_id>/`` after
a run; they are copied next to the data so the report links on the Run detail
and Dashboard pages resolve on Pages too.

A static site cannot call an AI provider when a visitor clicks "Generate AI
Summary", so when ``ANTHROPIC_API_KEY`` is set the export generates the summary
for each failed run first, through the same endpoint the button calls, and
freezes the result. Without a key the failed runs keep their "no summary"
payload and the UI explains that summaries are generated live. A generated
summary is stored with the run, so later exports reuse it instead of paying
for it again.

Only cycles that have a run in the export are published: a cycle card with no
history would lead nowhere on a site that cannot start runs.

Usage::

    python scripts/export_static_site.py --out public --runs 5 \\
        --site-url "$CI_PAGES_URL"

The layout it writes is the contract shared with ``static-backend.ts``:

    data/manifest.json                     provenance + the exported run ids
    data/health.json                       GET /api/v1/health/ready
    data/ai-config.json                    GET /api/v1/ai/config/status
    data/cycles.json                       GET /api/v1/cycles (cycles that ran)
    data/cycles/<name>.json                GET /api/v1/cycles/{name}
    data/flaky/<name>.json                 GET /api/v1/analytics/flaky?cycle={name}
    data/runs.json                         GET /api/v1/runs
    data/runs/<run_id>/detail.json         GET /api/v1/runs/{id}
    data/runs/<run_id>/reports.json        GET /api/v1/runs/{id}/reports
    data/runs/<run_id>/pyramid.json        GET /api/v1/runs/{id}/pyramid
    data/runs/<run_id>/ai-summary.json     GET /api/v1/runs/{id}/ai-summary
    data/dashboard/overview.json           GET /api/v1/dashboard/overview
    data/dashboard/recent-runs.json        GET /api/v1/dashboard/runs/recent
    data/delta/<current>__<baseline>/comparison.json
    data/delta/<current>__<baseline>/cases.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

# Model for the frozen AI summaries; override with TESTO_DEMO_AI_MODEL. The
# Anthropic provider sends a sampling temperature and reads the first content
# block, so it needs a model without always-on thinking.
DEFAULT_DEMO_AI_MODEL = "claude-haiku-4-5"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _scrub(payload: Any) -> Any:
    """Make checkout-absolute paths relative before they are published.

    Several payloads echo filesystem paths (the resolved ``testosterone.yaml``,
    artifact snapshot dirs). On a public site those would expose the CI runner's
    directory layout and read as noise, so the checkout root is stripped.
    """
    root = str(REPO_ROOT)
    if isinstance(payload, str):
        return payload.replace(root + "/", "").replace(root, ".")
    if isinstance(payload, list):
        return [_scrub(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _scrub(value) for key, value in payload.items()}
    return payload


def _ran_cycles_only(listing: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the cycles that have at least one exported run, in config order."""
    ran = {run.get("cycle") for run in runs}
    return {**listing, "items": [c for c in listing.get("items", []) if c.get("name") in ran]}


class Exporter:
    """Writes one JSON file per read-only endpoint the UI calls."""

    def __init__(self, *, out_dir: Path, site_url: str, run_limit: int, delta_pairs: int) -> None:
        from fastapi.testclient import TestClient

        # The export switches AI on for its own run; keep that out of the local settings file.
        os.environ["TESTO_AI_SETTINGS_PATH"] = ""
        from testo_api.main import create_app

        self.out_dir = out_dir
        self.data_dir = out_dir / "data"
        self.site_url = site_url.rstrip("/")
        self.run_limit = run_limit
        self.delta_pairs = delta_pairs
        self.client = TestClient(create_app())
        self.written: list[str] = []
        self.skipped: list[str] = []
        self.ai_summaries = 0

    # --- plumbing -----------------------------------------------------------

    def _get(self, path: str) -> Any | None:
        """GET ``path``, returning the decoded body, or None when it is unusable.

        ``/health/ready`` answers 503 when a check is degraded while still carrying
        its payload, which is exactly what the UI renders, so non-2xx bodies are
        kept when they parse.
        """
        resp = self.client.get(path)
        try:
            body = resp.json()
        except ValueError:
            self.skipped.append(f"{path} (status {resp.status_code}, non-JSON body)")
            return None
        if resp.status_code >= 400 and not isinstance(body, dict):
            self.skipped.append(f"{path} (status {resp.status_code})")
            return None
        if resp.status_code >= 400 and "error" in body:
            self.skipped.append(f"{path} (status {resp.status_code}: {body['error'].get('code')})")
            return None
        return body

    def _write(self, rel_path: str, payload: Any) -> None:
        target = self.data_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(_scrub(payload), indent=2, sort_keys=True) + "\n"
        target.write_text(text, encoding="utf-8")
        self.written.append(rel_path)

    def _dump(self, api_path: str, rel_path: str) -> Any | None:
        payload = self._get(api_path)
        if payload is None:
            return None
        self._write(rel_path, payload)
        return payload

    # --- endpoint groups ----------------------------------------------------

    def export_runs(self) -> list[dict[str, Any]]:
        listing = self._get(f"/api/v1/runs?limit={self.run_limit}")
        items: list[dict[str, Any]] = list(listing.get("items", [])) if listing else []
        items = items[: self.run_limit]
        self._write("runs.json", {"items": items})

        failed = [item["run_id"] for item in items if item.get("returncode") not in (0, None)]
        self.generate_ai_summaries(failed)

        for item in items:
            run_id = item["run_id"]
            base = f"runs/{run_id}"
            self._dump(f"/api/v1/runs/{run_id}", f"{base}/detail.json")
            self._dump(f"/api/v1/runs/{run_id}/reports", f"{base}/reports.json")
            self._dump(f"/api/v1/runs/{run_id}/pyramid", f"{base}/pyramid.json")
            self._dump(f"/api/v1/runs/{run_id}/ai-summary", f"{base}/ai-summary.json")
        return items

    def generate_ai_summaries(self, run_ids: list[str]) -> None:
        """Generate (or reuse) the AI failure summary of each run, if a key is set.

        Goes through the API like the UI's "Generate AI Summary" button does:
        enable the Anthropic provider with the key from the environment, then
        ask for each run's summary. The key itself is never written anywhere;
        only the summary text ends up in ``ai-summary.json``.
        """
        if not run_ids or not os.getenv("ANTHROPIC_API_KEY"):
            return
        resp = self.client.put(
            "/api/v1/ai/config",
            json={
                "enabled": True,
                "provider": "anthropic",
                "model": os.getenv("TESTO_DEMO_AI_MODEL") or DEFAULT_DEMO_AI_MODEL,
                "api_key_source": "env",
                # One attempt per run, bounded, so a slow provider cannot stall the deploy.
                "timeout_s": 30,
                "retry_count": 0,
            },
        )
        if resp.status_code != 200:
            self.skipped.append(f"AI summaries (config rejected: status {resp.status_code})")
            return
        for run_id in run_ids:
            # Optional feature: whatever goes wrong here must not stop the site from publishing.
            try:
                summary = self.client.post(
                    f"/api/v1/runs/{run_id}/ai-summary:generate", json={"force_refresh": False}
                ).json()
            except Exception as exc:  # noqa: BLE001
                self.skipped.append(f"AI summary for {run_id} ({type(exc).__name__})")
                continue
            if summary.get("status") == "available":
                self.ai_summaries += 1
            else:
                self.skipped.append(f"AI summary for {run_id} ({summary.get('error_code')})")

    def export_cycles(self, runs: list[dict[str, Any]]) -> None:
        listing = self._get("/api/v1/cycles")
        if listing is None:
            return
        listing = _ran_cycles_only(listing, runs)
        self._write("cycles.json", listing)
        for cycle in listing["items"]:
            name = cycle["name"]
            self._dump(f"/api/v1/cycles/{quote(name, safe='')}", f"cycles/{name}.json")
            self._dump(
                f"/api/v1/analytics/flaky?cycle={quote(name, safe='')}", f"flaky/{name}.json"
            )

    def export_dashboard(self) -> None:
        overview = self._get("/api/v1/dashboard/overview?recent_limit=6")
        if overview is not None:
            self._write("dashboard/overview.json", self._absolutize_report_links(overview))
        self._dump("/api/v1/dashboard/runs/recent?limit=8", "dashboard/recent-runs.json")

    def export_deltas(self, runs: list[dict[str, Any]]) -> list[list[str]]:
        """Export the run pairs the UI can ask for.

        The Dashboard and Runs pages only ever compare a run with the previous
        run of the same cycle (this run of ``fake-api`` against the previous
        one), so those are the pairs exported, newest first across cycles.
        """
        pairs: list[tuple[str, str]] = []
        previous_by_cycle: dict[str | None, str] = {}
        for run in reversed(runs):  # oldest first
            cycle = run.get("cycle")
            if cycle in previous_by_cycle:
                pairs.append((run["run_id"], previous_by_cycle[cycle]))
            previous_by_cycle[cycle] = run["run_id"]
        pairs.reverse()

        exported: list[list[str]] = []
        for current, baseline in pairs[: self.delta_pairs]:
            folder = f"delta/{current}__{baseline}"
            comparison = self._dump(
                f"/api/v1/analytics/delta?current_run_id={current}&baseline_run_id={baseline}",
                f"{folder}/comparison.json",
            )
            if comparison is None:
                continue
            self._dump(
                f"/api/v1/analytics/delta/cases?current_run_id={current}&baseline_run_id={baseline}",
                f"{folder}/cases.json",
            )
            exported.append([current, baseline])
        return exported

    def export_misc(self) -> None:
        self._dump("/api/v1/health/ready", "health.json")
        self._dump("/api/v1/ai/config/status", "ai-config.json")

    # --- report HTML --------------------------------------------------------

    def copy_reports(self, runs: list[dict[str, Any]]) -> int:
        """Copy ``static/history/<run_id>/`` for each exported run into the site."""
        from testo_core.paths import STATIC_HISTORY_ROOT

        copied = 0
        for item in runs:
            src = Path(STATIC_HISTORY_ROOT) / item["run_id"]
            if not src.is_dir():
                self.skipped.append(f"report html for {item['run_id']} (no {src})")
                continue
            dst = self.out_dir / "history" / item["run_id"]
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied += 1
        return copied

    def _absolutize_report_links(self, overview: dict[str, Any]) -> dict[str, Any]:
        """Make dashboard report links absolute.

        The dashboard hands the UI paths relative to the API's ``/history`` mount
        and the UI uses them verbatim in ``href``, which on a static host would
        resolve against whatever page the user is on. Rewriting them against the
        published site URL keeps those links working from every route.
        """
        if not self.site_url:
            return overview
        links = overview.get("report_links") or {}
        for link in links.values():
            url = link.get("url") if isinstance(link, dict) else None
            if isinstance(url, str) and url.startswith("history/"):
                link["url"] = f"{self.site_url}/{url}"
        return overview

    # --- entry point --------------------------------------------------------

    def run(self) -> int:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Before export_runs(): generating AI summaries switches the in-process
        # provider on, and the published settings should describe the snapshot.
        self.export_misc()
        runs = self.export_runs()
        if not runs:
            print("error: no runs in the history database — run a cycle first.", file=sys.stderr)
            return 1
        self.export_cycles(runs)
        self.export_dashboard()
        deltas = self.export_deltas(runs)
        copied = self.copy_reports(runs)

        self._write(
            "manifest.json",
            {
                "mode": "static",
                "generated_at": time.time(),
                "site_url": self.site_url or None,
                "run_ids": [r["run_id"] for r in runs],
                "latest_run_id": runs[0]["run_id"],
                "delta_pairs": deltas,
                "commit": os.getenv("CI_COMMIT_SHA") or _git("rev-parse", "HEAD"),
                "commit_ref": os.getenv("CI_COMMIT_REF_NAME")
                or _git("rev-parse", "--abbrev-ref", "HEAD"),
                "pipeline_url": os.getenv("CI_PIPELINE_URL"),
                "project_url": os.getenv("CI_PROJECT_URL"),
            },
        )

        print(f"[export] {len(self.written)} JSON files under {self.data_dir}")
        print(
            f"[export] {len(runs)} run(s), {len(deltas)} comparison(s), {copied} report tree(s), "
            f"{self.ai_summaries} AI summary(ies)"
        )
        for note in self.skipped:
            print(f"[export] skipped: {note}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out", default="public", help="Output directory for the static site (default: public)."
    )
    parser.add_argument(
        "--runs", type=int, default=10, help="How many recent runs to export (default: 10)."
    )
    parser.add_argument(
        "--delta-pairs",
        type=int,
        default=20,
        help="Maximum run comparisons to export (default: 20).",
    )
    parser.add_argument(
        "--site-url",
        default=os.getenv("CI_PAGES_URL", ""),
        help="Public base URL of the published site; used to absolutize report links.",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out).expanduser().resolve()
    exporter = Exporter(
        out_dir=out_dir,
        site_url=args.site_url,
        run_limit=max(1, args.runs),
        delta_pairs=max(0, args.delta_pairs),
    )
    return exporter.run()


if __name__ == "__main__":
    raise SystemExit(main())
