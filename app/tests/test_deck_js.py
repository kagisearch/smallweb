"""Run the deck.js state-machine tests as part of the normal pytest run.

deck.js owns the queue and history bookkeeping behind Next, and its bugs look
exactly like server bugs from the outside (same post twice, dead button). Node
is not a hard dependency of the app, so this skips when it is missing rather
than failing the suite.
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
DECK_TEST = os.path.join(TESTS_DIR, "deck.test.mjs")


def test_deck_js_state_machine():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    result = subprocess.run(
        [node, "--test", DECK_TEST],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
