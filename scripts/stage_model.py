"""Copy one pinned model snapshot to job-local storage before model loading."""

import json
import shutil
import sys
import time
from pathlib import Path

source, destination = (Path(value).resolve() for value in sys.argv[1:])
if source == destination or destination.name != source.name:
    raise ValueError("Use a separate destination ending in the pinned snapshot revision")
files = [path for path in source.iterdir() if path.is_file()]
sizes = {path.name: path.stat().st_size for path in files}
marker = destination / ".comet-staged.json"
if marker.exists():
    record = json.loads(marker.read_text())
    if record["files"] != sizes or any((destination / name).stat().st_size != size
                                       for name, size in sizes.items()):
        raise ValueError("Existing staged snapshot differs; use a fresh job directory")
else:
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("Staging requires an empty destination")
    if shutil.disk_usage(destination).free < sum(sizes.values()) + 2**30:
        raise OSError("Insufficient job-local storage for model staging")
    started = time.monotonic()
    for path in files:
        shutil.copyfile(path, destination / path.name)
    record = {"revision": source.name, "files": sizes,
              "bytes": sum(sizes.values()), "seconds": time.monotonic() - started}
    marker.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
