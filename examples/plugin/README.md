# Example plugin

A complete Testosterone plugin in two short files: a framework adapter that runs the standard library's `unittest` and a reporter that writes the run's counts to JSON. Copy it as the starting point for your own runner or reporter.

```bash
pip install testo-core -e examples/plugin
cd examples/plugin
testo plugins --check        # unittest and json-summary are listed, status ok
testo run --cycle unit       # 2 passed; reports/summary.json written
```

- [`pyproject.toml`](pyproject.toml) registers both through the `testo.frameworks` and `testo.reporters` entry point groups.
- [`testo_example_plugin/__init__.py`](testo_example_plugin/__init__.py) has the adapter (`build_argv` returns the command) and the reporter (`publish` receives the collected results).
- [`testo_example_plugin/runner.py`](testo_example_plugin/runner.py) writes one Allure `*-result.json` per test into the results directory the adapter is given, which is all Testosterone needs to count, diff and track the tests.

The plugin interface is described in the [Command Reference](../../docs/CLI%20Commands/Command%20Reference.md#plugins).
