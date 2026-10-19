"""``playwright`` framework: argv, config defaults, and a real stage run against
a stand-in ``npx`` that writes what Playwright's junit and html reporters write."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from testo_core.config.loader import load_config
from testo_core.config.schema import Stage
from testo_core.engine.executor import run_stage
from testo_core.frameworks.base import get_adapter
from testo_core.frameworks.playwright_adapter import PlaywrightAdapter

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]


def _argv(*args: str, workers: int = 4) -> list[str]:
    return PlaywrightAdapter().build_argv(
        target_repo=Path("."), results_dir=Path("r"), stage_args=args, workers=workers
    )


def test_argv_adds_reporters_and_workers() -> None:
    assert isinstance(get_adapter("playwright"), PlaywrightAdapter)
    assert _argv("tests/login.spec.ts", "--project=chromium") == [
        "npx",
        "playwright",
        "test",
        "tests/login.spec.ts",
        "--project=chromium",
        "--reporter=list,junit,html",
        "--workers=4",
    ]


@pytest.mark.parametrize("flag", [["--reporter=dot"], ["--reporter", "dot"]])
def test_own_reporter_wins(flag: list[str]) -> None:
    assert not any(a.startswith("--reporter=list") for a in _argv(*flag))


@pytest.mark.parametrize("flag", [["--workers=1"], ["-j", "1"], ["--workers", "1"]])
def test_own_workers_win(flag: list[str]) -> None:
    assert "--workers=4" not in _argv(*flag)


def test_stage_env_and_native_report(tmp_path: Path) -> None:
    adapter = PlaywrightAdapter()
    stage_dir = tmp_path / "artifacts" / "app" / "web"
    env = adapter.stage_env(
        target_repo=tmp_path, results_dir=stage_dir / "allure-results" / "playwright"
    )

    assert env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"] == str(
        tmp_path.resolve() / "test-results" / "testo-junit.xml"
    )
    assert env["PLAYWRIGHT_HTML_OUTPUT_DIR"] == str(stage_dir / "playwright-report")
    assert env["PLAYWRIGHT_HTML_OPEN"] == "never"
    assert adapter.native_report(stage_dir) is None
    (stage_dir / "playwright-report").mkdir(parents=True)
    (stage_dir / "playwright-report" / "index.html").write_text("<html/>", encoding="utf-8")
    native = adapter.native_report(stage_dir)
    assert native is not None and native.entry_relpath == "index.html"


def test_config_defaults_to_e2e_tier(tmp_path: Path) -> None:
    config = tmp_path / "testosterone.yaml"
    config.write_text(
        "version: 1\ncycles:\n  web:\n    stages:\n      - {name: web, equipment: playwright}\n",
        encoding="utf-8",
    )

    (stage,) = load_config(config).cycles["web"].stages

    assert (stage.framework, stage.tier, stage.junit_xml) == ("playwright", "e2e", ())


_FAKE_NPX = textwrap.dedent(
    """\
    #!{python}
    import os, pathlib, sys
    junit = pathlib.Path(os.environ["PLAYWRIGHT_JUNIT_OUTPUT_FILE"])
    junit.parent.mkdir(parents=True, exist_ok=True)
    junit.write_text(
        '<testsuites><testsuite name="login.spec.ts">'
        '<testcase classname="login.spec.ts" name="logs in" time="0.4"/>'
        '<testcase classname="login.spec.ts" name="rejects bad password" time="0.2">'
        '<failure message="expected 401">boom</failure></testcase>'
        '</testsuite></testsuites>'
    )
    html = pathlib.Path(os.environ["PLAYWRIGHT_HTML_OUTPUT_DIR"])
    html.mkdir(parents=True, exist_ok=True)
    (html / "index.html").write_text("<html>report</html>")
    print("argv:", " ".join(sys.argv[1:]))
    sys.exit(1)
    """
)


def test_stage_imports_playwright_junit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(_FAKE_NPX.format(python=sys.executable), encoding="utf-8")
    npx.chmod(npx.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    repo = tmp_path / "repo"
    repo.mkdir()
    stage = Stage(name="web", framework="playwright", target_repo=repo, workers=2, tier="e2e")

    result = run_stage(stage, plan_name="app", artifacts_root=tmp_path / "artifacts")

    assert result.returncode == 1
    stage_dir = tmp_path / "artifacts" / "app" / "web"
    log = (stage_dir / "run.log").read_text(encoding="utf-8")
    assert "argv: playwright test --reporter=list,junit,html --workers=2" in log
    assert "imported 2 test(s) from 1 file(s)" in log
    statuses = sorted(
        json.loads(p.read_text(encoding="utf-8"))["status"]
        for p in (stage_dir / "allure-results" / "playwright").glob("*-result.json")
    )
    assert statuses == ["failed", "passed"]
    assert (stage_dir / "playwright-report" / "index.html").is_file()
