"""Plugins: framework adapters and reporters from ``testo.frameworks`` /
``testo.reporters`` entry points, exercised through the example plugin in
``examples/plugin`` as if it were pip-installed."""

from __future__ import annotations

import json
import os
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core import plugins
from testo_core.cli.app import app
from testo_core.config.errors import ConfigValidationError
from testo_core.config.loader import discover_and_load
from testo_core.config.resolver import resolve_plan
from testo_core.frameworks.base import get_adapter
from testo_core.reporting.reporters.factory import ReporterFactory
from testo_core.services.cycle_run import CycleRunOptions, CycleRunService
from tests.fixtures.engine import NoopRenderer

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "plugin"


def _install(
    site: Path, dist: str, entry_points: str, modules: dict[str, str] | None = None
) -> None:
    """Write what ``pip install`` leaves behind: a dist-info with entry points."""
    info = site / f"{dist.replace('-', '_')}-0.1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist}\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (info / "entry_points.txt").write_text(textwrap.dedent(entry_points), encoding="utf-8")
    for name, source in (modules or {}).items():
        (site / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A fresh site-packages on sys.path, with the example plugin installed."""
    root = tmp_path / "site"
    root.mkdir()
    _install(
        root,
        "testo-example-plugin",
        """\
        [testo.frameworks]
        unittest = testo_example_plugin:UnittestAdapter
        [testo.reporters]
        json-summary = testo_example_plugin:JsonSummaryReporter
        """,
    )
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.syspath_prepend(str(EXAMPLE))
    # The stage subprocess imports the plugin's runner module too.
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join(filter(None, [str(EXAMPLE), os.environ.get("PYTHONPATH")]))
    )
    plugins.clear_cache()
    yield root
    plugins.clear_cache()


def test_installed_plugins_are_discovered(site: Path) -> None:
    found = {(p.kind, p.name): p for p in plugins.list_plugins()}

    assert set(found) == {("framework", "unittest"), ("reporter", "json-summary")}
    assert found["framework", "unittest"].package == "testo-example-plugin 0.1.0"
    assert found["framework", "unittest"].target == "testo_example_plugin:UnittestAdapter"
    assert {"pytest", "unittest"} <= plugins.framework_names()
    assert {"allure", "json-summary"} <= plugins.reporter_types()


def test_get_adapter_and_reporter_factory_load_plugins(site: Path) -> None:
    from testo_core.config.schema import ReporterSpec

    assert get_adapter("unittest").name == "unittest"
    (reporter,) = ReporterFactory.build(
        config_reporters=(ReporterSpec(type="json-summary", options=()),)
    )
    assert reporter.reporter_type == "json-summary"
    assert [
        r.reporter_type
        for r in ReporterFactory.build(config_reporters=(), overrides=["json-summary"])
    ] == ["json-summary"]


def test_cycle_runs_a_plugin_stage_and_reporter(site: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (project / "tests" / "test_math.py").write_text(
        (EXAMPLE / "tests" / "test_math.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project / "testosterone.yaml").write_text(
        (EXAMPLE / "testosterone.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    cfg = discover_and_load(config_path=project / "testosterone.yaml")

    outcome = CycleRunService().run(
        cfg=cfg,
        plan=resolve_plan(cfg, plan_name="unit"),
        renderer=NoopRenderer(),
        options=CycleRunOptions(persist=False, report_db=False),
    )

    assert outcome.exit_code == 0
    summary = json.loads((project / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert (summary["cycle"], summary["total"], summary["passed"]) == ("unit", 2, 2)


def test_unknown_framework_error_lists_plugins(site: Path, tmp_path: Path) -> None:
    config = tmp_path / "testosterone.yaml"
    config.write_text(
        "version: 1\ncycles:\n  c:\n    stages:\n      - {name: s, equipment: nope}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="unittest"):
        discover_and_load(config_path=config)


def test_builtin_names_and_duplicates_are_ignored(site: Path) -> None:
    _install(
        site,
        "testo-shadow",
        """\
        [testo.frameworks]
        pytest = shadow:Adapter
        unittest = shadow:Adapter
        """,
    )
    plugins.clear_cache()

    names = {p.name: p.package for p in plugins.list_plugins() if p.kind == "framework"}
    # Discovery order between the two dists is up to importlib.metadata.
    assert set(names) == {"unittest"}
    assert type(get_adapter("pytest")).__module__ == "testo_core.frameworks.pytest_adapter"


def test_broken_plugins_raise_plugin_error_and_fail_check(site: Path) -> None:
    _install(
        site,
        "testo-broken",
        """\
        [testo.frameworks]
        crashes = broken_mod:Missing
        halfdone = broken_mod:HalfAdapter
        [testo.reporters]
        notareporter = broken_mod:HalfAdapter
        """,
        modules={
            "broken_mod": """\
            class HalfAdapter:
                name = "halfdone"
                def build_argv(self, **kwargs):
                    return []
            """
        },
    )
    plugins.clear_cache()

    with pytest.raises(plugins.PluginError, match="testo-broken 0.1.0.*failed to import"):
        get_adapter("crashes")
    with pytest.raises(plugins.PluginError, match="missing: results_subdir, native_report"):
        get_adapter("halfdone")
    with pytest.raises(plugins.PluginError, match="not a BaseReporter subclass"):
        plugins.load_reporter("notareporter")

    result = CliRunner().invoke(app, ["plugins", "--check", "--json"])
    assert result.exit_code == 1
    rows = {r["name"]: r["status"] for r in json.loads(result.stdout)}
    assert rows["unittest"] == "ok"
    assert rows["json-summary"] == "ok"
    assert rows["crashes"].startswith("error:")


def test_plugins_command_without_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugins, "_entry_points", lambda kind: {})

    result = CliRunner().invoke(app, ["plugins"])

    assert result.exit_code == 0
    assert "pytest" in result.stdout
    assert "No plugins installed" in result.stdout
