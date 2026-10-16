import contextlib
import io
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from comet.appworld import AppWorldAdapter, parse_action
from comet.errors import UnsupportedPath


class FakeWorld:
    instances = []

    def __init__(self, **kwargs):
        self.instances.append(self)
        self.kwargs = kwargs
        self.output_directory = str(self.root / kwargs["experiment_name"] / kwargs["task_id"])
        self.output_checkpoints_directory = str(Path(self.output_directory) / "checkpoints")
        Path(self.output_directory).mkdir(parents=True)
        self.task = SimpleNamespace(db_version="0.2.0", instruction="A task", supervisor={},
                                    datetime="2026-01-01", app_descriptions={},
                                    api_docs={"api_docs": {}, "supervisor": {}})
        self.done = False
        self.closed = False
        self.shell = SimpleNamespace(user_ns={"__builtins__": __builtins__})
        self.requester = SimpleNamespace(request_tracker=SimpleNamespace(
            requests=[], num_requests_reset_on=0))
        self.environment_io = []
        self.num_interactions = self.num_sub_interactions = 0

    def execute(self, code):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(code, self.shell.user_ns)
        self.num_interactions += 1
        self.environment_io.append({"input": code, "output": output.getvalue()})
        return output.getvalue()

    def task_completed(self):
        return self.done

    def save_state(self, state_id=None):
        directory = (Path(self.output_checkpoints_directory) / state_id if state_id else
                     Path(self.output_directory) / "dbs")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "state.json").write_text(json.dumps({"done": self.done}))
        return state_id

    def load_state(self, state_id):
        self.done = json.loads((Path(self.output_checkpoints_directory) /
                               state_id / "state.json").read_text())["done"]
        random.seed(self.kwargs["random_seed"])

    def _set_datetime(self):
        pass

    def save(self):
        self.save_state()

    def close(self):
        self.closed = True

    def evaluate(self):
        raise AssertionError("Evaluation must never enter online execution.")


@pytest.fixture
def adapter(tmp_path):
    FakeWorld.root = tmp_path / "appworld"
    return AppWorldAdapter(tmp_path, world_factory=FakeWorld)


def test_action_requires_one_nonempty_python_block():
    assert parse_action("thinking\n```python\nprint(1)\n```") == "print(1)"
    assert parse_action("```python\nwrong()\n```\n</think>\n```python\nright()\n```") == "right()"
    for response in ("print(1)", "```python\n\n```", "```python\na=1\n```\n```py\nb=2\n```"):
        with pytest.raises(ValueError):
            parse_action(response)


def test_fresh_attempt_and_saved_outcome_are_isolated(adapter, tmp_path):
    adapter.reset("task1", 17, tmp_path / "first")
    first = adapter.world
    first.done = True
    adapter.execute("a = [1]")
    reference = adapter.save(tmp_path / "first")
    adapter.reset("task1", 17, tmp_path / "second")
    assert first.closed
    assert not adapter.completed()
    assert "a" not in adapter.world.shell.user_ns
    assert adapter.world.kwargs["load_ground_truth"] is False
    assert reference["experiment_name"] != adapter.experiment_name
    assert json.loads((tmp_path / "first/task/dbs/state.json").read_text())["done"]
    with pytest.raises(FileExistsError):
        adapter.reset("task1", 17, tmp_path / "first")


def test_checkpoint_roundtrip_preserves_state_aliases_and_rng_without_replay(adapter, tmp_path):
    adapter.reset("task1", 3, tmp_path / "first")
    adapter.execute("value = [1]; alias = value")
    adapter.world.done = True
    adapter.world.requester.request_tracker.requests = [{"url": "test"}]
    adapter.world.requester.request_tracker.num_requests_reset_on = 1
    random.seed(27)
    adapter.checkpoint(tmp_path / "checkpoint")
    expected_random = random.random()
    adapter.execute("value.append(2)")
    adapter.reset("task1", 3, tmp_path / "second")
    adapter.restore(tmp_path / "checkpoint")
    assert adapter.completed()
    namespace = adapter.world.shell.user_ns
    assert namespace["value"] == [1]
    assert namespace["alias"] is namespace["value"]
    assert adapter.world.num_interactions == 1
    assert len(adapter.world.environment_io) == 1
    assert adapter.world.requester.request_tracker.requests == [{"url": "test"}]
    assert random.random() == expected_random
    adapter.execute("value.append(3)")
    adapter.restore(tmp_path / "checkpoint")
    assert adapter.world.shell.user_ns["value"] == [1]
    assert adapter.world.num_interactions == 1


def test_checkpoint_fails_closed_for_function_or_runtime_mutation(adapter, tmp_path):
    adapter.reset("task1", 3, tmp_path / "first")
    adapter.execute("def action(): return 2")
    with pytest.raises(UnsupportedPath, match="Cannot checkpoint"):
        adapter.checkpoint(tmp_path / "unsupported")
    assert not (tmp_path / "unsupported").exists()
    del adapter.world.shell.user_ns["action"]
    adapter.world.shell.user_ns["__builtins__"] = {}
    with pytest.raises(UnsupportedPath, match="Runtime binding"):
        adapter.checkpoint(tmp_path / "changed")


def test_checkpoint_identity_and_integrity_checked(adapter, tmp_path):
    adapter.reset("task1", 3, tmp_path / "first")
    adapter.checkpoint(tmp_path / "checkpoint")
    adapter.reset("task2", 3, tmp_path / "second")
    with pytest.raises(ValueError, match="task_id"):
        adapter.restore(tmp_path / "checkpoint")
    adapter.reset("task1", 3, tmp_path / "third")
    (tmp_path / "checkpoint/execution.pkl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        adapter.restore(tmp_path / "checkpoint")
