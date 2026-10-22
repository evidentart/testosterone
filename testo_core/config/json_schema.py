"""JSON Schema for ``testosterone.yaml``, for editor autocomplete and validation.

The loader (:mod:`testo_core.config.loader`) stays the source of truth: it is
what accepts or rejects a config. This schema describes the same keys so that
editors with a YAML language server (VS Code, JetBrains, Neovim) can suggest
them and flag typos while you type. It is built from the constants in
:mod:`testo_core.config.schema`, so adding a built-in framework, tier or
reporter there updates it; ``scripts/export_config_schema.py --check`` fails
CI when the committed ``schema/testosterone.schema.json`` is stale.

Only the canonical ``cycles:`` layout is described. Legacy ``plans:`` and
``runs:`` still load but are not suggested.
"""

from __future__ import annotations

from typing import Any

from testo_core.config.schema import (
    DEFAULT_TIER_BY_FRAMEWORK,
    SUPPORTED_FRAMEWORKS,
    SUPPORTED_REPORTER_TYPES,
    SUPPORTED_TIERS,
    Defaults,
)

SCHEMA_ID = "https://raw.githubusercontent.com/taltal-beep/testosterone/main/schema/testosterone.schema.json"

_NAME_PATTERN = r"^(?![/\\])(?![A-Za-z]:)(?!.*(^|[/\\])\.\.([/\\]|$)).+$"


def _open_enum(values: frozenset[str], description: str) -> dict[str, Any]:
    """Suggest the built-in values but accept any string (plugins add their own)."""
    return {
        "description": description,
        "anyOf": [{"enum": sorted(values)}, {"type": "string", "minLength": 1}],
    }


def _env() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Extra environment variables for the test process.",
        "additionalProperties": {"type": ["string", "number", "boolean"]},
    }


def _timeout(default: float | None) -> dict[str, Any]:
    return {
        "type": ["number", "null"],
        "exclusiveMinimum": 0,
        "default": default,
        "description": "Kill the stage after this many seconds. null means no limit.",
    }


def build_json_schema() -> dict[str, Any]:
    """Return the JSON Schema (draft-07) for a ``testosterone.yaml`` file."""
    defaults = Defaults()
    tier_defaults = ", ".join(f"{k}={v}" for k, v in sorted(DEFAULT_TIER_BY_FRAMEWORK.items()))

    stage = {
        "type": "object",
        "description": "One step of a cycle: a test runner and its arguments.",
        "required": ["name"],
        "anyOf": [{"required": ["equipment"]}, {"required": ["framework"]}],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
                "pattern": _NAME_PATTERN,
                "description": "Stage name; also its artifacts folder, so it must be a relative path.",
            },
            "equipment": _open_enum(
                SUPPORTED_FRAMEWORKS,
                "Test runner for this stage. 'command' runs any program given in 'args'. "
                "Plugins can add more.",
            ),
            "framework": _open_enum(SUPPORTED_FRAMEWORKS, "Legacy name for 'equipment'."),
            "target_repo": {
                "type": "string",
                "description": "Directory the runner starts in, relative to this file. "
                "Defaults to defaults.target_repo.",
            },
            "args": {
                "description": "Arguments for the runner, as a list or one shell-style string. "
                "For 'command' this is the whole command line.",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": ["string", "number"]}},
                ],
            },
            "workers": {
                "type": "integer",
                "minimum": 1,
                "description": "Parallel workers (pytest with xdist, behavex, playwright). "
                "Defaults to defaults.workers.",
            },
            "timeout_s": _timeout(defaults.timeout_s),
            "if": {
                "type": "string",
                "description": "Run the stage only when this expression is true.",
            },
            "extra_env": _env(),
            "tier": {
                "enum": sorted(SUPPORTED_TIERS),
                "description": "Test-pyramid tier the stage's tests count under. "
                f"Default by equipment: {tier_defaults}.",
            },
            "junit_xml": {
                "description": "Glob(s), relative to target_repo, of JUnit XML reports the "
                "stage writes. They are imported as results after the stage.",
                "oneOf": [
                    {"type": "string", "minLength": 1},
                    {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                ],
            },
        },
        "additionalProperties": False,
    }

    quarantine = {
        "type": "array",
        "description": "Tests whose failures don't fail their stage. They still run and still "
        "show as failed in results.",
        "items": {
            "anyOf": [
                {
                    "type": "string",
                    "minLength": 1,
                    "description": "fnmatch glob on the test's name or full name.",
                },
                {
                    "type": "object",
                    "required": ["test"],
                    "properties": {
                        "test": {
                            "type": "string",
                            "minLength": 1,
                            "description": "fnmatch glob on the test's name or full name.",
                        },
                        "reason": {"type": "string"},
                        "owner": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ]
        },
    }

    cycle = {
        "type": "object",
        "description": "A named list of stages, run with `testo run --cycle <name>`.",
        "required": ["stages"],
        "properties": {
            "description": {"type": "string"},
            "stages": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/stage"}},
            "quarantine": {
                "$ref": "#/definitions/quarantine",
                "description": "Added to the top-level quarantine list for this cycle.",
            },
            "trigger": {
                "type": "object",
                "description": "Run the cycle only when files matching these globs changed.",
                "required": ["paths"],
                "properties": {
                    "paths": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                        "description": "Globs relative to this file's directory.",
                    },
                    "since_ref": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Git ref to diff against, e.g. origin/main.",
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }

    reporter = {
        "type": "object",
        "description": "A post-run reporter. Keys other than 'type' are its options.",
        "required": ["type"],
        "properties": {
            "type": _open_enum(SUPPORTED_REPORTER_TYPES, "Reporter type. Plugins can add more."),
            "output_dir": {"type": "string", "description": "Relative to this file."},
            "out_dir": {"type": "string", "description": "Relative to this file."},
        },
        "additionalProperties": True,
    }

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": SCHEMA_ID,
        "title": "testosterone.yaml",
        "description": "Config for Testosterone (testo-core): cycles of test stages and reporters.",
        "type": "object",
        "required": ["cycles"],
        "properties": {
            "version": {"type": "integer", "enum": [1], "default": 1},
            "defaults": {
                "type": "object",
                "description": "Values every stage inherits unless it sets its own.",
                "properties": {
                    "target_repo": {"type": "string", "default": str(defaults.target_repo)},
                    "artifacts_root": {"type": "string", "default": str(defaults.artifacts_root)},
                    "timeout_s": _timeout(defaults.timeout_s),
                    "workers": {"type": "integer", "minimum": 1, "default": defaults.workers},
                    "extra_env": _env(),
                },
                "additionalProperties": False,
            },
            "database": {
                "type": "object",
                "description": "Where run history is stored. DATABASE_URL overrides it.",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "SQLAlchemy URL, e.g. sqlite:////tmp/testo.db or "
                        "postgresql+psycopg://user:pass@host/db.",
                    }
                },
                "additionalProperties": False,
            },
            "reporters": {"type": "array", "items": {"$ref": "#/definitions/reporter"}},
            "quarantine": {"$ref": "#/definitions/quarantine"},
            "cycles": {
                "type": "object",
                "minProperties": 1,
                "propertyNames": {"not": {"const": "all"}, "pattern": _NAME_PATTERN},
                "additionalProperties": {"$ref": "#/definitions/cycle"},
            },
        },
        "additionalProperties": False,
        "definitions": {
            "stage": stage,
            "cycle": cycle,
            "quarantine": quarantine,
            "reporter": reporter,
        },
    }
