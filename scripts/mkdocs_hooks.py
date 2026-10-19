"""MkDocs hooks that render the docs/ vault as a site without changing the notes.

The notes stay plain GitHub/Obsidian markdown (docs/CLAUDE.md). These hooks
bridge the differences when mkdocs.yml builds them:

- ``Index.md`` becomes the home page, and every page gets a lowercase,
  hyphenated URL (``CLI Commands/Command Reference.md`` -> ``cli-commands/command-reference/``).
- The vault's ``status`` frontmatter key is dropped: Material reads it as a
  page badge and would mark every page in the nav.
- Links that leave ``docs/`` (``../README.md``, ``../testo_core/...``) point at
  the file on GitHub, the same rewrite the wiki export does.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docs_vault import _EXTERNAL_RE, _LINK_RE, DOCS_ROOT, INDEX, REPO_ROOT, _mask_code  # noqa: E402

REPO = "taltal-beep/testosterone"
REF = "main"
_BLOB = f"https://github.com/{REPO}/blob/{REF}"
_RAW = f"https://raw.githubusercontent.com/{REPO}/{REF}"
# Pages whose file name makes a poor URL.
_RENAMED = {"CLAUDE.md": "vault-schema/index.html"}


def _slug(part: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", part.lower().replace("&", "and")).strip("-")


def page_dest(src_uri: str) -> str:
    """Map a docs-relative markdown path to its output path."""
    if src_uri == INDEX:
        return "index.html"
    if src_uri in _RENAMED:
        return _RENAMED[src_uri]
    path = Path(src_uri)
    folders = [_slug(p) for p in path.parent.parts]
    if path.name != "README.md":
        folders.append(_slug(path.stem))
    return "/".join([*folders, "index.html"])


def on_files(files: Any, config: Any) -> Any:
    for file in files.documentation_pages():
        file.dest_uri = page_dest(file.src_uri)
        file.url = file.dest_uri.removesuffix("index.html")
    return files


def rewrite_outside_links(markdown: str, src_uri: str) -> str:
    """Point links whose target is outside docs/ at the file on GitHub."""
    note_dir = (DOCS_ROOT / src_uri).parent
    masked = _mask_code(markdown)
    out: list[str] = []
    last = 0
    for match in _LINK_RE.finditer(masked):
        bang, _, target = match.groups()
        if _EXTERNAL_RE.match(target) or target.startswith("#"):
            continue
        path, _, anchor = target.partition("#")
        resolved = (note_dir / unquote(path)).resolve()
        if resolved.is_relative_to(DOCS_ROOT):
            continue
        try:
            repo_rel = resolved.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        suffix = f"#{anchor}" if anchor else ""
        label = markdown[match.start(2) : match.end(2)]
        out.append(markdown[last : match.start()])
        out.append(f"{bang}[{label}]({_RAW if bang else _BLOB}/{quote(repo_rel)}{suffix})")
        last = match.end()
    out.append(markdown[last:])
    return "".join(out)


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    page.meta.pop("status", None)
    return rewrite_outside_links(markdown, page.file.src_uri)
