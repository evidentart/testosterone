"""Pytest configuration for the orchestrator package."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# Tests must not read or overwrite a developer's saved AI settings (artifacts/ai_settings.json).
os.environ.setdefault("TESTO_AI_SETTINGS_PATH", "")

# Project root is parent of ``tests/``; ``pythonpath = .`` in pytest.ini also applies.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _try_import_allure():
    try:
        import allure  # type: ignore

        return allure
    except Exception:
        return None


def _path_kind(path: Path) -> str:
    p = str(path).replace("\\", "/").lstrip("./")
    if p.startswith("tests/e2e/") or "/tests/e2e/" in p:
        return "e2e"
    if p.startswith("tests/integration/") or "/tests/integration/" in p:
        return "integration"
    if p.startswith("tests/contract/") or "/tests/contract/" in p:
        return "contract"
    if p.startswith("tests/contracts/") or "/tests/contracts/" in p:
        return "contract"
    return "unit"


def _default_feature(kind: str) -> str:
    return {
        "unit": "Unit",
        "integration": "Flow/Integration",
        "e2e": "E2E Journeys",
        "contract": "Contract",
    }.get(kind, "Unit")


def _default_story(item: pytest.Item) -> str:
    try:
        rel = Path(str(item.fspath)).resolve().relative_to(_ROOT)
        return str(rel).replace("\\", "/")
    except Exception:
        return str(getattr(item, "fspath", "unknown"))


def _has_marker(item: pytest.Item, marker_name: str) -> bool:
    return item.get_closest_marker(marker_name) is not None


def _add_marker_if_missing(item: pytest.Item, marker_name: str) -> None:
    if not _has_marker(item, marker_name):
        item.add_marker(getattr(pytest.mark, marker_name))


def _normalized_test_path(item: pytest.Item) -> str:
    return str(item.fspath).replace("\\", "/")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Keep marker taxonomy deterministic across legacy and migrated test paths.
    """
    for item in items:
        p = _normalized_test_path(item)
        kind = _path_kind(Path(p))
        _add_marker_if_missing(item, kind)

        if "/tests/e2e/flows/test_external_provider_lifecycle.py" in p:
            _add_marker_if_missing(item, "tier_external")
            _add_marker_if_missing(item, "cleanup_required")
            continue

        if "/tests/e2e/" in p:
            _add_marker_if_missing(item, "tier_heavy")
            continue

        if (
            "/tests/integration/test_runner_image_mode_smoke.py" in p
            or "/tests/integration/ui/" in p
        ):
            _add_marker_if_missing(item, "tier_heavy")
            continue

        _add_marker_if_missing(item, "tier_fast")


def _sanitize_run_id(value: str) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return collapsed.strip("-")[:48] or "local"


def _default_run_id() -> str:
    for key in ("GITHUB_RUN_ID", "CI_PIPELINE_ID", "BUILD_BUILDID", "BUILD_TAG"):
        raw = os.getenv(key)
        if raw:
            return _sanitize_run_id(raw)
    return _sanitize_run_id(uuid.uuid4().hex[:12])


@pytest.fixture(scope="session")
def e2e_run_id() -> str:
    configured = os.getenv("TESTO_E2E_RUN_ID")
    if configured:
        return _sanitize_run_id(configured)
    return _default_run_id()


@dataclass
class CleanupRecord:
    resource_type: str
    resource_id: str
    provider: str
    status: str
    detail: str = ""


class CleanupLedger:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.records: list[CleanupRecord] = []

    def add(
        self, *, resource_type: str, resource_id: str, provider: str, status: str, detail: str = ""
    ) -> None:
        self.records.append(
            CleanupRecord(
                resource_type=resource_type,
                resource_id=resource_id,
                provider=provider,
                status=status,
                detail=detail,
            )
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at_epoch_s": int(time.time()),
            "records": [record.__dict__ for record in self.records],
        }

    def write(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        out = root / "cleanup-ledger.json"
        out.write_text(json.dumps(self.to_payload(), indent=2, sort_keys=True), encoding="utf-8")
        return out


@pytest.fixture(scope="session")
def cleanup_ledger(e2e_run_id: str, request: pytest.FixtureRequest) -> CleanupLedger:
    ledger = CleanupLedger(run_id=e2e_run_id)

    def _flush() -> None:
        artifact_root = _ROOT / ".artifacts" / "e2e" / e2e_run_id
        ledger.write(artifact_root)

    request.addfinalizer(_flush)
    return ledger


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """
    Allure-first defaults.

    We dynamically assign feature/story/title/severity so every test is categorized in Allure
    without requiring repetitive per-test decorators.
    """
    allure = _try_import_allure()
    if allure is None:
        return

    kind = _path_kind(Path(str(item.fspath)))
    allure.dynamic.feature(_default_feature(kind))
    allure.dynamic.story(_default_story(item))
    allure.dynamic.title(getattr(item, "originalname", None) or item.name)

    sev = None
    if kind == "e2e":
        sev = getattr(allure.severity_level, "BLOCKER", None)
    elif kind in {"integration", "contract"}:
        sev = getattr(allure.severity_level, "NORMAL", None)
    else:
        sev = getattr(allure.severity_level, "TRIVIAL", None)
    if sev is not None:
        allure.dynamic.severity(sev)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    """
    On failure, automatically attach last HTTP exchange (request/response) to Allure.
    """
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not getattr(report, "failed", False):
        return

    allure = _try_import_allure()
    if allure is None:
        return

    # Attach only for non-unit tests by default (integration/e2e/contracts), unless explicitly opted-in.
    kind = _path_kind(Path(str(item.fspath)))
    if kind == "unit" and item.get_closest_marker("attach_http_on_fail") is None:
        return

    rec: ApiRecorder | None = (
        item.funcargs.get("api_recorder") if hasattr(item, "funcargs") else None
    )  # type: ignore[attr-defined]
    if rec is None or rec.last is None:
        return

    last = rec.last
    try:
        allure.attach(
            f"{last.method} {last.url}\nstatus={last.status_code}\n\nheaders={last.request_headers}\n",
            name="http_request_meta",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception:
        pass
    try:
        allure.attach(
            f"status={last.status_code}\n\nheaders={last.response_headers}\n",
            name="http_response_meta",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception:
        pass

    # JSON bodies
    try:
        from tests._allure_utils import attach_json

        attach_json("http_request_json", last.request_json)
        attach_json(
            "http_response_json",
            last.response_json if last.response_json is not None else {"text": last.response_text},
        )
    except Exception:
        pass


@dataclass
class LastHttpExchange:
    method: str
    url: str
    request_json: Any | None
    request_headers: dict[str, str]
    status_code: int | None
    response_json: Any | None
    response_text: str | None
    response_headers: dict[str, str]


@dataclass
class ApiRecorder:
    last: LastHttpExchange | None = None

    def record(
        self,
        *,
        method: str,
        url: str,
        request_json: Any | None,
        request_headers: dict[str, str],
        status_code: int | None,
        response_json: Any | None,
        response_text: str | None,
        response_headers: dict[str, str],
    ) -> None:
        self.last = LastHttpExchange(
            method=method,
            url=url,
            request_json=request_json,
            request_headers=request_headers,
            status_code=status_code,
            response_json=response_json,
            response_text=response_text,
            response_headers=response_headers,
        )


@pytest.fixture
def api_recorder() -> ApiRecorder:
    return ApiRecorder()


@pytest.fixture(scope="session")
def mock_api_app():
    """
    In-process FastAPI app for integration/contract tests.
    """
    mock_api_path = _ROOT / "sample_target_repo" / "mock_api.py"
    if not mock_api_path.exists():
        raise FileNotFoundError(f"Missing mock API at {mock_api_path}")

    module_name = "uqo_sample_mock_api"
    mod = sys.modules.get(module_name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(module_name, str(mock_api_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module spec for {mock_api_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]

    app = getattr(mod, "app", None)
    if app is None:
        raise AttributeError("mock_api.py did not define `app`")
    return app


@pytest.fixture
def fastapi_client(mock_api_app, api_recorder: ApiRecorder):
    from fastapi.testclient import TestClient  # type: ignore

    client = TestClient(mock_api_app)

    class _Client:
        def request(
            self,
            method: str,
            url: str,
            *,
            json: Any | None = None,
            headers: dict[str, str] | None = None,
            timeout: float | None = None,
        ):
            # TestClient ignores `timeout`, but keep signature parallel to requests.
            hdrs = dict(headers or {})
            resp = client.request(method, url, json=json, headers=hdrs)
            try:
                rj = resp.json()
            except Exception:
                rj = None
            api_recorder.record(
                method=method.upper(),
                url=url,
                request_json=json,
                request_headers=hdrs,
                status_code=getattr(resp, "status_code", None),
                response_json=rj,
                response_text=getattr(resp, "text", None),
                response_headers=dict(getattr(resp, "headers", {}) or {}),
            )
            return resp

        def get(self, url: str, **kwargs: Any):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs: Any):
            return self.request("POST", url, **kwargs)

        def delete(self, url: str, **kwargs: Any):
            return self.request("DELETE", url, **kwargs)

    return _Client()


@pytest.fixture(autouse=True)
def reset_mock_api_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure sandbox mock API starts each test with clean state (in-process only).
    """
    try:
        # Prefer the same module loaded by `mock_api_app` fixture.
        m = sys.modules.get("uqo_sample_mock_api")
        if m is None:
            return
        items = getattr(m, "ITEMS", None)
        if isinstance(items, list):
            items.clear()
        if hasattr(m, "NEXT_ID"):
            m.NEXT_ID = 1
    except Exception:
        # If the sample app is not importable in this environment, unit tests should still run.
        return


@pytest.fixture
def auth_token(fastapi_client) -> str:
    r = fastapi_client.post("/login", json={"username": "alice"})
    assert r.status_code == 200
    token = r.json().get("token")
    assert isinstance(token, str) and token
    return token


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}
