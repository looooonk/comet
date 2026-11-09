"""Archive a managed runtime once, then unpack it on a job's local disk."""

import argparse
import json
import shutil
import tarfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("action", choices=("pack", "stage"))
parser.add_argument("source", type=Path)
parser.add_argument("archive", type=Path)
parser.add_argument("destination", nargs="?", type=Path)
args = parser.parse_args()
source = args.source.resolve()
identity = json.loads((source / ".comet-runtime.json").read_text())
if not identity.get("ready"):
    raise ValueError("Source runtime setup is incomplete")
record_path = args.archive.with_suffix(".json")
started = time.monotonic()
if args.action == "pack":
    if args.archive.exists() or record_path.exists():
        raise FileExistsError("Use a new archive for each runtime version")
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.archive.with_suffix(".tmp")
    with tarfile.open(temporary, "w", copybufsize=8 * 2**20) as archive:
        archive.add(source, arcname=".")
    temporary.replace(args.archive)
    record = {"source": str(source), "identity": identity,
              "bytes": args.archive.stat().st_size, "seconds": time.monotonic() - started}
    record_path.write_text(json.dumps(record, indent=2) + "\n")
else:
    record = json.loads(record_path.read_text())
    if record["source"] != str(source) or record["identity"] != identity:
        raise ValueError("Archive does not match the selected managed runtime")
    if args.destination is None:
        raise ValueError("Stage requires a job-local destination")
    destination = args.destination.resolve()
    if destination == source:
        raise ValueError("Do not stage over the managed source runtime")
    marker = destination / ".comet-local-runtime.json"
    if marker.exists():
        if json.loads(marker.read_text())["identity"] != identity:
            raise ValueError("Staged runtime differs; use a fresh destination")
    else:
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            raise ValueError("Stage requires an empty destination")
        if shutil.disk_usage(destination).free < record["bytes"] + 2**30:
            raise OSError("Insufficient job-local storage for runtime staging")
        # This archive is produced above from our own managed environment.
        with tarfile.open(args.archive, copybufsize=8 * 2**20) as archive:
            archive.extractall(destination, filter="fully_trusted")
        for path in (destination / "bin").iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            with path.open("rb") as stream:
                prefix = stream.read(512)
            if prefix.startswith(b"#!") and str(source).encode() in prefix.split(b"\n", 1)[0]:
                content = path.read_bytes()
                first, rest = content.split(b"\n", 1)
                path.write_bytes(first.replace(str(source).encode(), str(destination).encode()) + b"\n" + rest)
        marker.write_text(json.dumps(record, indent=2) + "\n")
    record = {"identity": identity, "destination": str(destination),
              "seconds": time.monotonic() - started}
print(json.dumps(record))
