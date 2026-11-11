import json
import sys

import pytest

import comet
from comet.runtime import manage


def test_runtime_ownership_and_incomplete_setup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text("first lock")
    (repo / "pyproject.toml").write_text("project metadata")
    environment = tmp_path / "runtime"
    manage("prepare", repo, environment, "cpu")
    monkeypatch.setattr(sys, "prefix", str(environment))
    monkeypatch.setattr(comet, "__file__", str(repo / "src/comet/__init__.py"))
    with pytest.raises(ValueError, match="incomplete"):
        manage("verify", repo, environment, "cpu")
    manage("record", repo, environment, "cpu")
    manage("verify", repo, environment, "cpu")
    (repo / "uv.lock").write_text("changed lock")
    with pytest.raises(ValueError, match="locks changed"):
        manage("verify", repo, environment, "cpu")
    manage("prepare", repo, environment, "cpu")
    manage("record", repo, environment, "cpu")
    monkeypatch.setattr(comet, "__file__", str(tmp_path / "wrong/src/comet/__init__.py"))
    with pytest.raises(ValueError, match="different checkout"):
        manage("verify", repo, environment, "cpu")
    marker = environment / ".comet-runtime.json"
    record = json.loads(marker.read_text())
    record["checkout"] = str(tmp_path / "other")
    marker.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="another checkout"):
        manage("prepare", repo, environment, "cpu")


def test_unmanaged_runtime_is_untouched(tmp_path):
    repo, environment = tmp_path / "repo", tmp_path / "runtime"
    repo.mkdir()
    environment.mkdir()
    (repo / "uv.lock").write_text("lock")
    (repo / "pyproject.toml").write_text("project metadata")
    marker = environment / "pyvenv.cfg"
    marker.write_text("existing environment")
    with pytest.raises(ValueError, match="Unmanaged"):
        manage("prepare", repo, environment, "cpu")
    assert marker.read_text() == "existing environment"
    assert not (environment / ".comet-runtime.json").exists()
