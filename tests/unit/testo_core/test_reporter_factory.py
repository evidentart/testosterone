"""ReporterFactory and resolve_active_reporter_specs tests."""

from __future__ import annotations

import pytest

from testo_core.config.schema import ReporterSpec
from testo_core.reporting.reporters.factory import ReporterFactory, resolve_active_reporter_specs


def test_cli_override_replaces_yaml() -> None:
    yaml_specs = (
        ReporterSpec(type="extent", options=(("output_dir", "/tmp/e"),)),
        ReporterSpec(type="testbeats", options=()),
    )
    active = resolve_active_reporter_specs(yaml_specs, overrides=["allure", "extent"])
    assert [s.type for s in active] == ["allure", "extent"]


def test_build_reporters_from_config() -> None:
    specs = (ReporterSpec(type="extent", options=(("output_dir", "/tmp/out"),)),)
    reporters = ReporterFactory.build(config_reporters=specs)
    assert len(reporters) == 1
    assert reporters[0].reporter_type == "extent"


def test_build_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="unsupported reporter type"):
        resolve_active_reporter_specs((), overrides=["not-a-reporter"])
