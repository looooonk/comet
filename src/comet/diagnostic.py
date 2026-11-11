from __future__ import annotations

from comet.artifacts import read_json, write_json
from comet.budget import Budget
from comet.clocks import wall_time
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
            "checkpoint_eligible": False,
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
            with budget.charge("checkpoint_eligibility"):
                record["source_completed"] = environment.completed()
            if record["source_completed"]:
                raise UnsupportedPath(
                    "Task completed at or before the requested checkpoint boundary"
                )
            if state["tool_calls"] < config.checkpoint_after_tool_calls:
                raise UnsupportedPath("Trajectory stopped before the requested checkpoint boundary")
            record["checkpoint_eligible"] = True
            with budget.charge("checkpoint"):
                environment.checkpoint(directory / "environment")
                engine.checkpoint(directory / "engine")
                write_json(directory / "agent.json", state)
            record.update(status="completed", failure_reason=None)
        except Exception as error:
            record.update(status="failed", failure_reason=f"{type(error).__name__}: {error}")
        finally:
            cleanup_start = budget.elapsed
            cleanup = ([engine.synchronize] if hasattr(engine, "synchronize") else []) + [
                environment.close
            ]
            for finish in cleanup:
                try:
                    finish()
                except Exception as error:
                    record.setdefault("cleanup_errors", []).append(
                        f"{type(error).__name__}: {error}"
                    )
                    if record["status"] == "completed":
                        record.update(
                            status="failed", failure_reason=f"Preparation cleanup failed: {error}"
                        )
            try:
                memory = engine.memory_stats()
            except Exception as error:
                attempt["metrics"]["memory_error"] = f"{type(error).__name__}: {error}"
                if record["status"] == "completed":
                    record.update(
                        status="failed",
                        failure_reason=f"Preparation memory measurement failed: {error}",
                    )
            else:
                for key, value in memory.items():
                    if key.startswith("peak_"):
                        value = max(value, attempt["metrics"].get(key, 0))
                    attempt["metrics"][key] = value
            budget.timings["cleanup"] = (
                budget.timings.get("cleanup", 0) + budget.elapsed - cleanup_start
            )
            if record["status"] == "completed" and not budget.remaining:
                record.update(
                    status="failed", failure_reason="Budget expired during preparation cleanup"
                )
            record.update(
                elapsed_seconds=budget.elapsed,
                timings=budget.timings,
                metrics=attempt["metrics"],
                tool_calls=state["tool_calls"],
                rebuilds=state["rebuilds"],
                prepared_at_unix=wall_time(),
            )
            write_json(record_path, record)


def charge_checkpoint_preparation(runner, cell: dict, attempt: dict, budget: Budget) -> None:
    directory = runner.output / "checkpoints" / f"{cell['task_id']}-{cell['seed']}"
    record = read_json(directory / "preparation.json")
    budget.consumed += record["elapsed_seconds"]
    budget.timings["shared_checkpoint_preparation"] = record["elapsed_seconds"]
    attempt["metrics"].update(record.get("metrics", {}))
    attempt["checkpoint_preparation"] = {
        "artifact_dir": str(directory.relative_to(runner.output)),
        "status": record["status"],
        "tool_calls": record.get("tool_calls"),
        "rebuilds": record.get("rebuilds"),
    }
    if record["status"] != "completed":
        raise UnsupportedPath(f"Common checkpoint unavailable: {record['failure_reason']}")
    budget.check()


def restore_checkpoint(runner, cell: dict, environment, engine, budget: Budget) -> dict:
    directory = runner.output / "checkpoints" / f"{cell['task_id']}-{cell['seed']}"
    with budget.charge("checkpoint_restore"):
        environment.restore(directory / "environment")
        engine.restore(directory / "engine", branch=True)
        state = read_json(directory / "agent.json")
    return state
