"""Register a generated net class and check its digest.

``VelocitronNet`` is the base every generated Python net extends.
``register_into`` copies the net, stamps synthesized handler refs, adapts
methods onto the engine registry, and records async
:class:`~velocitron_runtime.HandlerSpec` values. ``HashMismatch`` is the
digest gate. ``handler_spec`` declares a method's lane.

``net_document``, ``canonical_net_json``, ``net_sha256``, and
``SYNTH_HANDLER`` live in ``velocitron_codegen`` and are re-exported so
registration checks the same bytes the generator stamps.

The TypeScript package names this seam and does not register a net.
``velocitron_replay`` subclasses :class:`VelocitronNet` through this
package. ``velocitron_replay`` re-exports that driver. Generated modules
still import ``velocitron_netbase``, which re-exports this package. This
package does not import ``velocitron``.
"""

from __future__ import annotations

from .base import (
    SYNTH_HANDLER,
    HashMismatch,
    Registration,
    VelocitronNet,
    canonical_net_json,
    handler_spec,
    net_document,
    net_sha256,
)

__all__ = [
    "SYNTH_HANDLER",
    "HashMismatch",
    "Registration",
    "VelocitronNet",
    "canonical_net_json",
    "handler_spec",
    "net_document",
    "net_sha256",
]
