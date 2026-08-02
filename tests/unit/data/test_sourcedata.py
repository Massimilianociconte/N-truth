"""Tests for SourceData lockfile loading and file validation."""

from __future__ import annotations

import pytest

from ntruth.data.datasets.sourcedata import SourceDataError, load_sourcedata_lockfile


def test_load_sourcedata_lockfile():
    lock = load_sourcedata_lockfile()
    assert lock["repository"] == "EMBO/SourceData"
    assert lock["semantic_version"] == "2.0.3"
    assert len(lock["files"]) == 6
    assert all(len(f["sha256"]) == 64 for f in lock["files"])
