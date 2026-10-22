"""Discover and parse ``testosterone.yaml`` (or ``[tool.testosterone]``).

Discovery order (first hit wins):

1. ``--config PATH`` argument.
2. ``./testosterone.yaml`` in the current directory.
3. ``./testosterone.yml``.
4. ``[tool.testosterone]`` table inside ``./pyproject.toml``.

The loader **does not** import the engine, runners, or framework adapters —
keep it cheap so ``testo plans list`` is responsive even in cold venvs.

Backwards compatibility: a legacy flat ``runs: [...]`` schema (the one
consumed by the deprecated argparse CLI) is accepted and wrapped into a
single anonymous plan called ``default``.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml

from testo_core import plugins
from testo_core.config.errors import ConfigDiscoveryError, ConfigValidationError
from testo_core.config.schema import (
    DEFAULT_TIER_BY_FRAMEWORK,
    PARALLEL_FRAMEWORKS,
    SUPPORTED_FRAMEWORKS,
    SUPPORTED_TIERS,
    CycleTrigger,
    Defaults,
    Plan,
    ReporterSpec,
    Stage,
    TestosteroneConfig,
)

logger = logging.getLogger(__name__)

_DEFAULT_PLAN_NAME = "default"


def _candidate_paths(cwd: Path) -> list[Path]:
    return [
        cwd / "testosterone.yaml",
        cwd / "testosterone.yml",
        cwd / "pyproject.toml",
    ]


def discover_and_load(
    *, config_path: Path | None = None, cwd: Path | None = None
) -> TestosteroneConfig:
    """Discover the config file then call :func:`load_config`.

    If ``config_path`` is provided it is used directly; otherwise the
    discovery order above applies.  ``cwd`` defaults to ``Path.cwd()`` and
    is the only seam tests need to monkeypatch.
    """
    cwd = (cwd or Path.cwd()).expanduser().resolve()
    if config_path is not None:
        path = config_path.expanduser().resolve()
        if not path.is_file():
            raise ConfigDiscoveryError(f"config file not found: {path}")
        return load_config(path)

    for candidate in _candidate_paths(cwd):
        if candidate.is_file():
            return load_config(candidate)
    raise ConfigDiscoveryError(
        f"no testosterone.yaml / testosterone.yml / pyproject.toml [tool.testosterone] found under {cwd}"
    )


def load_config_or_defaults(*, config_path: Path | None = None) -> TestosteroneConfig:
    """The given or discovered config; built-in defaults when none is found.

    For ``testo ingest`` and the ingest endpoint, which need no cycles from the
    file, only its reporters and paths when there is one. An explicit
    *config_path* that doesn't exist still raises.
    """
    if config_path is not None:
        return discover_and_load(config_path=config_path)
    try:
        return discover_and_load()
    except ConfigDiscoveryError:
        return TestosteroneConfig(version=1, defaults=Defaults())


def load_config(path: Path) -> TestosteroneConfig:
    """Load and validate one config file."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ConfigDiscoveryError(f"config file not found: {path}")

    if path.name == "pyproject.toml":
        raw = _read_pyproject_section(path)
        if raw is None:
            raise ConfigDiscoveryError(
                f"pyproject.toml at {path} has no [tool.testosterone] table."
            )
    else:
        raw = _read_yaml(path)

    return _build_config(raw, source=path)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise ConfigValidationError(f"cannot read {path}: {exc}") from exc
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"invalid YAML in {path}: {exc}") from exc
    if parsed is None:
        raise ConfigValidationError(f"config file {path} is empty.")
    if not isinstance(parsed, (dict, list)):
        raise ConfigValidationError(f"top-level of {path} must be a mapping or list.")
    return parsed if isinstance(parsed, dict) else {"runs": parsed}


def _read_pyproject_section(path: Path) -> dict[str, Any] | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigValidationError(f"invalid pyproject.toml at {path}: {exc}") from exc
    return data.get("tool", {}).get("testosterone")


def _build_config(raw: dict[str, Any], *, source: Path) -> TestosteroneConfig:
    config_dir = source.parent

    if "cycles" in raw or "plans" in raw:
        return _build_cycle_config(raw, config_dir=config_dir, source=source)
    if "runs" in raw:
        return _build_legacy_runs_config(raw, config_dir=config_dir, source=source)
    if {"test_type", "target_repo"}.issubset(raw):
        # Single legacy run, no `runs:` wrapper.
        return _build_legacy_runs_config({"runs": [raw]}, config_dir=config_dir, source=source)

    raise ConfigValidationError(
        f"config at {source} has neither a 'cycles:' nor a 'runs:' section."
    )


def _build_cycle_config(
    raw: dict[str, Any], *, config_dir: Path, source: Path
) -> TestosteroneConfig:
    version = int(raw.get("version", 1))
    defaults = _parse_defaults(raw.get("defaults", {}), config_dir=config_dir)
    # Canonical: cycles. Legacy: plans.
    cycles_raw = raw.get("cycles")
    if cycles_raw is None:
        cycles_raw = raw.get("plans")
    if not isinstance(cycles_raw, dict) or not cycles_raw:
        raise ConfigValidationError("'cycles:' must be a non-empty mapping.")
    cycles: dict[str, Plan] = {}
    for cycle_name, cycle_raw in cycles_raw.items():
        name_key = str(cycle_name)
        if name_key == "all":
            raise ConfigValidationError(
                "cycle name 'all' is reserved for `testo run --cycle all` (run every cycle). "
                "Rename this cycle in your config."
            )
        _validate_artifact_name(name_key, kind="cycle name")
        cycle = _parse_cycle(
            cycle_name=name_key,
            cycle_raw=cycle_raw or {},
            defaults=defaults,
            config_dir=config_dir,
        )
        cycles[cycle.name] = cycle
    reporters = _parse_reporters(raw.get("reporters"), config_dir=config_dir)
    return TestosteroneConfig(
        version=version, defaults=defaults, cycles=cycles, reporters=reporters, source_path=source
    )


def _build_legacy_runs_config(
    raw: dict[str, Any], *, config_dir: Path, source: Path
) -> TestosteroneConfig:
    """Wrap a legacy flat ``runs: [...]`` config into a single anonymous plan."""
    runs_raw = raw.get("runs")
    if not isinstance(runs_raw, list) or not runs_raw:
        raise ConfigValidationError("'runs:' must be a non-empty list.")
    defaults = _parse_defaults(raw.get("defaults", {}), config_dir=config_dir)
    stages: list[Stage] = []
    for idx, run in enumerate(runs_raw, start=1):
        if not isinstance(run, dict):
            raise ConfigValidationError(f"runs[{idx}] must be a mapping.")
        framework = str(run.get("test_type") or run.get("framework") or "").strip()
        if not framework:
            raise ConfigValidationError(f"runs[{idx}] is missing 'test_type' / 'framework'.")
        if framework == "behave_native":
            framework = "behave"
        if framework not in plugins.framework_names():
            raise ConfigValidationError(
                f"runs[{idx}] unsupported framework {framework!r}; "
                f"supported: {sorted(plugins.framework_names())}"
            )
        stage = _parse_stage(
            stage_raw={
                "name": run.get("name", f"{framework}-{idx}"),
                "framework": framework,
                "target_repo": run.get("target_repo"),
                "args": run.get("cli_args") or run.get("args"),
                "timeout_s": run.get("timeout_s"),
                "extra_env": run.get("extra_env"),
                "junit_xml": run.get("junit_xml"),
            },
            defaults=defaults,
            config_dir=config_dir,
        )
        stages.append(stage)
    plan = Plan(
        name=_DEFAULT_PLAN_NAME,
        description="Legacy 'runs:' shim.",
        stages=tuple(stages),
        trigger=None,
    )
    reporters = _parse_reporters(raw.get("reporters"), config_dir=config_dir)
    return TestosteroneConfig(
        version=int(raw.get("version", 1)),
        defaults=defaults,
        cycles={plan.name: plan},
        reporters=reporters,
        source_path=source,
    )


def _parse_defaults(raw: Any, *, config_dir: Path) -> Defaults:
    if not isinstance(raw, dict):
        raise ConfigValidationError("'defaults:' must be a mapping.")
    target_repo = _resolve_path(raw.get("target_repo", "."), config_dir=config_dir)
    artifacts_root = _resolve_path(raw.get("artifacts_root", "artifacts"), config_dir=config_dir)
    timeout_s = raw.get("timeout_s", 600.0)
    workers = int(raw.get("workers", 4))
    extra_env = _normalise_env(raw.get("extra_env"))
    return Defaults(
        target_repo=target_repo,
        artifacts_root=artifacts_root,
        timeout_s=float(timeout_s) if timeout_s is not None else None,
        workers=workers,
        extra_env=extra_env,
    )


def _parse_cycle(
    *, cycle_name: str, cycle_raw: dict[str, Any], defaults: Defaults, config_dir: Path
) -> Plan:
    if not isinstance(cycle_raw, dict):
        raise ConfigValidationError(f"cycle {cycle_name!r} must be a mapping.")
    description = cycle_raw.get("description")
    stages_raw = cycle_raw.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ConfigValidationError(f"cycle {cycle_name!r} must define a non-empty 'stages:' list.")
    stages = tuple(
        _parse_stage(stage_raw=item, defaults=defaults, config_dir=config_dir)
        for item in stages_raw
    )
    trigger = _parse_trigger(cycle_raw.get("trigger"), cycle_name=cycle_name)
    return Plan(name=cycle_name, description=description, stages=stages, trigger=trigger)


def _parse_trigger(raw: Any, *, cycle_name: str) -> CycleTrigger | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigValidationError(f"cycle {cycle_name!r}: 'trigger' must be a mapping.")
    paths_raw = raw.get("paths")
    if not isinstance(paths_raw, list) or not paths_raw:
        raise ConfigValidationError(
            f"cycle {cycle_name!r}: 'trigger.paths' must be a non-empty list."
        )
    paths_out: list[str] = []
    for i, p in enumerate(paths_raw):
        if not isinstance(p, str) or not p.strip():
            raise ConfigValidationError(
                f"cycle {cycle_name!r}: trigger.paths[{i}] must be a non-empty string."
            )
        paths_out.append(p.strip())
    since_raw = raw.get("since_ref")
    since_ref: str | None = None
    if since_raw is not None:
        if not isinstance(since_raw, str) or not since_raw.strip():
            raise ConfigValidationError(
                f"cycle {cycle_name!r}: 'trigger.since_ref' must be a non-empty string."
            )
        since_ref = since_raw.strip()
    return CycleTrigger(paths=tuple(paths_out), since_ref=since_ref)


_REPORTER_PATH_OPTION_KEYS: frozenset[str] = frozenset({"output_dir", "out_dir"})


def _parse_reporters(raw: Any, *, config_dir: Path) -> tuple[ReporterSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigValidationError("'reporters:' must be a list.")
    out: list[ReporterSpec] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ConfigValidationError(f"reporters[{idx}] must be a mapping.")
        reporter_type = str(item.get("type") or item.get("name") or "").strip().lower()
        if not reporter_type:
            raise ConfigValidationError(f"reporters[{idx}] is missing 'type'.")
        if reporter_type not in plugins.reporter_types():
            raise ConfigValidationError(
                f"reporters[{idx}] has unsupported type {reporter_type!r}; "
                f"supported: {sorted(plugins.reporter_types())}"
            )
        options: list[tuple[str, str]] = []
        for key, value in item.items():
            if key in ("type", "name") or value is None:
                continue
            key_str = str(key)
            if key_str in _REPORTER_PATH_OPTION_KEYS:
                options.append((key_str, str(_resolve_path(value, config_dir=config_dir))))
            else:
                options.append((key_str, str(value)))
        out.append(ReporterSpec(type=reporter_type, options=tuple(options)))
    return tuple(out)


def _parse_stage(*, stage_raw: Mapping[str, Any], defaults: Defaults, config_dir: Path) -> Stage:
    if not isinstance(stage_raw, Mapping):
        raise ConfigValidationError("stage entries must be mappings.")
    name = str(stage_raw.get("name") or "").strip()
    equipment_raw = stage_raw.get("equipment")
    framework_raw = stage_raw.get("framework")
    if equipment_raw is not None and framework_raw is not None:
        if str(equipment_raw).strip() != str(framework_raw).strip():
            raise ConfigValidationError(
                f"stage {name or '<unnamed>'!r} defines both 'equipment' and 'framework' with different values."
            )
    framework = str((equipment_raw if equipment_raw is not None else framework_raw) or "").strip()
    if not name:
        raise ConfigValidationError("stage is missing 'name'.")
    _validate_artifact_name(name, kind=f"stage {name!r} name")
    if not framework:
        raise ConfigValidationError(f"stage {name!r} is missing 'equipment' (legacy: 'framework').")
    if framework == "behave_native":
        framework = "behave"
    if framework not in plugins.framework_names():
        raise ConfigValidationError(
            f"stage {name!r} has unsupported framework {framework!r}; "
            f"supported: {sorted(plugins.framework_names())}"
        )

    target_repo_raw = stage_raw.get("target_repo")
    target_repo = (
        _resolve_path(target_repo_raw, config_dir=config_dir)
        if target_repo_raw is not None
        else defaults.target_repo
    )

    args_raw = stage_raw.get("args")
    if args_raw is None:
        args: tuple[str, ...] = ()
    elif isinstance(args_raw, str):
        import shlex

        args = tuple(shlex.split(args_raw))
    elif isinstance(args_raw, list):
        if not all(isinstance(a, (str, int, float)) for a in args_raw):
            raise ConfigValidationError(f"stage {name!r}: 'args' must be a list of scalars.")
        args = tuple(str(a) for a in args_raw)
    else:
        raise ConfigValidationError(f"stage {name!r}: 'args' must be a string or list.")

    workers = int(stage_raw.get("workers", defaults.workers))
    # Plugin adapters get ``workers`` in build_argv and decide for themselves.
    if (
        "workers" in stage_raw
        and framework in SUPPORTED_FRAMEWORKS
        and framework not in PARALLEL_FRAMEWORKS
    ):
        logger.warning(
            "stage %r: 'workers' has no effect on framework %r (it runs single-process).",
            name,
            framework,
        )
    timeout_raw = stage_raw.get("timeout_s", defaults.timeout_s)
    timeout_s = float(timeout_raw) if timeout_raw is not None else None
    if_expr = stage_raw.get("if")
    if if_expr is not None and not isinstance(if_expr, str):
        raise ConfigValidationError(f"stage {name!r}: 'if' must be a string.")

    extra_env = _normalise_env(stage_raw.get("extra_env")) or defaults.extra_env

    tier_raw = stage_raw.get("tier")
    if tier_raw is None:
        tier = DEFAULT_TIER_BY_FRAMEWORK.get(framework, "unit")
    else:
        tier = str(tier_raw).strip().lower()
        if tier not in SUPPORTED_TIERS:
            raise ConfigValidationError(
                f"stage {name!r} has unsupported tier {tier!r}; supported: {sorted(SUPPORTED_TIERS)}"
            )

    junit_raw = stage_raw.get("junit_xml")
    if junit_raw is None:
        junit_xml: tuple[str, ...] = ()
    elif isinstance(junit_raw, str) and junit_raw.strip():
        junit_xml = (junit_raw.strip(),)
    elif (
        isinstance(junit_raw, list)
        and junit_raw
        and all(isinstance(p, str) and p.strip() for p in junit_raw)
    ):
        junit_xml = tuple(p.strip() for p in junit_raw)
    else:
        raise ConfigValidationError(
            f"stage {name!r}: 'junit_xml' must be a non-empty string or list of glob patterns."
        )
    for pattern in junit_xml:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ConfigValidationError(
                f"stage {name!r}: 'junit_xml' patterns must be relative to target_repo "
                f"and stay inside it (got {pattern!r})."
            )

    if framework == "command" and not args:
        raise ConfigValidationError(
            f"stage {name!r}: framework 'command' needs 'args' (the full command to run)."
        )
    if framework == "junit" and not junit_xml:
        raise ConfigValidationError(
            f"stage {name!r}: framework 'junit' needs 'junit_xml' (the reports to record)."
        )

    return Stage(
        name=name,
        framework=framework,
        target_repo=target_repo,
        args=args,
        workers=workers,
        timeout_s=timeout_s,
        if_expr=if_expr,
        extra_env=extra_env,
        tier=tier,
        junit_xml=junit_xml,
    )


def _resolve_path(value: Any, *, config_dir: Path) -> Path:
    if value is None:
        return config_dir
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else (config_dir / p).resolve()


def _validate_artifact_name(value: str, *, kind: str) -> None:
    """Reject artifact path names that can escape their containing directory."""
    text = str(value).strip()
    posix_text = text.replace("\\", "/")
    win = PureWindowsPath(text)
    if posix_text.startswith("/") or win.is_absolute() or win.drive:
        raise ConfigValidationError(f"{kind} must be relative: {value!r}")
    if any(part == ".." for part in posix_text.split("/")) or any(
        part == ".." for part in win.parts
    ):
        raise ConfigValidationError(f"{kind} must not contain '..': {value!r}")


def _normalise_env(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ConfigValidationError("'extra_env' must be a mapping of strings.")
    out: list[tuple[str, str]] = []
    for k, v in value.items():
        out.append((str(k), str(v)))
    return tuple(out)
