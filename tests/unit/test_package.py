"""Smoke tests for the package skeleton.

They prove the package is installed correctly and exposes a single-sourced version.
"""

import re
from importlib.metadata import version

import it_equipment


def test_version_matches_installed_distribution_metadata():
    assert it_equipment.__version__ == version("it-equipment-handler")


def test_version_follows_semantic_versioning():
    assert re.fullmatch(r"\d+\.\d+\.\d+", it_equipment.__version__)
