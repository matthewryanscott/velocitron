#!/usr/bin/env python3
"""Guard that ``velocitron-netbase`` stays the registration-base source."""

from __future__ import annotations

import sys

from umbrella_thin import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv, "netbase"))
