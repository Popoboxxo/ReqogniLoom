"""
Pytest configuration for the ReqogniLoom backend test suite.
"""
import os
import sys
from pathlib import Path
from typing import Optional

from pytest import Dir

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


def pytest_collect_directory(path: Path, parent) -> Optional[Dir]:
    """Collect the hyphenated plugin dir as a plain dir instead of a package.

    ``hermes-agent-plugin`` is not a valid Python package name, so pytest's
    ``Package`` collector would import its ``__init__.py`` as a top-level
    module and die on the relative import inside it. ``collect_ignore`` cannot
    prevent this: an ancestor of the initial path is collected through
    ``Session._collect_path``, which calls this hook directly and never
    consults ``pytest_ignore_collect``.
    """
    if path.name == 'hermes-agent-plugin' and (path / '__init__.py').is_file():
        return Dir.from_parent(parent, path=path)
    return None
