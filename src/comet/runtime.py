"""Ownership and lock checks for explicitly managed runtime environments."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def identity(repo: Path, profile: str) -> dict:
    files = (
        ["uv.lock"]
        if profile == "cpu"
        else [
            f"infra/requirements/{profile}.lock",
            "dependencies.lock.json",
        ]
    )
    if profile in {"gpu", "hybrid"}:
        files.append("patches/minisgl-comet.patch")
    files.append("pyproject.toml")
    return {
        "schema_version": 1,
        "checkout": str(repo.resolve()),
        "profile": profile,
        "locks": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in files},
    }


def manage(action: str, repo: Path, environment: Path, profile: str) -> None:
    repo, environment = repo.resolve(), environment.resolve()
    marker = environment / ".comet-runtime.json"
    expected = identity(repo, profile)
    existing = json.loads(marker.read_text()) if marker.exists() else None
    if existing is not None:
        if any(existing.get(key) != expected[key] for key in ("checkout", "profile")):
            raise ValueError(
                "Runtime belongs to another checkout or profile; choose a new environment"
            )
    elif action != "prepare" or (environment.exists() and any(environment.iterdir())):
        raise ValueError(
            "Unmanaged runtime; choose a new empty environment and run setup_runtime.sh"
        )
    if action == "prepare":
        environment.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({**expected, "ready": False}, indent=2) + "\n")
        return
    if any(existing.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Runtime locks changed; rerun setup_runtime.sh before executing checks or runs"
        )
    if Path(sys.prefix).resolve() != environment:
        raise ValueError("Use the selected runtime's Python interpreter")
    import comet

    if Path(comet.__file__).resolve().parent != repo / "src/comet":
        raise ValueError("Installed COMET resolves to a different checkout")
    if action == "record":
        marker.write_text(json.dumps({**expected, "ready": True}, indent=2) + "\n")
    elif not existing.get("ready"):
        raise ValueError("Runtime setup is incomplete; rerun setup_runtime.sh")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "record", "verify"))
    parser.add_argument("repo", type=Path)
    parser.add_argument("environment", type=Path)
    parser.add_argument("profile", choices=("cpu", "appworld", "gpu", "hybrid"))
    args = parser.parse_args()
    manage(args.action, args.repo, args.environment, args.profile)


if __name__ == "__main__":
    main()
