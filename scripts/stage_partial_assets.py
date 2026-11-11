"""Isolate offline scoring databases from live AppWorld workers."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from comet.artifacts import write_json


def copy_database(source, destination):
    # GPFS sendfile can stall while live SQLite readers hold the source open.
    with Path(source).open("rb") as reader, Path(destination).open("wb") as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
    shutil.copystat(source, destination)
    return destination


def prepare(source: Path, destination: Path, report: Path, base_databases: Path | None = None):
    source, destination = source.resolve(), destination.resolve()
    if source == destination or destination.is_relative_to(source):
        raise ValueError("Scoring assets need a separate job-local root.")
    base_databases = base_databases or source / "data/base_dbs"
    expected = {path.name: path.stat().st_size for path in (source / "data/base_dbs").iterdir()}
    actual = {path.name: path.stat().st_size for path in base_databases.iterdir()}
    if expected != actual:
        raise ValueError("Replacement base databases differ from the pinned installation layout.")
    (destination / "data").mkdir(parents=True)
    for path in (source / "data").iterdir():
        target = destination / "data" / path.name
        if path.name == "base_dbs":
            shutil.copytree(base_databases, target, copy_function=copy_database)
        else:
            target.symlink_to(path, target_is_directory=path.is_dir())
    for path in report.glob("cells/*/*/attempt-*/environment/reference.json"):
        original = path.with_name("reference.source.json")
        if not original.exists():
            shutil.copyfile(path, original)
        reference = json.loads(original.read_text())
        if Path(reference["appworld_root"]).resolve() != source:
            raise ValueError("Snapshot references a different benchmark installation.")
        reference["appworld_root"] = str(destination)
        write_json(path, reference)
    write_json(report / "scoring-assets.json", {
        "policy": "Job-local base databases and scoring scratch; immutable task assets shared.",
        "source": str(source), "job_local_root": str(destination),
        "original_references_preserved": True,
        "base_database_source": str(base_databases),
        "base_database_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (destination / "data/base_dbs").iterdir()
        },
    })


def restore(report: Path):
    for path in report.glob("cells/*/*/attempt-*/environment/reference.source.json"):
        shutil.copyfile(path, path.with_name("reference.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "restore"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--base-databases", type=Path,
                        help="An independent copy from the same pinned AppWorld data release.")
    args = parser.parse_args()
    if args.command == "prepare":
        if args.source is None or args.destination is None:
            parser.error("prepare requires --source and --destination")
        prepare(args.source, args.destination, args.report, args.base_databases)
    else:
        restore(args.report)
