"""Resolve the bundled Velocitron authoring skill.

The authoring source of truth is the repo-root ``skills/velocitron/`` tree.
``velocitron_skill/skill`` symlinks that directory, and the wheel ships the
files it points at. :func:`skill_root` reads the directory through
:mod:`importlib.resources`, so an editable install and a wheel use one path.

This package does not install a console script and does not import
``velocitron``. ``velocitron skill`` lives in ``velocitron_cli`` and copies
the directory this function returns. The map of how the packages fit
together for an agent is ``skills/README.md``.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

__all__ = ["skill_root"]


def skill_root() -> Path:
    """Return the bundled skill directory that contains ``SKILL.md``.

    Raises:
        FileNotFoundError: The packaged skill marker is missing.
    """
    resource = importlib.resources.files("velocitron_skill").joinpath("skill")
    source = Path(str(resource))
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError("bundled velocitron skill data not found")
    return source
