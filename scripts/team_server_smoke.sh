#!/usr/bin/env bash
# Start the team server (deploy/server/docker-compose.yml: server image + Postgres),
# upload JUnit XML to it with `testo ingest --server`, and check the run, the
# token and the UI. Needs Docker and a `testo` on PATH (this checkout, installed).
# Usage: scripts/team_server_smoke.sh   (TESTO_SERVER_PORT defaults to 8000;
#        TESTO_SMOKE_NO_BUILD=1 uses an already built ghcr.io/taltal-beep/testo-server:1)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose -f "$root/deploy/server/docker-compose.yml" -p testo-smoke)
port="${TESTO_SERVER_PORT:-8000}"
export TESTO_SERVER_PORT="$port"
export TESTO_API_TOKEN="smoke-$RANDOM-$RANDOM"
base="http://127.0.0.1:$port"
work="$(mktemp -d)"
cleanup() {
  "${compose[@]}" logs server | tail -n 30 || true
  "${compose[@]}" down -v >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

build=(--build)
[ "${TESTO_SMOKE_NO_BUILD:-}" = 1 ] && build=(--no-build)
"${compose[@]}" up -d "${build[@]}" --wait

mkdir -p "$work/reports"
cat > "$work/reports/unit.xml" <<'XML'
<testsuite name="cart"><testcase classname="cart" name="adds item" time="0.2"/></testsuite>
XML
cat > "$work/reports/e2e.xml" <<'XML'
<testsuite name="checkout"><testcase classname="checkout" name="pays" time="1.5">
<failure message="timeout">Timed out</failure></testcase></testsuite>
XML
cd "$work"

# A wrong token is refused (exit 3), and nothing is recorded.
if testo ingest reports/unit.xml --cycle smoke --server "$base" --token wrong; then
  echo "::error::upload with a wrong token was accepted"; exit 1
else
  test $? -eq 3
fi

testo ingest reports/unit.xml --cycle smoke --server "$base"
set +e
testo ingest 'reports/*.xml' --cycle smoke --server "$base" --ci > upload.ndjson
code=$?
set -e
cat upload.ndjson
test "$code" -eq 1  # a failed test makes the upload exit 1, like `testo run`
grep -q '"tests":2' upload.ndjson

runs="$(curl -fsS "$base/api/v1/runs")"
echo "$runs" | python -c 'import json,sys; items=json.load(sys.stdin)["items"]; assert len(items) == 2, items; assert {i["cycle"] for i in items} == {"smoke"}'
curl -fsS "$base/" | grep -q '<div id="root">'
curl -fsS "$base/runs/anything" | grep -q '<div id="root">'
echo "team server smoke: ok"
