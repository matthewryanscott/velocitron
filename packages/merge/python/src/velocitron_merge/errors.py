"""Errors raised by the composition merge."""

from __future__ import annotations


class NetValidationError(Exception):
    """A composition merge rejected its inputs.

    The message matches ``velocitron_petrinet.NetValidationError`` for the
    same rejection. This package does not import ``velocitron``.
    """
