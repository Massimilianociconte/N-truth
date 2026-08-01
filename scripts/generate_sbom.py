#!/usr/bin/env python3
"""Wrapper CLI per il generatore SBOM installabile di N-Truth."""

from ntruth.release.sbom import main

if __name__ == "__main__":
    raise SystemExit(main())
