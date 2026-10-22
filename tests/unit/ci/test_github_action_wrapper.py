from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def _load_wrapper_module():
    script = Path("integrations/github-action/run_testo_action.py").resolve()
    spec = importlib.util.spec_from_file_location("run_testo_action", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_command_includes_expected_flags() -> None:
    module = _load_wrapper_module()
    cmd = module.build_command(config_path="config.yml", cycle="smoke", ci_mode=True, persist=False)
    assert cmd == [
        "testo",
        "run",
        "--config",
        "config.yml",
        "--cycle",
        "smoke",
        "--ci",
        "--no-persist",
    ]


def test_build_command_omits_empty_config_and_cycle() -> None:
    module = _load_wrapper_module()
    assert module.build_command(config_path="", cycle="", ci_mode=True, persist=True) == [
        "testo",
        "run",
        "--ci",
    ]


def test_extract_summary_uses_last_plan_finished_line() -> None:
    module = _load_wrapper_module()
    stdout = "\n".join(
        [
            '{"event":"plan_started","plan":"smoke","stage_count":1}',
            '{"event":"stage_finished","stage":"s","returncode":0}',
            '{"event":"plan_finished","plan":"smoke","exit_code":0,"aggregate_returncode":0}',
        ]
    )
    summary = module._extract_summary(stdout, fallback_exit_code=4)
    assert summary["event"] == "plan_finished"
    assert summary["exit_code"] == 0


def test_extract_summary_falls_back_to_process_exit_code() -> None:
    module = _load_wrapper_module()
    summary = module._extract_summary("not json\n", fallback_exit_code=2)
    assert summary["event"] == "error"
    assert summary["exit_code"] == 2


def test_main_writes_outputs_and_summary_file(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    plan_finished = {
        "event": "plan_finished",
        "plan": "smoke",
        "exit_code": 1,
        "aggregate_returncode": 1,
    }
    captured_cmd: list[str] = []

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        captured_cmd.extend(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout=json.dumps(plan_finished) + "\n", stderr=""
        )

    output_file = tmp_path / "github_output.txt"
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))

    code = module.main(
        [
            "--cycle",
            "smoke",
            "--ci-mode",
            "true",
            "--persist",
            "true",
            "--job-summary",
            "false",
            "--annotations",
            "false",
        ]
    )
    assert code == 1
    assert captured_cmd == ["testo", "run", "--cycle", "smoke", "--ci"]

    kv = dict(
        line.split("=", 1)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert kv["exit_code"] == "1"
    assert kv["status"] == "failure"
    assert json.loads(kv["summary_json"])["plan"] == "smoke"
    assert Path(kv["summary_path"]) == tmp_path / "testo-summary.json"
    assert Path(kv["summary_path"]).is_file()


def _github_env(tmp_path: Path, *, event: str = "pull_request") -> dict[str, str]:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"number": 7}}), encoding="utf-8")
    return {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_API_URL": "https://api.example",
        "GITHUB_SERVER_URL": "https://github.example",
        "GITHUB_RUN_ID": "99",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "TESTO_GITHUB_TOKEN": "t",
    }


def test_pull_request_number_only_on_pull_request_events(tmp_path: Path) -> None:
    module = _load_wrapper_module()
    assert module.pull_request_number(_github_env(tmp_path)) == 7
    assert module.pull_request_number(_github_env(tmp_path, event="push")) is None


def test_render_markdown_links_the_workflow_run(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    seen: list[list[str]] = []

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        seen.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="<!-- m -->\nhi\n", stderr=""
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.render_markdown(cycle="smoke", env=_github_env(tmp_path)) == "<!-- m -->\nhi\n"
    assert seen[0] == [
        "testo",
        "report",
        "markdown",
        "--cycle",
        "smoke",
        "--run-url",
        "https://github.example/o/r/actions/runs/99",
    ]


def test_upsert_edits_the_cycles_earlier_comment(monkeypatch) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    calls: list[tuple[str, str, object]] = []

    def fake_github(method, url, token, body=None):  # noqa: ANN001
        calls.append((method, url, body))
        if method == "GET":
            return [
                {"id": 1, "body": "someone else"},
                {"id": 2, "body": "<!-- testo-summary:smoke -->\nold"},
            ]
        return {}

    monkeypatch.setattr(module, "_github", fake_github)
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_API_URL": "https://api.example"}
    result = module.upsert_pr_comment(
        markdown="<!-- testo-summary:smoke -->\nnew", number=7, token="t", env=env
    )
    assert result == "updated"
    assert calls[-1] == (
        "PATCH",
        "https://api.example/repos/o/r/issues/comments/2",
        {"body": "<!-- testo-summary:smoke -->\nnew"},
    )


def test_upsert_posts_when_there_is_no_earlier_comment(monkeypatch) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    calls: list[tuple[str, str]] = []

    def fake_github(method, url, token, body=None):  # noqa: ANN001
        calls.append((method, url))
        return [] if method == "GET" else {}

    monkeypatch.setattr(module, "_github", fake_github)
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_API_URL": "https://api.example"}
    assert (
        module.upsert_pr_comment(markdown="<!-- x -->\nb", number=7, token="t", env=env)
        == "created"
    )
    assert calls[-1] == ("POST", "https://api.example/repos/o/r/issues/7/comments")


def test_publish_summary_writes_job_summary_and_survives_a_comment_error(
    tmp_path: Path,
    monkeypatch,
    capsys,  # noqa: ANN001
) -> None:
    module = _load_wrapper_module()
    env = _github_env(tmp_path)
    monkeypatch.setattr(module, "render_markdown", lambda **_: "<!-- m -->\nbody\n")

    def boom(**_kwargs):  # noqa: ANN003
        raise module.urllib.error.HTTPError("u", 403, "Forbidden", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "upsert_pr_comment", boom)
    module.publish_summary(cycle="smoke", job_summary=True, comment=True, env=env)

    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == "<!-- m -->\nbody\n"
    assert "could not comment on pull request #7" in capsys.readouterr().err


def _fake_testo(module, monkeypatch, *, stdout: str = "") -> list[list[str]]:  # noqa: ANN001
    seen: list[list[str]] = []

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        seen.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return seen


def test_annotate_prints_the_error_lines(tmp_path: Path, monkeypatch, capsys) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    seen = _fake_testo(module, monkeypatch, stdout="::error title=t::boom\n")
    env = {**_github_env(tmp_path), "GITHUB_WORKSPACE": "/w"}
    module.annotate(cycle="smoke", config_path="", env=env)
    assert seen[0] == ["testo", "report", "annotations", "--cycle", "smoke", "--workspace", "/w"]
    assert capsys.readouterr().out == "::error title=t::boom\n"


def test_notify_sends_only_to_chats_with_a_webhook(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    module = _load_wrapper_module()
    seen = _fake_testo(module, monkeypatch)
    module.notify(cycle="smoke", when="failure", env=_github_env(tmp_path))
    assert seen == []

    env = {**_github_env(tmp_path), "TESTO_TEAMS_WEBHOOK_URL": "https://teams.example/hook"}
    module.notify(cycle="smoke", when="change", env=env)
    assert seen[0] == [
        "testo",
        "notify",
        "--cycle",
        "smoke",
        "--when",
        "change",
        "--to",
        "teams",
        "--run-url",
        "https://github.example/o/r/actions/runs/99",
    ]


def test_flaky_issues_skip_tests_that_already_have_an_open_issue(
    tmp_path: Path,
    monkeypatch,  # noqa: ANN001
) -> None:
    module = _load_wrapper_module()
    flaky = {
        "flaky": [
            {
                "name": "test_a",
                "runs": 3,
                "passed": 2,
                "failed": 1,
                "flips": 2,
                "history": ["passed", "failed", "passed"],
            },
            {"name": "test_b", "runs": 3, "passed": 2, "failed": 1, "flips": 2, "history": []},
        ]
    }
    seen = _fake_testo(module, monkeypatch, stdout=json.dumps(flaky))
    calls: list[tuple[str, str, object]] = []

    def fake_github(method, url, token, body=None):  # noqa: ANN001
        calls.append((method, url, body))
        return [{"title": "Flaky test: test_a (smoke)"}] if method == "GET" else {}

    monkeypatch.setattr(module, "_github", fake_github)
    module.open_flaky_issues(cycle="smoke", token="t", env=_github_env(tmp_path))

    assert seen[0] == ["testo", "flaky", "--cycle", "smoke", "--new", "--json"]
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    _, url, body = posts[0]
    assert url == "https://api.example/repos/o/r/issues"
    assert isinstance(body, dict)
    assert body["title"] == "Flaky test: test_b (smoke)"
    assert body["labels"] == ["flaky-test"]
    assert "testo flaky --cycle smoke" in body["body"]
