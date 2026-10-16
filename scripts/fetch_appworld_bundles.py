"""Materialize pinned Git LFS bundles omitted by uv's VCS installation."""

import hashlib
import importlib.metadata
import json
import urllib.request
from pathlib import Path


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    pin = json.loads((repo / "dependencies.lock.json").read_text())["repositories"]["appworld"]
    revision = pin["revision"]
    distribution = importlib.metadata.distribution("appworld")
    base = Path(distribution.locate_file("appworld/.source"))
    for name in ("apps.bundle", "tests.bundle"):
        path = base / name
        content = path.read_bytes()
        if not content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            if hashlib.sha256(content).hexdigest() != pin["bundle_sha256"][name]:
                raise RuntimeError(f"Installed AppWorld bundle differs from the lock: {name}")
            continue
        pointer = dict(line.split(" ", 1) for line in content.decode().splitlines())
        url = (
            "https://media.githubusercontent.com/media/StonyBrookNLP/appworld/"
            f"{revision}/src/appworld/.source/{name}"
        )
        with urllib.request.urlopen(url, timeout=120) as response:
            bundle = response.read()
        expected = pointer["oid"].removeprefix("sha256:")
        if expected != pin["bundle_sha256"][name]:
            raise RuntimeError(f"AppWorld LFS pointer differs from the lock: {name}")
        if len(bundle) != int(pointer["size"]) or hashlib.sha256(bundle).hexdigest() != expected:
            raise RuntimeError(f"Pinned AppWorld bundle failed integrity check: {name}")
        temporary = path.with_suffix(".download")
        temporary.write_bytes(bundle)
        temporary.replace(path)
        print(f"Verified AppWorld {name}: sha256:{expected}")


if __name__ == "__main__":
    main()
