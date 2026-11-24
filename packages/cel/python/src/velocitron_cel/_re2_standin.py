"""A stand-in for ``google-re2``, backed by Python's ``re`` (ADR 0054).

celpy uses only ``re2.search`` and ``re2.error``, for CEL's ``matches()``.
The bundled celpy (``velocitron_cel._vendor.celpy``) uses this module when the real
``re2`` does not import. ``matches()`` then follows Python's regex rules,
not RE2's: ``re`` accepts backreferences and lookaround, which RE2 rejects,
and ``re`` can take exponential time on some patterns, where RE2 is linear.
"""

from re import error, search

__all__ = ["error", "search"]
