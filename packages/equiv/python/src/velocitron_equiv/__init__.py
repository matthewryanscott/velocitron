"""Structural equivalence of two merged nets up to renaming (ADR 0042).

:func:`compare` maps places, transitions, and arcs by local name and
compares behavior facts. Ports are interface and do not count against
equivalence. :func:`load` from ``velocitron_analysis`` reads each side.
:func:`main` is the ``velocitron equiv`` command body.

``velocitron_cli`` installs :func:`add_parser` and :func:`main` for
``velocitron equiv``. The TypeScript package names
``compare`` and ``Equivalence`` and does not compare nets. This package
does not import ``velocitron``.
"""

from __future__ import annotations

from .equiv import Equivalence, add_parser, compare, main

__all__ = ["Equivalence", "add_parser", "compare", "main"]
