"""Sphinx configuration for PyMusicLooper documentation (HTML and man pages)."""

from __future__ import annotations

import contextlib
import os
import re
import sys

import click
from rich.errors import MarkupError
from rich.text import Text

# Ensure the repository root is importable for sphinx.ext.autodoc and sphinx_click
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pymusiclooper.cli  # noqa: F401, E402
from pymusiclooper import __version__ as _installed_version

# rich_click.patch.patch() replaces click.Group with _PatchedRichGroup, which
# breaks sphinx-click's isinstance(cmd, click.Group) check on Click >= 8.2.
click.Group = click.core.Group


def _get_project_version() -> str:
    pyproject_path = os.path.join(_REPO_ROOT, "pyproject.toml")
    try:
        with open(pyproject_path, encoding="utf-8") as f:
            match = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.MULTILINE)
        if match:
            return match.group(1)
    except OSError:
        pass
    return _installed_version


project = "PyMusicLooper"
author = "arkrow"
copyright = "2020-2026, arkrow"
release = _get_project_version()
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_click",
]

templates_path = []
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML output
html_theme = "furo"
html_title = f"{project} {release}"

# Man page output: `sphinx-build -b man docs docs/_build/man`
man_pages = [
    (
        "cli",
        "pymusiclooper",
        "Repeat music endlessly and create seamless music loops",
        [author],
        1,
    ),
]


def _strip_rich_markup_from_lines(lines: list[str]) -> None:
    """Strips Rich console markup tags from sphinx-click generated reST lines in place."""
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith((".. ", ":")):
            continue
        with contextlib.suppress(MarkupError):
            lines[idx] = Text.from_markup(line).plain


def _process_sphinx_click_lines(app, ctx, lines: list[str]) -> None:
    _strip_rich_markup_from_lines(lines)


def setup(app):
    for event in (
        "sphinx-click-process-description",
        "sphinx-click-process-options",
        "sphinx-click-process-arguments",
        "sphinx-click-process-epilog",
    ):
        app.connect(event, _process_sphinx_click_lines)

    return {
        "version": release,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
