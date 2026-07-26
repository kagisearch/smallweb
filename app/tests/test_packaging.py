"""Every template and static asset the app references must be in git.

The deployed image is built from the git checkout (`COPY app/ .`), so a file
that exists only in a working directory renders fine locally and 500s in
production. These tests catch a forgotten `git add` before it ships.
"""
import os
import re
import subprocess

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(APP_DIR)

# Covers `{% include "x.html" %}` and `render_template("x.html", ...)`, including
# the calls in sw.py that put the template name on the following line.
TEMPLATE_REF = re.compile(
    r"""(?:\{%-?\s*include\s+|render_template\(\s*)["']([^"']+\.html)["']"""
)
STATIC_REF = re.compile(
    r"""url_for\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"]([^'"]+)['"]"""
)


def _tracked_files():
    result = subprocess.run(
        ["git", "-C", REPO_DIR, "ls-files"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return set(result.stdout.splitlines())


def _references():
    """Every template name and static filename referenced by app code."""
    paths = [
        os.path.join(APP_DIR, name)
        for name in os.listdir(APP_DIR)
        if name.endswith(".py")
    ]
    for root, _dirs, files in os.walk(os.path.join(APP_DIR, "templates")):
        paths += [os.path.join(root, f) for f in files if f.endswith(".html")]

    templates, statics = set(), set()
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        templates.update(TEMPLATE_REF.findall(text))
        statics.update(STATIC_REF.findall(text))
    return templates, statics


def test_referenced_templates_are_tracked():
    tracked = _tracked_files()
    templates, _ = _references()
    assert templates, "found no template references; the regex has drifted"
    missing = sorted(
        name for name in templates if f"app/templates/{name}" not in tracked
    )
    assert not missing, f"referenced but not in git (will 500 when deployed): {missing}"


def test_referenced_static_assets_are_tracked():
    tracked = _tracked_files()
    _, statics = _references()
    assert statics, "found no static references; the regex has drifted"
    missing = sorted(name for name in statics if f"app/static/{name}" not in tracked)
    assert not missing, f"referenced but not in git (will 404 when deployed): {missing}"
