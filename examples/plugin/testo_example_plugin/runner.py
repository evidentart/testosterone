"""``python -m testo_example_plugin.runner RESULTS_DIR [unittest args]``.

Runs unittest discovery (or the given test names) and writes one Allure
``*-result.json`` per test into RESULTS_DIR. Exits 1 when a test failed.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
import uuid
from pathlib import Path


class _AllureResult(unittest.TextTestResult):
    def __init__(self, *args, results_dir: Path, **kwargs) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self._dir = results_dir
        self._start = 0

    def startTest(self, test: unittest.TestCase) -> None:  # noqa: N802
        self._start = int(time.time() * 1000)
        super().startTest(test)

    def _write(self, test: unittest.TestCase, status: str, message: str | None = None) -> None:
        test_id = test.id()
        data = {
            "uuid": str(uuid.uuid4()),
            "historyId": test_id,
            "name": test_id.rsplit(".", 1)[-1],
            "fullName": test_id,
            "status": status,
            "start": self._start,
            "stop": int(time.time() * 1000),
            "labels": [{"name": "suite", "value": test_id.rsplit(".", 1)[0]}],
        }
        if message:
            data["statusDetails"] = {"message": message}
        (self._dir / f"{data['uuid']}-result.json").write_text(json.dumps(data), encoding="utf-8")

    def addSuccess(self, test: unittest.TestCase) -> None:  # noqa: N802
        super().addSuccess(test)
        self._write(test, "passed")

    def addFailure(self, test, err) -> None:  # noqa: ANN001, N802
        super().addFailure(test, err)
        self._write(test, "failed", str(err[1]))

    def addError(self, test, err) -> None:  # noqa: ANN001, N802
        super().addError(test, err)
        self._write(test, "broken", str(err[1]))

    def addSkip(self, test, reason) -> None:  # noqa: ANN001, N802
        super().addSkip(test, reason)
        self._write(test, "skipped", reason)


def main(argv: list[str]) -> int:
    results_dir = Path(argv[0])
    results_dir.mkdir(parents=True, exist_ok=True)
    names = argv[1:]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(names) if names else loader.discover(".")
    runner = unittest.TextTestRunner(
        verbosity=2,
        resultclass=lambda *a, **k: _AllureResult(*a, results_dir=results_dir, **k),
    )
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
