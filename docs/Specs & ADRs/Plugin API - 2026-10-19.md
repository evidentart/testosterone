---
type: spec
status: current
created: 2026-10-19
updated: 2026-10-19
---

# Plugin API - 2026-10-19

## Context

Adding a test runner or a reporter meant a pull request to Testosterone: an adapter in `testo_core/frameworks/` or a reporter in `testo_core/reporting/reporters/`, plus its name in `SUPPORTED_FRAMEWORKS` or `SUPPORTED_REPORTER_TYPES`. The `command` framework covers runners that write JUnit XML, but anything else (a runner that needs flags injected, a reporter that posts to a team's own service) had no way in from outside the repository. Open-source users should be able to ship those as their own packages.

## Decision

- Two [entry point](https://packaging.python.org/en/latest/specifications/entry-points/) groups: `testo.frameworks` (a `FrameworkAdapter` class or factory) and `testo.reporters` (a `BaseReporter` subclass). The interfaces are the ones the built-ins already implement, so a plugin and a built-in look the same to the engine.
- `testo_core/plugins.py` owns discovery. The config loader, `get_adapter()`, `ReporterFactory` and the ad-hoc plan builder ask it for the known names instead of reading the frozensets directly.
- Built-in names always win, and the first plugin to claim a name keeps it; the rest are ignored with a warning. A plugin can add, never replace.
- Entry points are read once per process and a plugin is imported only when a stage or reporter uses it. Import errors and missing methods become a `PluginError` that names the package.
- `testo plugins` lists everything; `--check` imports each plugin, which is the test a plugin author runs.
- `examples/plugin/` is a complete plugin (a `unittest` adapter that writes Allure results, a `json-summary` reporter) and `tests/unit/testo_core/test_plugins.py` runs a real cycle through it.

We chose entry points over a pluggy hook system or a `plugins:` list of import paths in YAML: they are the standard Python mechanism, need no new dependency, and installing the package is the whole setup.

## Consequences

- Plugin stages have no default tier beyond `unit` and receive `workers` unchanged; the plugin decides what it means.
- The API's ad-hoc endpoint keeps its `Literal` of built-in frameworks so the OpenAPI schema and generated frontend types stay static. Plugin frameworks run through cycles.
- The adapter and reporter interfaces are now public API: changing them is a breaking change for plugins and needs a major version.

Usage: [Command Reference § Plugins](../CLI%20Commands/Command%20Reference.md#plugins).
