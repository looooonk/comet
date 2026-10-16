from __future__ import annotations

import time

from comet.artifacts import read_json, write_json
from comet.budget import Budget
from comet.config import Condition, attempt_seed
from comet.errors import UnsupportedPath


def prepare_checkpoints(runner, manifest: dict, engine) -> None:
    config = runner.config
    control = Condition("diagnostic_source", "full", 1.0, "never", 1)
    missing = [
        (task, seed)
        for task in config.task_ids
        for seed in config.seeds
        if not (runner.output / "checkpoints" / f"{task}-{seed}" / "preparation.json").exists()
    ]
    if not missing:
        return
    engine.set_policy("full", 1.0)
    for task, seed in missing:
        directory = runner.output / "checkpoints" / f"{task}-{seed}"
        record_path = directory / "preparation.json"
        record = {
            "status": "running",
            "task_id": task,
            "seed": seed,
            "elapsed_seconds": config.budget_seconds,
            "failure_reason": "Preparation interrupted; reserved budget is consumed",
        }
        write_json(record_path, record)
        budget = Budget(config.budget_seconds, clock=runner.clock)
        environment = runner.environment_factory()
        state = {"tool_calls": 0, "rebuilds": 0, "turns": [], "pending_tokens": []}
        attempt = {"metrics": {}, "recovery_events": []}
        try:
            with budget.charge("reset"):
                actual_seed = attempt_seed(seed, 0)
                engine.start(actual_seed)
                environment.reset(task, actual_seed, directory / "source-environment")
                state["pending_tokens"] = runner._initial_tokens(engine, environment)
            runner._trajectory(
                {"task_id": task},
                attempt,
                directory,
                control,
                engine,
                environment,
                budget,
                state,
                stop_after_tools=config.checkpoint_after_tool_calls,
            )
            if state["tool_calls"] < config.checkpoint_after_tool_calls:
                raise UnsupportedPath("Task completed before the requested checkpoint boundary")
            with budget.charge("checkpoint"):
                environment.checkpoint(directory / "environment")
                engine.checkpoint(directory / "engine")
                write_json(directory / "agent.json", state)
            record.update(status="completed", failure_reason=None)
        except Exception as error:
            record.update(status="failed", failure_reason=f"{type(error).__name__}: {error}")
        finally:
            environment.close()
            record.update(
                elapsed_seconds=budget.elapsed,
                timings=budget.timings,
                metrics=attempt["metrics"],
                prepared_at_unix=time.time(),
            )
            write_json(record_path, record)


def restore_checkpoint(runner, cell: dict, environment, engine, budget: Budget) -> dict:
    directory = runner.output / "checkpoints" / f"{cell['task_id']}-{cell['seed']}"
    record = read_json(directory / "preparation.json")
    budget.consumed += record["elapsed_seconds"]
    budget.timings["shared_checkpoint_preparation"] = record["elapsed_seconds"]
    if record["status"] != "completed":
        raise UnsupportedPath(f"Common checkpoint unavailable: {record['failure_reason']}")
    budget.check()
    with budget.charge("checkpoint_restore"):
        environment.restore(directory / "environment")
        engine.restore(directory / "engine", branch=True)
        state = read_json(directory / "agent.json")
    return state
