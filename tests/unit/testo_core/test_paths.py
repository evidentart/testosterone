"""Tests for ``testo_core.paths`` (layout + Allure input directory resolution)."""

from __future__ import annotations

from pathlib import Path

from testo_core.paths import (
    ALLURE_FRAMEWORK_RESULT_SUBDIRS,
    DATA_HOME_ENV,
    allure_cli_input_directories,
    allure_results_dir,
    default_artifacts_root,
    resolve_data_root,
    source_checkout_root,
)


def test_default_artifacts_root_is_relative() -> None:
    assert default_artifacts_root() == Path("artifacts")


def test_allure_results_dir_joins(tmp_path: Path) -> None:
    assert allure_results_dir(tmp_path) == tmp_path / "allure-results"


def test_allure_cli_input_directories_prefers_subdirs_when_any_exist(tmp_path: Path) -> None:
    root = tmp_path / "allure-results"
    root.mkdir()
    (root / "pytest").mkdir()
    d = allure_cli_input_directories(root)
    assert d == [root / "pytest"]


def test_allure_cli_input_directories_falls_back_to_parent(tmp_path: Path) -> None:
    root = tmp_path / "allure-results"
    root.mkdir()
    (root / "x-result.json").write_text("{}", encoding="utf-8")
    d = allure_cli_input_directories(root)
    assert d == [root]


def test_framework_subdir_names_triple() -> None:
    # Locust support has been removed; the framework subdir set is now
    # pytest / behave_native / behavex.
    assert len(ALLURE_FRAMEWORK_RESULT_SUBDIRS) == 3
    assert set(ALLURE_FRAMEWORK_RESULT_SUBDIRS) == {"pytest", "behave_native", "behavex"}


def _fake_install(tmp_path: Path, *, with_pyproject: bool) -> Path:
    root = tmp_path / "site-packages" if not with_pyproject else tmp_path / "checkout"
    pkg = root / "testo_core"
    pkg.mkdir(parents=True)
    if with_pyproject:
        (root / "pyproject.toml").write_text("[project]\nname = 'testo-core'\n")
    return pkg


def test_data_root_is_checkout_for_source_tree(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(DATA_HOME_ENV, raising=False)
    pkg = _fake_install(tmp_path, with_pyproject=True)
    assert source_checkout_root(pkg) == pkg.parent
    assert resolve_data_root(package_dir=pkg, cwd=tmp_path / "elsewhere") == pkg.parent


def test_data_root_is_dot_testo_in_cwd_for_installed_package(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(DATA_HOME_ENV, raising=False)
    pkg = _fake_install(tmp_path, with_pyproject=False)
    project = tmp_path / "project"
    assert source_checkout_root(pkg) is None
    root = resolve_data_root(package_dir=pkg, cwd=project)
    assert root == project.resolve() / ".testo"
    assert pkg.parent not in (root, *root.parents)


def test_testo_home_overrides_data_root(tmp_path: Path, monkeypatch) -> None:
    pkg = _fake_install(tmp_path, with_pyproject=True)
    monkeypatch.setenv(DATA_HOME_ENV, str(tmp_path / "data"))
    assert resolve_data_root(package_dir=pkg, cwd=tmp_path) == (tmp_path / "data").resolve()


def test_this_checkout_keeps_repo_root_layout(monkeypatch) -> None:
    monkeypatch.delenv(DATA_HOME_ENV, raising=False)
    repo = Path(__file__).resolve().parents[3]
    assert resolve_data_root() == repo
