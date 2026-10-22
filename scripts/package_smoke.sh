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
# Run data lands in the project (.testo/), never inside the installed package.
test -d .testo/static/history || { echo "no run data under .testo/" >&2; exit 1; }
site="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
if [ -e "$site/static" ] || [ -e "$site/static_reports" ]; then
  echo "run data was written under $site" >&2
  exit 1
fi
# The plain install stays lean: Behave and BehaveX come only with the [bdd] extra.
if python -c "import behave" 2>/dev/null || python -c "import behavex" 2>/dev/null; then
  echo "behave/behavex installed without the [bdd] extra" >&2
  exit 1
fi
echo "package smoke passed: $(basename "$wheel")"
