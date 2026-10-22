"""Third-party framework adapters and reporters, found through entry points.

A package adds a runner or a reporter without changing Testosterone by
declaring an entry point in its ``pyproject.toml``::

    [project.entry-points."testo.frameworks"]
    cargo = "testo_cargo:CargoAdapter"        # a FrameworkAdapter class or factory

    [project.entry-points."testo.reporters"]
    discord = "testo_discord:DiscordReporter" # a BaseReporter subclass

Once it is installed, ``equipment: cargo`` and ``reporters: [{type: discord}]``
work in ``testosterone.yaml`` and ``testo plugins`` lists them. Built-in names
always win: a plugin that reuses one is ignored with a warning.

Entry points are read once per process and a plugin is imported only when a
stage or reporter uses it, so ``testo --help`` never imports plugin code.
See docs/Specs & ADRs/Plugin API - 2026-10-19.md.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING, Literal

from testo_core.config.schema import SUPPORTED_FRAMEWORKS, SUPPORTED_REPORTER_TYPES

if TYPE_CHECKING:
    from testo_core.frameworks.base import FrameworkAdapter
    from testo_core.reporting.reporters.base import BaseReporter

logger = logging.getLogger(__name__)

FRAMEWORK_GROUP = "testo.frameworks"
REPORTER_GROUP = "testo.reporters"

PluginKind = Literal["framework", "reporter"]
_GROUPS: dict[PluginKind, tuple[str, frozenset[str]]] = {
    "framework": (FRAMEWORK_GROUP, SUPPORTED_FRAMEWORKS),
    "reporter": (REPORTER_GROUP, SUPPORTED_REPORTER_TYPES),
}
_ADAPTER_METHODS = ("results_subdir", "build_argv", "native_report")


class PluginError(ValueError):
    """A plugin could not be imported or does not implement its interface."""


@dataclass(frozen=True)
class PluginInfo:
    kind: PluginKind
    name: str
    target: str  # "module:attr", as declared
    package: str | None  # distribution that declared it, with its version


def _package(ep: EntryPoint) -> str | None:
    dist = ep.dist
    if dist is None:
        return None
    return f"{dist.metadata['Name']} {dist.version}"


@functools.cache
def _entry_points(kind: PluginKind) -> dict[str, EntryPoint]:
    group, builtins = _GROUPS[kind]
    found: dict[str, EntryPoint] = {}
    for ep in entry_points(group=group):
        name = ep.name.strip().lower()
        if name in builtins:
            logger.warning(
                "ignoring %s plugin %r from %s: the name is built in", kind, name, _package(ep)
            )
            continue
        if name in found:
            logger.warning(
                "ignoring %s plugin %r from %s: %s already registered it",
                kind,
                name,
                _package(ep),
                _package(found[name]),
            )
            continue
        found[name] = ep
    return found


def clear_cache() -> None:
    """Forget discovered entry points (after installing a package, and in tests)."""
    _entry_points.cache_clear()


def framework_names() -> frozenset[str]:
    """Built-in frameworks plus installed ``testo.frameworks`` plugins."""
    return SUPPORTED_FRAMEWORKS | frozenset(_entry_points("framework"))


def reporter_types() -> frozenset[str]:
    """Built-in reporters plus installed ``testo.reporters`` plugins."""
    return SUPPORTED_REPORTER_TYPES | frozenset(_entry_points("reporter"))


def list_plugins() -> list[PluginInfo]:
    """Every installed plugin, frameworks first, sorted by name."""
    out: list[PluginInfo] = []
    for kind in _GROUPS:
        for name, ep in sorted(_entry_points(kind).items()):
            out.append(PluginInfo(kind=kind, name=name, target=ep.value, package=_package(ep)))
    return out


def _load(kind: PluginKind, name: str) -> object:
    ep = _entry_points(kind).get(name)
    if ep is None:
        raise PluginError(f"no {kind} plugin named {name!r}")
    try:
        return ep.load()
    except Exception as exc:
        # Broad on purpose: any import-time failure in third-party code is the plugin's.
        raise PluginError(
            f"{kind} plugin {name!r} ({ep.value}, from {_package(ep)}) failed to import: {exc}"
        ) from exc


def load_framework(name: str) -> FrameworkAdapter:
    """Instantiate the adapter a ``testo.frameworks`` plugin registered as ``name``."""
    factory = _load("framework", name)
    if not callable(factory):
        raise PluginError(f"framework plugin {name!r} is not a class or factory")
    adapter = factory()
    missing = [m for m in _ADAPTER_METHODS if not callable(getattr(adapter, m, None))]
    if missing:
        raise PluginError(
            f"framework plugin {name!r} does not implement FrameworkAdapter "
            f"(missing: {', '.join(missing)})"
        )
    return adapter  # type: ignore[no-any-return]


def load_reporter(name: str) -> type[BaseReporter]:
    """The reporter class a ``testo.reporters`` plugin registered as ``name``."""
    from testo_core.reporting.reporters.base import BaseReporter

    cls = _load("reporter", name)
    if not (isinstance(cls, type) and issubclass(cls, BaseReporter)):
        raise PluginError(f"reporter plugin {name!r} is not a BaseReporter subclass")
    return cls
