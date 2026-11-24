"""Console commands for Velocitron.

``main`` is the ``velocitron`` dispatcher. ``viz_main`` is
``velocitron-viz``. ``main`` calls :func:`install_default_hooks`, which
fills canonical emission, explain, equiv, and the CEL backend hint from
the packages that own them. ``skill`` reads
:func:`velocitron_skill.skill_root` unless ``configure(skill_source=...)``
overrides it. The console scripts are ``velocitron`` and ``velocitron-viz``.

This package does not import ``velocitron``.
"""

from __future__ import annotations

from .check import (
    CheckReport,
    MarkdownFence,
    check_markdown_file,
    check_paths,
    check_petrinet_file,
    check_play_file,
    extract_fences,
)
from .codegen import (
    add_parser as codegen_add_parser,
)
from .codegen import (
    document_kind as codegen_document_kind,
)
from .codegen import (
    generate as codegen_generate,
)
from .codegen import (
    generate_composition_cli as codegen_generate_composition,
)
from .codegen import (
    main as codegen_main,
)
from .dispatch import main
from .dispatch import parser as build_parser
from .host import HOST, configure
from .prove import add_parser as prove_add_parser
from .prove import main as prove_main
from .viz import main as viz_main

__all__ = [
    "HOST",
    "CheckReport",
    "MarkdownFence",
    "build_parser",
    "check_markdown_file",
    "check_paths",
    "check_petrinet_file",
    "check_play_file",
    "codegen_add_parser",
    "codegen_document_kind",
    "codegen_generate",
    "codegen_generate_composition",
    "codegen_main",
    "configure",
    "extract_fences",
    "main",
    "prove_add_parser",
    "prove_main",
    "viz_main",
]
