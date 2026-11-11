"""Online AppWorld adapter. Scoring lives in comet.evaluation."""

from __future__ import annotations

import ast
import copy
import datetime
import hashlib
import importlib
import importlib.metadata
import json
import pickle
import random
import re
import shutil
import sys
import types
import uuid
from collections import Counter, defaultdict, deque
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from comet.errors import UnsupportedPath

APPWORLD_REVISION = "42b5bcf3cd334fee33f0c37c02070a9f5807add5"
APPWORLD_DATA_VERSION = "0.2.0"
APPWORLD_DATABASE_PATH_VERSION = "structured-memory-v1"
_DATABASE_PATHS_CONFIGURED = False
_BOOKKEEPING = {"In", "Out", "_ih", "_oh", "_dh", "_", "__", "___"}
_ATOMS = (
    type(None),
    bool,
    int,
    float,
    complex,
    str,
    bytes,
    bytearray,
    range,
    datetime.date,
    datetime.time,
    datetime.timedelta,
    Decimal,
    Fraction,
)


def verify_appworld_revision() -> None:
    distribution = importlib.metadata.distribution("appworld")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    actual = direct_url.get("vcs_info", {}).get("commit_id")
    if actual != APPWORLD_REVISION:
        raise UnsupportedPath(
            f"Install AppWorld from commit {APPWORLD_REVISION}; found {actual!r}."
        )


def configure_appworld_database_paths() -> None:
    global _DATABASE_PATHS_CONFIGURED
    if _DATABASE_PATHS_CONFIGURED:
        return
    verify_appworld_revision()
    from appworld.apps.lib.models.db import Database

    original = Database._get_engine_to_details

    def engine_details(engine: Any) -> tuple[Any, ...]:
        url, path, home, storage, connection = original(engine)
        if engine.url.query.get("mode") == "memory":
            database = engine.url.database
            if not database or not database.startswith("file:") or database.count("/") != 1:
                raise UnsupportedPath(f"Unsupported AppWorld memory database: {database!r}")
            # SQLAlchemy's rendered URL escapes file:, splitting mutation and export counters.
            home = ":memory:" + database.removeprefix("file:").rsplit("/", 1)[0]
        return url, path, home, storage, connection

    Database._get_engine_to_details = staticmethod(engine_details)
    _DATABASE_PATHS_CONFIGURED = True


def validate_tasks(split: str, task_ids: list[str]) -> None:
    verify_appworld_revision()
    from appworld import load_task_ids

    if len(task_ids) != len(set(task_ids)) or not task_ids:
        raise ValueError("Task subset must be nonempty and contain no duplicates.")
    unknown = set(task_ids) - set(load_task_ids(split))
    if unknown:
        raise ValueError(f"Tasks do not belong to {split}: {sorted(unknown)}")


def parse_action(response: str, *, require_executable: bool = False) -> str:
    """One model turn is one Python execution, even if it calls several APIs."""
    if "</think>" in response:
        response = response.rsplit("</think>", 1)[1]
    elif "<think>" in response:
        raise ValueError("Finish reasoning before returning the action block.")
    blocks = re.findall(
        r"^```(?:python|py)[ \t]*\n(.*?)^```[ \t]*$", response, flags=re.MULTILINE | re.DOTALL
    )
    if len(blocks) != 1 or not blocks[0].strip():
        raise ValueError("Return exactly one nonempty fenced Python block.")
    action = blocks[0].strip()
    if require_executable:
        try:
            tree = ast.parse(action)
        except SyntaxError:
            return action
        if not tree.body:
            raise ValueError(
                "A comment-only block cannot advance the task; return executable Python"
            )
    return action


def _checkpoint_value(value: Any, seen: set[int]) -> None:
    if id(value) in seen:
        return
    seen.add(id(value))
    if type(value) in _ATOMS or isinstance(value, (datetime.datetime, re.Pattern)):
        return
    if type(value) in (list, tuple, set, frozenset, deque):
        for item in value:
            _checkpoint_value(item, seen)
        return
    if type(value) in (dict, Counter, defaultdict):
        if isinstance(value, defaultdict) and value.default_factory not in (
            None,
            int,
            float,
            str,
            list,
            dict,
            set,
            tuple,
            bool,
        ):
            raise UnsupportedPath("Checkpoint requires a builtin defaultdict factory.")
        for key, item in value.items():
            _checkpoint_value(key, seen)
            _checkpoint_value(item, seen)
        return
    raise UnsupportedPath(
        f"Cannot checkpoint execution value {type(value).__module__}.{type(value).__name__}; "
        "functions, API handles, iterators and resources need an explicit state implementation."
    )


class AppWorldAdapter:
    def __init__(self, root: str | Path, *, world_factory: Callable[..., Any] | None = None):
        self.root = Path(root).resolve()
        self._factory = world_factory
        self.world: Any = None
        self.artifact_dir: Path | None = None
        self._baseline: dict[str, Any] = {}

    def reset(self, task_id: str, seed: int, artifact_dir: str | Path) -> None:
        self.close()
        self.artifact_dir = Path(artifact_dir).resolve()
        if (self.artifact_dir / "reference.json").exists():
            raise FileExistsError(f"Completed environment already exists: {self.artifact_dir}")
        if self._factory is None:
            configure_appworld_database_paths()
            from appworld import AppWorld, update_root

            update_root(str(self.root))
            factory = AppWorld
        else:
            factory = self._factory
        self.task_id, self.seed = task_id, seed
        self.experiment_name = f"comet/{uuid.uuid4().hex}"
        try:
            self.world = factory(
                task_id=task_id,
                experiment_name=self.experiment_name,
                random_seed=seed,
                load_ground_truth=False,
                remote_apis_url=None,
                remote_environment_url=None,
                remote_mcp_url=None,
                remote_docker=False,
                timeout_seconds=None,
                max_interactions=sys.maxsize,
                max_api_calls_per_interaction=sys.maxsize,
            )
        except BaseException:
            if hasattr(factory, "close_all"):
                factory.close_all()
            raise
        if self.world.task.db_version != APPWORLD_DATA_VERSION:
            self.close()
            raise UnsupportedPath(f"Expected AppWorld data {APPWORLD_DATA_VERSION}.")
        self._baseline = dict(self.world.shell.user_ns)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        (self.artifact_dir / "live.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "seed": seed,
                    "appworld_root": str(self.root),
                    "experiment_name": self.experiment_name,
                    "output_directory": str(self.world.output_directory),
                },
                indent=2,
            )
            + "\n"
        )

    def _active(self) -> Any:
        if self.world is None:
            raise RuntimeError("Reset an AppWorld attempt before using it.")
        return self.world

    def initial_prompt(self) -> str:
        task = self._active().task
        context = {
            "instruction": task.instruction,
            "supervisor": dict(task.supervisor),
            "datetime": str(task.datetime),
            "apps": dict(task.app_descriptions),
            "api_docs": {name: task.api_docs[name] for name in ("api_docs", "supervisor")},
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    def execute(self, code: str, *, timeout_seconds: float | None = None) -> str:
        """The runner's outer wall timer enforces timeout_seconds, including saving."""
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise TimeoutError("No task budget remains for tool execution.")
        world = self._active()
        try:
            return world.execute(code)
        finally:
            # A deadline can interrupt upstream before its process-wide patches are undone.
            if hasattr(world, "safety_guard"):
                world.safety_guard.disable()

    def completed(self) -> bool:
        return bool(self._active().task_completed())

    def save(self, path: str | Path) -> dict[str, Any]:
        world = self._active()
        world.save()
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(world.output_directory, path / "task", dirs_exist_ok=True)
        reference = {
            "schema_version": 1,
            "task_id": self.task_id,
            "seed": self.seed,
            "appworld_root": str(self.root),
            "experiment_name": self.experiment_name,
            "appworld_revision": APPWORLD_REVISION,
            "data_version": APPWORLD_DATA_VERSION,
            "task_directory": "task",
            "database_path_version": APPWORLD_DATABASE_PATH_VERSION,
        }
        (path / "reference.json").write_text(json.dumps(reference, indent=2) + "\n")
        return reference

    def checkpoint(self, path: str | Path) -> None:
        world = self._active()
        namespace: dict[str, Any] = {}
        modules: dict[str, str] = {}
        removed: list[str] = []
        for key, value in self._baseline.items():
            if key in _BOOKKEEPING or re.fullmatch(r"_i\d*", key):
                continue
            if key not in world.shell.user_ns:
                removed.append(key)
            elif world.shell.user_ns[key] is not value:
                raise UnsupportedPath(f"Runtime binding {key!r} was changed before checkpoint.")
        for key, value in world.shell.user_ns.items():
            if key in self._baseline or key in _BOOKKEEPING or re.fullmatch(r"_i\d*", key):
                continue
            if isinstance(value, types.ModuleType):
                modules[key] = value.__name__
            else:
                _checkpoint_value(value, set())
                namespace[key] = value
        tracker = world.requester.request_tracker
        state = {
            "namespace": namespace,
            "modules": modules,
            "removed": removed,
            "random_state": random.getstate(),
            "numpy_state": sys.modules["numpy"].random.get_state()
            if "numpy" in sys.modules
            else None,
            "environment_io": world.environment_io,
            "num_interactions": world.num_interactions,
            "num_sub_interactions": world.num_sub_interactions,
            "requests": tracker.requests,
            "num_requests_reset_on": tracker.num_requests_reset_on,
        }
        payload = pickle.dumps(state, protocol=5)
        path = Path(path)
        path.mkdir(parents=True, exist_ok=False)
        checkpoint_id = uuid.uuid4().hex
        world.save_state(state_id=checkpoint_id)
        shutil.copytree(Path(world.output_checkpoints_directory) / checkpoint_id, path / "dbs")
        (path / "execution.pkl").write_bytes(payload)
        metadata = {
            "schema_version": 1,
            "task_id": self.task_id,
            "seed": self.seed,
            "appworld_revision": APPWORLD_REVISION,
            "data_version": APPWORLD_DATA_VERSION,
            "database_path_version": APPWORLD_DATABASE_PATH_VERSION,
            "execution_sha256": hashlib.sha256(payload).hexdigest(),
        }
        (path / "checkpoint.json").write_text(json.dumps(metadata, indent=2) + "\n")

    def restore(self, path: str | Path) -> None:
        world = self._active()
        path = Path(path)
        metadata = json.loads((path / "checkpoint.json").read_text())
        for key, value in {
            "schema_version": 1,
            "task_id": self.task_id,
            "seed": self.seed,
            "appworld_revision": APPWORLD_REVISION,
            "data_version": APPWORLD_DATA_VERSION,
            "database_path_version": APPWORLD_DATABASE_PATH_VERSION,
        }.items():
            if metadata.get(key) != value:
                raise ValueError(f"Incompatible AppWorld checkpoint: {key}.")
        payload = (path / "execution.pkl").read_bytes()
        if hashlib.sha256(payload).hexdigest() != metadata["execution_sha256"]:
            raise ValueError("AppWorld execution checkpoint checksum mismatch.")
        # Checkpoints are local trusted run artifacts; never load foreign pickle files.
        state = pickle.loads(payload)
        checkpoint_id = uuid.uuid4().hex
        shutil.copytree(path / "dbs", Path(world.output_checkpoints_directory) / checkpoint_id)
        world.load_state(state_id=checkpoint_id)
        # load_state clears AppWorld's time freezer and reruns the API preamble.
        world._set_datetime()
        for key in tuple(world.shell.user_ns):
            if key not in self._baseline:
                del world.shell.user_ns[key]
        self._baseline = dict(world.shell.user_ns)
        world.shell.user_ns.update(state["namespace"])
        world.shell.user_ns.update(
            {key: importlib.import_module(name) for key, name in state["modules"].items()}
        )
        for key in state["removed"]:
            world.shell.user_ns.pop(key, None)
        world.environment_io = copy.deepcopy(state["environment_io"])
        world.num_interactions = state["num_interactions"]
        world.num_sub_interactions = state["num_sub_interactions"]
        world.requester.request_tracker.requests = copy.deepcopy(state["requests"])
        world.requester.request_tracker.num_requests_reset_on = state["num_requests_reset_on"]
        random.setstate(state["random_state"])
        if state["numpy_state"] is not None:
            import numpy

            numpy.random.set_state(state["numpy_state"])
        world.save()

    def close(self) -> None:
        if self.world is not None:
            self.world.close()
            self.world = None
