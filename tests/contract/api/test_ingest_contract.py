"""``POST /api/v1/ingest`` (``testo ingest --server``), the UI served by the API
(``TESTO_UI_DIR``), and the upload client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testo_api.main import create_app
from testo_core.repository.db import get_repository, reset_repository_cache
from testo_core.services import ingest_client, junit_ingest

PASSING = b"""<testsuite name="cart"><testcase classname="cart" name="adds" time="0.2"/>
<testcase classname="cart" name="skips" time="0"><skipped/></testcase></testsuite>"""
FAILING = b"""<testsuite name="pay"><testcase classname="pay" name="refunds" time="0.5">
<failure message="boom">trace</failure></testcase></testsuite>"""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("TESTO_API_TOKEN", "TESTO_CORS_ORIGINS", "TESTO_UI_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setattr("testo_core.paths.ORCHESTRATOR_ROOT", tmp_path)
    monkeypatch.setattr("testo_core.paths.STATIC_HISTORY_ROOT", tmp_path / "static" / "history")
    monkeypatch.chdir(tmp_path)  # no testosterone.yaml here: built-in defaults
    reset_repository_cache()
    yield
    reset_repository_cache()


def _files(*pairs: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, body, "application/xml")) for name, body in pairs]


def test_upload_is_recorded_as_a_run_with_the_clients_provenance() -> None:
    resp = TestClient(create_app()).post(
        "/api/v1/ingest",
        data={
            "cycle": "web-unit",
            "ci_provider": "github",
            "ci_commit_sha": "abc123",
            "repository": "acme/web",
            "not_a_field": "ignored",
        },
        files=_files(("ok.xml", PASSING), ("../../bad.xml", FAILING)),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["cycle"], body["exit_code"]) == ("web-unit", 1)
    assert (body["tests"], body["passed"], body["failed"], body["skipped"]) == (3, 1, 1, 1)
    assert body["run_url"] is None  # no UI served by this app

    record = get_repository().get_run(body["run_id"])
    assert record is not None
    meta = record.metadata_
    assert meta["plan"] == "web-unit"
    assert meta["ci_provider"] == "github"
    assert meta["ci_commit_sha"] == "abc123"
    assert meta["target_repo"] == "acme/web"
    assert "not_a_field" not in meta


def test_upload_needs_the_token_when_one_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTO_API_TOKEN", "s3cret")
    client = TestClient(create_app())
    args = {"data": {"cycle": "web"}, "files": _files(("ok.xml", PASSING))}
    assert client.post("/api/v1/ingest", **args).status_code == 401
    ok = client.post("/api/v1/ingest", headers={"Authorization": "Bearer s3cret"}, **args)
    assert ok.status_code == 201
    assert ok.json()["exit_code"] == 0


@pytest.mark.parametrize("cycle", ["../x", "a/b", ""])
def test_unsafe_cycle_name_is_400(cycle: str) -> None:
    resp = TestClient(create_app()).post(
        "/api/v1/ingest", data={"cycle": cycle}, files=_files(("ok.xml", PASSING))
    )
    assert resp.status_code in (400, 422)


def test_oversized_file_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(junit_ingest, "MAX_FILE_BYTES", 10)
    monkeypatch.setattr("testo_api.routes.ingest.MAX_FILE_BYTES", 10)
    resp = TestClient(create_app()).post(
        "/api/v1/ingest", data={"cycle": "web"}, files=_files(("ok.xml", PASSING))
    )
    assert resp.status_code == 400
    assert "larger than" in resp.json()["error"]["message"]


# --- UI served by the API ----------------------------------------------------------


@pytest.fixture
def ui(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>testo ui</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("TESTO_UI_DIR", str(dist))
    return dist


def test_ui_routes_fall_back_to_index_but_api_404s_stay(ui: Path) -> None:
    client = TestClient(create_app())
    assert "testo ui" in client.get("/").text
    assert "testo ui" in client.get("/runs/some-id").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    missing = client.get("/api/v1/nope")
    assert missing.status_code == 404
    assert "testo ui" not in missing.text
    assert client.get("/api/v1/health/live").status_code == 200


def test_run_url_points_at_the_ui_when_served(ui: Path) -> None:
    resp = TestClient(create_app()).post(
        "/api/v1/ingest", data={"cycle": "web"}, files=_files(("ok.xml", PASSING))
    )
    body = resp.json()
    assert body["run_url"] == f"http://testserver/runs/{body['run_id']}"


def test_same_origin_writes_need_a_token(monkeypatch: pytest.MonkeyPatch, ui: Path) -> None:
    args = {
        "data": {"cycle": "web"},
        "files": _files(("ok.xml", PASSING)),
        "headers": {"Origin": "http://testserver"},
    }
    # No token: the Origin allow-list is the only guard, so the server's own origin is refused.
    assert TestClient(create_app()).post("/api/v1/ingest", **args).status_code == 403
    monkeypatch.setenv("TESTO_API_TOKEN", "s3cret")
    args["headers"] = {"Origin": "http://testserver", "Authorization": "Bearer s3cret"}
    assert TestClient(create_app()).post("/api/v1/ingest", **args).status_code == 201


# --- client --------------------------------------------------------------------------


def test_client_metadata_from_github_actions() -> None:
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_SHA": "abc",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REPOSITORY": "acme/web",
    }
    meta = ingest_client.client_run_metadata(env)
    assert meta["ci_provider"] == "github"
    assert meta["ci_commit_sha"] == "abc"
    assert meta["repository"] == "acme/web"
    assert ingest_client.client_run_metadata({}) == {}


def test_client_posts_files_and_raises_the_servers_message(tmp_path: Path) -> None:
    report = tmp_path / "a.xml"
    report.write_bytes(PASSING)
    ok = MagicMock(status_code=201)
    ok.json.return_value = {"run_id": "r1", "exit_code": 0}
    with patch("requests.post", return_value=ok) as post:
        body = ingest_client.upload_reports(
            server="https://testo.example.com/",
            token="t",
            cycle="web",
            files=[report],
            metadata={"ci_provider": "github"},
        )
    assert body == {"run_id": "r1", "exit_code": 0}
    url = post.call_args[0][0]
    kwargs = post.call_args[1]
    assert url == "https://testo.example.com/api/v1/ingest"
    assert kwargs["headers"] == {"Authorization": "Bearer t"}
    assert kwargs["data"]["cycle"] == "web"
    assert kwargs["data"]["ci_provider"] == "github"
    assert kwargs["files"][0][1][0] == "a.xml"

    refused = MagicMock(status_code=401)
    refused.json.return_value = {"error": {"message": "Missing or invalid API token."}}
    with (
        patch("requests.post", return_value=refused),
        pytest.raises(ingest_client.IngestUploadError, match="401: Missing or invalid"),
    ):
        ingest_client.upload_reports(server="http://x", token=None, cycle="web", files=[report])


def test_cli_upload_exit_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from testo_core.cli.app import app

    (tmp_path / "a.xml").write_bytes(PASSING)
    runner = CliRunner()
    with patch.object(
        ingest_client, "upload_reports", return_value={"exit_code": 1, "tests": 2, "cycle": "web"}
    ):
        result = runner.invoke(app, ["ingest", "a.xml", "--cycle", "web", "--server", "http://x"])
    assert result.exit_code == 1, result.output
    with patch.object(
        ingest_client, "upload_reports", side_effect=ingest_client.IngestUploadError("down")
    ):
        result = runner.invoke(app, ["ingest", "a.xml", "--cycle", "web", "--server", "http://x"])
    assert result.exit_code == 3
    assert "down" in result.output
