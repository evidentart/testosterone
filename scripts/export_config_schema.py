"""Write the ``testosterone.yaml`` JSON Schema to ``schema/testosterone.schema.json``.

Editors load the committed file (by URL or a relative ``$schema`` modeline) to
autocomplete and validate configs. It is generated from
:mod:`testo_core.config.json_schema`; CI re-runs this script and fails if the
committed file is stale.

Usage::

    python scripts/export_config_schema.py            # write the file
    python scripts/export_config_schema.py --check    # exit 1 if it is out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "testosterone.schema.json"


def render_schema() -> str:
    from testo_core.config.json_schema import build_json_schema

    return json.dumps(build_json_schema(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the testosterone.yaml JSON Schema.")
    parser.add_argument(
        "--check", action="store_true", help="fail if the committed schema is stale"
    )
    args = parser.parse_args(argv)

    rendered = render_schema()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != rendered:
            print(
                f"{SCHEMA_PATH.relative_to(REPO_ROOT)} is out of date. Run "
                "`python scripts/export_config_schema.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        return 0

    SCHEMA_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
