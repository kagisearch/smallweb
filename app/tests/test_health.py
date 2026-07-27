"""Cloud Run probe endpoints.

The deploy points its startup probe at /readyz and its liveness probe at
/healthz, so each has to actually fail for the condition it exists to catch:
feeds not loaded yet, and a gcsfuse data mount that has gone away. A probe that
can only ever return 200 is just a TCP check with extra steps.
"""
import os
import re

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(APP_DIR)


def test_readyz_ok_once_feeds_are_loaded(client):
    assert client.get("/readyz").status_code == 200


def test_readyz_503_before_feeds_load(app_module, client):
    # What an instance looks like while the import-time fetches are still
    # running: port bound, no post it could serve.
    app_module.urls_cache = []
    assert client.get("/readyz").status_code == 503


def test_healthz_ok_when_data_dir_is_reachable(client):
    assert client.get("/healthz").status_code == 200


def test_healthz_503_when_data_dir_is_unreachable(app_module, client, monkeypatch):
    # A dead gcsfuse daemon fails stat() with ENOTCONN; an absent path fails it
    # with ENOENT. The handler treats every OSError alike, so pointing at a
    # missing path drives the real code path without faking out os.stat.
    monkeypatch.setattr(app_module, "DIR_DATA", "/nonexistent/smallweb-data")
    assert client.get("/healthz").status_code == 503


def test_probe_paths_in_cloudbuild_are_registered_routes(app_module):
    """A renamed route would make every instance fail its startup probe.

    Cloud Run treats a 404 from a startup probe as a failure, so a drifted path
    here does not degrade the service -- it stops the revision from ever going
    live.
    """
    with open(os.path.join(REPO_DIR, "cloudbuild.yaml"), encoding="utf-8") as handle:
        probe_paths = set(re.findall(r"httpGet\.path=([^,'\"]+)", handle.read()))

    assert probe_paths, "found no probe paths in cloudbuild.yaml"
    registered = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    assert probe_paths <= registered, f"not routed: {sorted(probe_paths - registered)}"
