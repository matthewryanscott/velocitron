"""Hooks for canonical emission, explain, equiv, and the CEL backend hint.

:func:`install_default_hooks` fills any hook that is still unset from the
package that owns it. :func:`configure` replaces the hooks that are passed.
Omitted arguments stay as they are. Pass ``None`` to clear a hook. Clearing
``skill_source`` selects ``skill_root`` again. The bundled skill directory
is :func:`velocitron_skill.skill_root` unless ``skill_source`` overrides it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EmitPetrinet = Callable[..., str]
ExplainNet = Callable[..., str]
EquivAddParser = Callable[[Any], None]
EquivMain = Callable[[Any], int]
SlowBackendHint = Callable[..., str | None]
SkillSource = Callable[[], Path]

_UNSET: Any = object()


@dataclass
class CliHost:
    """Umbrella hooks and the few callables tests replace.

    ``parse_net``, ``compile_document``, and ``validate_document`` stay
    unset in production. A test may assign them for one call.
    ``backend_hint_shown`` is the once-per-process CEL hint flag.
    """

    emit_petrinet: EmitPetrinet | None = None
    explain_net: ExplainNet | None = None
    equiv_add_parser: EquivAddParser | None = None
    equiv_main: EquivMain | None = None
    slow_backend_hint: SlowBackendHint | None = None
    skill_source: SkillSource | None = None
    parse_net: Callable[..., Any] | None = None
    compile_document: Callable[..., Any] | None = None
    validate_document: Callable[..., Any] | None = None
    backend_hint_shown: bool = False


HOST = CliHost()


def install_default_hooks() -> None:
    """Fill hooks that are still unset. A hook that is already set stays."""
    from velocitron_cel import slow_backend_hint
    from velocitron_dsl import emit_petrinet
    from velocitron_equiv import add_parser as equiv_add_parser
    from velocitron_equiv import main as equiv_main
    from velocitron_explain import explain_net

    if HOST.emit_petrinet is None:
        HOST.emit_petrinet = emit_petrinet
    if HOST.explain_net is None:
        HOST.explain_net = explain_net
    if HOST.equiv_add_parser is None:
        HOST.equiv_add_parser = equiv_add_parser
    if HOST.equiv_main is None:
        HOST.equiv_main = equiv_main
    if HOST.slow_backend_hint is None:
        HOST.slow_backend_hint = slow_backend_hint


def configure(
    *,
    emit_petrinet: Any = _UNSET,
    explain_net: Any = _UNSET,
    equiv_add_parser: Any = _UNSET,
    equiv_main: Any = _UNSET,
    slow_backend_hint: Any = _UNSET,
    skill_source: Any = _UNSET,
) -> None:
    """Replace the hooks that are passed.

    ``None`` clears a hook. ``skill_source=None`` clears an override and
    the dispatcher uses :func:`velocitron_skill.skill_root`.
    """
    if emit_petrinet is not _UNSET:
        HOST.emit_petrinet = emit_petrinet
    if explain_net is not _UNSET:
        HOST.explain_net = explain_net
    if equiv_add_parser is not _UNSET:
        HOST.equiv_add_parser = equiv_add_parser
    if equiv_main is not _UNSET:
        HOST.equiv_main = equiv_main
    if slow_backend_hint is not _UNSET:
        HOST.slow_backend_hint = slow_backend_hint
    if skill_source is not _UNSET:
        HOST.skill_source = skill_source


__all__ = ["HOST", "configure", "install_default_hooks"]
