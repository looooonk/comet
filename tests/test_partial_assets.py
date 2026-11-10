from comet.artifacts import read_json, write_json
from scripts.stage_partial_assets import prepare, restore


def test_scoring_assets_isolate_databases_and_restore_snapshot_references(tmp_path):
    source, local, report = (tmp_path / name for name in ("source", "local", "report"))
    (source / "data/base_dbs").mkdir(parents=True)
    database = source / "data/base_dbs/example.db"
    database.write_bytes(b"original database")
    (source / "data/tasks").mkdir()
    reference = report / "cells/part-00/task/attempt-000/environment/reference.json"
    write_json(reference, {"appworld_root": str(source), "task_id": "task"})
    original = reference.read_bytes()
    prepare(source, local, report)
    assert read_json(reference)["appworld_root"] == str(local)
    assert (local / "data/tasks").resolve() == source / "data/tasks"
    (local / "data/base_dbs/example.db").write_bytes(b"isolated change")
    assert database.read_bytes() == b"original database"
    restore(report)
    assert reference.read_bytes() == original
