"""Allure Report 3 CLI resolution and subprocess helpers."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from testo_core.paths import source_checkout_root

DEFAULT_ALLURE_VERSION = (os.environ.get("TESTO_ALLURE_VERSION") or "3").strip()
ALLURE_CONFIG_NAMES = ("allurerc.mjs", "allurerc.js", "allurerc.cjs")


class AllureCLINotFoundError(RuntimeError):
    """Raised when the Allure 3 CLI cannot be resolved."""


@dataclass(frozen=True)
class AllureCommand:
    """Resolved argv prefix to invoke the Allure CLI."""

    argv: tuple[str, ...]
    cwd: Path


def find_repo_root(*, start: Path | None = None) -> Path:
    """Walk parents from ``start`` (or cwd) for a directory containing ``allurerc.mjs``."""
    cur = (start or Path.cwd()).expanduser().resolve()
    for directory in (cur, *cur.parents):
        if any((directory / name).is_file() for name in ALLURE_CONFIG_NAMES):
            return directory
        if (directory / "package.json").is_file() and (
            directory / "node_modules" / ".bin" / "allure"
        ).is_file():
            return directory
    return source_checkout_root() or cur


def find_config_path(*, repo_root: Path | None = None) -> Path | None:
    root = (repo_root or find_repo_root()).expanduser().resolve()
    for name in ALLURE_CONFIG_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def resolve_allure_command(*, repo_root: Path | None = None) -> AllureCommand:
    """
    Resolve how to invoke Allure 3.

    Precedence: ``TESTO_ALLURE_BIN`` → ``node_modules/.bin/allure`` → ``allure`` on PATH
    → ``npx --yes allure@<version>``.
    """
    root = (repo_root or find_repo_root()).expanduser().resolve()
    override = (os.environ.get("TESTO_ALLURE_BIN") or "").strip()
    if override:
        return AllureCommand(argv=(override,), cwd=root)

    local_bin = root / "node_modules" / ".bin" / "allure"
    if local_bin.is_file():
        return AllureCommand(argv=(str(local_bin),), cwd=root)

    on_path = shutil.which("allure")
    if on_path:
        return AllureCommand(argv=(on_path,), cwd=root)

    npx = shutil.which("npx")
    if npx:
        return AllureCommand(argv=(npx, "--yes", f"allure@{DEFAULT_ALLURE_VERSION}"), cwd=root)

    raise AllureCLINotFoundError(_install_hint(root))


def is_allure_available(*, repo_root: Path | None = None) -> bool:
    try:
        resolve_allure_command(repo_root=repo_root)
        return True
    except AllureCLINotFoundError:
        return False


def _install_hint(repo_root: Path) -> str:
    return (
        "Allure Report 3 CLI was not found. Install Node.js 18+ and run "
        f"`npm install` in {repo_root}, set TESTO_ALLURE_BIN, or use "
        "`testo report --format json`."
    )


def _subprocess_env() -> dict[str, str]:
    return dict(os.environ)


def run_subprocess(
    argv: list[str],
    *,
    cwd: Path,
    capture_output: bool = False,
    check: bool = False,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    runner = subprocess_run or subprocess.run
    return runner(  # noqa: S603
        argv,
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=capture_output,
        env=_subprocess_env(),
    )


def build_generate_argv(
    *,
    result_dirs: Sequence[Path],
    out_dir: Path,
    config_path: Path | None = None,
    report_name: str | None = None,
    single_file: bool = False,
) -> list[str]:
    cmd = resolve_allure_command()
    subcommand = "awesome" if single_file else "generate"
    argv: list[str] = [*cmd.argv, subcommand]
    cfg = config_path or find_config_path(repo_root=cmd.cwd)
    if cfg is not None:
        argv.extend(["--config", str(cfg.resolve())])
    argv.extend(["--output", str(out_dir.expanduser().resolve())])
    if report_name:
        argv.extend(["--name", report_name])
    if single_file:
        argv.append("--single-file")
    argv.extend(str(p.expanduser().resolve()) for p in result_dirs)
    return argv


def build_open_argv(
    *,
    paths: Sequence[Path],
    config_path: Path | None = None,
    port: int | None = None,
) -> list[str]:
    cmd = resolve_allure_command()
    argv: list[str] = [*cmd.argv, "open"]
    cfg = config_path or find_config_path(repo_root=cmd.cwd)
    if cfg is not None:
        argv.extend(["--config", str(cfg.resolve())])
    if port is not None and int(port) > 0:
        argv.extend(["--port", str(int(port))])
    argv.extend(str(p.expanduser().resolve()) for p in paths)
    return argv


def run_generate(
    *,
    result_dirs: Sequence[Path],
    out_dir: Path,
    clean: bool = True,
    single_file: bool = False,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    out = out_dir.expanduser().resolve()
    if clean and out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    cmd = resolve_allure_command()
    argv = build_generate_argv(
        result_dirs=result_dirs,
        out_dir=out,
        single_file=single_file,
    )
    return run_subprocess(argv, cwd=cmd.cwd, capture_output=True, subprocess_run=subprocess_run)


def run_open_blocking(
    *,
    paths: Sequence[Path],
    port: int = 8080,
    subprocess_popen: Callable[..., subprocess.Popen[bytes]] | None = None,
) -> int:
    """Run ``allure open`` and block until the process exits (Ctrl-C → 130)."""
    if not paths:
        return 1
    cmd = resolve_allure_command()
    argv = build_open_argv(paths=paths, port=port)
    popen = subprocess_popen or subprocess.Popen  # noqa: S603
    proc = popen(
        argv,
        cwd=str(cmd.cwd),
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=None,
        env=_subprocess_env(),
    )
    try:
        return int(proc.wait())
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGTERM)
        try:
            return int(proc.wait(timeout=5.0))
        except subprocess.TimeoutExpired:
            proc.kill()
            return 130


def report_has_index(out_dir: Path) -> bool:
    out = out_dir.expanduser().resolve()
    return (out / "index.html").is_file()
