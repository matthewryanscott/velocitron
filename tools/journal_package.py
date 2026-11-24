#!/usr/bin/env python3
"""Guard that ``velocitron-journal`` stays the journal-durability source."""

from __future__ import annotations

import sys

from umbrella_thin import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv, "journal"))
