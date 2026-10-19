#!/usr/bin/env bash
# Install a built testo-core wheel into a clean virtualenv with no extras and
# run a one-stage pytest cycle with it, the way a new user would after
# `pip install testo-core`. Catches runtime imports that only the dev extras
# provided. Usage: scripts/package_smoke.sh [dist-dir]   (default: dist)
set -euo pipefail

dist_dir="$(cd "${1:-dist}" && pwd)"
wheel="$(ls "$dist_dir"/testo_core-*.whl | head -n 1)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python -m venv "$work/venv"
export PATH="$work/venv/bin:$PATH"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "$wheel" pytest

mkdir -p "$work/project/tests"
cd "$work/project"
cat > tests/test_smoke.py <<'PY'
def test_smoke():
    assert True
PY
cat > testosterone.yaml <<'YAML'
version: 1
cycles:
  smoke:
    stages:
      - name: unit
        equipment: pytest
        args: ["-q", "tests"]
YAML

testo --version
testo config validate
testo run --cycle smoke
test -f testo_history.db
echo "package smoke passed: $(basename "$wheel")"
