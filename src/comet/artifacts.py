from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path

from comet.clocks import wall_time


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


@contextmanager
def run_lock(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    with (path / ".lock").open("w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another process owns run {path}") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def provenance() -> dict:
    root = Path(__file__).resolve().parents[2]

    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    source_hashes = {
        str(file.relative_to(root)): hashlib.sha256(file.read_bytes()).hexdigest()
        for pattern in ("src/comet/**/*.py", "patches/*.patch", "infra/requirements/*.lock")
        for file in sorted(root.glob(pattern))
    }
    return {
        "recorded_at_unix": wall_time(),
        "code_commit": git("rev-parse", "HEAD"),
        "local_changes": git("diff", "HEAD", "--binary"),
        "untracked_paths": git("ls-files", "--others", "--exclude-standard"),
        "source_hashes": source_hashes,
        "installed_packages": {
            d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        },
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
    }
