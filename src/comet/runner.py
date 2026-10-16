from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path
from typing import Callable

from comet.artifacts import provenance, read_json, run_lock, write_json
from comet.budget import Budget
from comet.clocks import monotonic, wall_time
from comet.config import Condition, Experiment, attempt_seed
from comet.errors import BudgetExpired, MemoryCapExceeded, UnsupportedPath
from comet.policies import decide


def cell_id(task_id: str, condition: Condition, seed: int) -> str:
    return f"{task_id}-{condition.id}-{seed}"


def _plain(value):
    return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value


def _runtime_contract(metadata: dict) -> dict:
    return {k: v for k, v in metadata.items() if k not in {"model_path", "memory", "warmup"}}


class Runner:
    def __init__(
        self,
        config: Experiment,
        output: Path,
        engine_factory: Callable,
        environment_factory: Callable,
        *,
        clock: Callable = monotonic,
        integration_smoke: bool = False,
    ):
        self.config, self.output = config, output.resolve()
        self.engine_factory, self.environment_factory = engine_factory, environment_factory
        self.clock, self.integration_smoke = clock, integration_smoke
        if integration_smoke and config.stage == "final":
            raise ValueError("Final evaluation requires the specified A100 hardware")

    def run(self, *, resume: bool = False) -> dict:
        with run_lock(self.output):
            manifest = self._manifest(resume)
            if manifest["status"] == "completed":
                return manifest
            initial = (
                Condition("diagnostic_source", "full", 1.0, "never", 1)
                if self.config.stage == "diagnostic"
                else self.config.conditions[0]
            )
            try:
                engine = self.engine_factory(initial)
            except Exception as error:
                if (
                    not isinstance(error, MemoryError)
                    and type(error).__name__ != "OutOfMemoryError"
                ):
                    raise
                for reference in manifest["cells"]:
                    if self._done(reference):
                        continue
                    condition = next(
                        c for c in self.config.conditions if c.id == reference["condition_id"]
                    )
                    path = self.output / reference["path"]
                    cell = (
                        read_json(path)
                        if path.exists()
                        else self._new_cell(manifest, reference, condition)
                    )
                    if cell.get("inflight"):
                        cell["elapsed_seconds"] = self.config.budget_seconds
                        for attempt in cell["attempts"]:
                            if attempt["status"] == "running":
                                attempt.update(
                                    status="interrupted", failure_reason="process_interrupted"
                                )
                        cell["inflight"] = False
                    cell.update(completed=True, infeasible=True, failure_reason=str(error))
                    write_json(path, cell)
                manifest.update(status="completed", finished_at_unix=wall_time())
                write_json(self.output / "manifest.json", manifest)
                return manifest
            try:
                if hasattr(engine, "warmup"):
                    engine.warmup()
                self.engine_metadata = engine.provenance() if hasattr(engine, "provenance") else {}
                previous = manifest.get("engine")
                if previous is not None and _runtime_contract(previous) != _runtime_contract(
                    self.engine_metadata
                ):
                    raise ValueError(
                        "Resume runtime dependencies or hardware differ from the original run"
                    )
                manifest.setdefault("engine", self.engine_metadata)
                manifest.setdefault("launches", []).append(
                    {"at_unix": wall_time(), "engine": self.engine_metadata}
                )
                write_json(self.output / "manifest.json", manifest)
                if self.config.stage == "diagnostic":
                    from comet.diagnostic import prepare_checkpoints

                    prepare_checkpoints(self, manifest, engine)
                for condition in self.config.conditions:
                    pending = [
                        c
                        for c in manifest["cells"]
                        if c["condition_id"] == condition.id and not self._done(c)
                    ]
                    if not pending:
                        continue
                    engine.set_policy(condition.method, condition.retention)
                    for reference in pending:
                        self._run_cell(manifest, reference, condition, engine)
            finally:
                engine.close()
            manifest["status"] = "completed"
            manifest["finished_at_unix"] = wall_time()
            write_json(self.output / "manifest.json", manifest)
            return manifest

    def _done(self, reference: dict) -> bool:
        path = self.output / reference["path"]
        return path.exists() and read_json(path).get("completed", False)

    def _manifest(self, resume: bool) -> dict:
        path = self.output / "manifest.json"
        current = provenance()
        if path.exists():
            if not resume:
                raise FileExistsError(
                    "Run already exists; use --resume with its original configuration"
                )
            manifest = read_json(path)
            if manifest["config_digest"] != self.config.digest:
                raise ValueError("Resume configuration differs from the saved run")
            if manifest["integration_smoke"] != self.integration_smoke:
                raise ValueError("Resume hardware mode differs from the saved run")
            for key in ("code_commit", "local_changes", "source_hashes", "installed_packages"):
                if manifest["provenance"][key] != current[key]:
                    raise ValueError(f"Resume requires the original code ({key} differs)")
            return manifest
        if resume:
            raise FileNotFoundError("Cannot resume without a run manifest")
        manifest = {
            "schema_version": 1,
            "run_id": str(uuid.uuid4()),
            "stage": self.config.stage,
            "status": "running",
            "config_digest": self.config.digest,
            "config": self.config.to_dict(),
            "provenance": current,
            "integration_smoke": self.integration_smoke,
            "started_at_unix": wall_time(),
            "cells": [
                {
                    "id": cell_id(task, condition, seed),
                    "path": f"cells/{cell_id(task, condition, seed)}/cell.json",
                    "task_id": task,
                    "condition_id": condition.id,
                    "seed": seed,
                }
                for condition in self.config.conditions
                for task in self.config.task_ids
                for seed in self.config.seeds
            ],
        }
        lock = Path(__file__).resolve().parents[2] / "dependencies.lock.json"
        if lock.exists():
            manifest["dependencies"] = read_json(lock)
        write_json(path, manifest)
        return manifest

    def _run_cell(self, manifest: dict, reference: dict, condition: Condition, engine) -> None:
        path = self.output / reference["path"]
        if path.exists():
            cell = read_json(path)
            if cell["completed"]:
                return
            # A crashed operation has no trustworthy end time; never refund its reserved budget.
            if cell.get("inflight"):
                if cell["attempts"] and cell["attempts"][-1]["status"] == "running":
                    cell["attempts"][-1].update(
                        status="interrupted", failure_reason="process_interrupted"
                    )
                cell.update(
                    elapsed_seconds=self.config.budget_seconds, completed=True, inflight=False
                )
                write_json(path, cell)
                return
        else:
            cell = self._new_cell(manifest, reference, condition)
        budget = Budget(self.config.budget_seconds, cell["elapsed_seconds"], clock=self.clock)
        for index in range(len(cell["attempts"]), condition.max_attempts):
            if not budget.remaining:
                break
            attempt_dir = path.parent / f"attempt-{index:03d}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            attempt = {
                "attempt_index": index,
                "seed": attempt_seed(cell["seed"], index),
                "status": "running",
                "failure_reason": None,
                "artifact_dir": str(attempt_dir.relative_to(self.output)),
                "elapsed_seconds": 0.0,
                "timings": {},
                "metrics": {},
                "recovery_events": [],
            }
            cell["attempts"].append(attempt)
            cell["inflight"] = True
            write_json(path, cell)
            self._attempt(cell, attempt, attempt_dir, condition, engine, budget)
            if attempt["status"] == "completed" and not budget.remaining:
                attempt.update(
                    status="timeout",
                    failure_reason="Artifact finalization exceeded the shared budget",
                )
                write_json(attempt_dir / "attempt.json", attempt)
            attempt["budget_elapsed_seconds"] = budget.elapsed
            cell.update(elapsed_seconds=budget.elapsed, inflight=False)
            self._persist_cell(path, cell, budget)
        cell.update(completed=True, elapsed_seconds=budget.elapsed)
        self._persist_cell(path, cell, budget)

    def _persist_cell(self, path: Path, cell: dict, budget: Budget) -> None:
        write_json(path, cell)
        if (
            cell["attempts"]
            and cell["attempts"][-1]["status"] == "completed"
            and not budget.remaining
        ):
            attempt = cell["attempts"][-1]
            attempt.update(
                status="timeout",
                failure_reason="Run journal finalization exceeded the shared budget",
                budget_elapsed_seconds=budget.elapsed,
            )
            write_json(self.output / attempt["artifact_dir"] / "attempt.json", attempt)
            cell["elapsed_seconds"] = budget.elapsed
            write_json(path, cell)

    def _new_cell(self, manifest: dict, reference: dict, condition: Condition) -> dict:
        return {
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "stage": self.config.stage,
            "config_digest": self.config.digest,
            "task_id": reference["task_id"],
            "split": self.config.split,
            "condition": dataclasses.asdict(condition),
            "seed": reference["seed"],
            "budget_seconds": self.config.budget_seconds,
            "elapsed_seconds": 0.0,
            "completed": False,
            "inflight": False,
            "attempts": [],
        }

    def _initial_tokens(self, engine, environment) -> list[int]:
        return engine.tokenizer.apply_chat_template(
            [
                {"role": "system", "content": self.config.prompt},
                {"role": "user", "content": environment.initial_prompt()},
            ],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=self.config.sampling.enable_thinking,
        )

    def _observation_tokens(self, engine, observation: str, *, finished: bool) -> list[int]:
        prefix = "" if finished else "<|im_end|>"
        suffix = "" if self.config.sampling.enable_thinking else "<think>\n\n</think>\n\n"
        text = (
            f"{prefix}\n<|im_start|>user\n<tool_response>\n{observation}\n"
            f"</tool_response><|im_end|>\n<|im_start|>assistant\n{suffix}"
        )
        return engine.tokenizer.encode(text, add_special_tokens=False)

    def _attempt(
        self,
        cell: dict,
        attempt: dict,
        directory: Path,
        condition: Condition,
        engine,
        budget: Budget,
    ) -> None:
        environment = self.environment_factory()
        start, old_timings = budget.elapsed, dict(budget.timings)
        state = {"tool_calls": 0, "rebuilds": 0, "turns": [], "pending_tokens": []}
        try:
            with budget.charge("reset"):
                engine.start(attempt["seed"])
                environment.reset(cell["task_id"], attempt["seed"], directory / "environment")
                state["pending_tokens"] = self._initial_tokens(engine, environment)
            if self.config.stage == "diagnostic":
                from comet.diagnostic import restore_checkpoint

                state = restore_checkpoint(self, cell, environment, engine, budget)
                attempt["metrics"].update(state.pop("preparation_metrics", {}))
            self._trajectory(
                cell, attempt, directory, condition, engine, environment, budget, state
            )
            with budget.charge("save_outcome"):
                attempt["environment"] = environment.save(directory / "environment")
            attempt["status"] = "completed"
        except BudgetExpired as error:
            attempt.update(status="timeout", failure_reason=str(error))
        except (MemoryCapExceeded, MemoryError) as error:
            attempt.update(status="oom", failure_reason=str(error))
        except ContextLimit as error:
            attempt.update(status="context_limit", failure_reason=str(error))
        except UnsupportedPath as error:
            attempt.update(status="infeasible", failure_reason=str(error))
        except Exception as error:
            if type(error).__name__ == "OutOfMemoryError":
                attempt.update(status="oom", failure_reason=str(error))
            else:
                attempt.update(status="error", failure_reason=f"{type(error).__name__}: {error}")
        finally:
            cleanup_start = budget.elapsed
            cleanup = ([engine.synchronize] if hasattr(engine, "synchronize") else []) + [
                environment.close
            ]
            for finish in cleanup:
                try:
                    finish()
                except Exception as error:
                    status = (
                        "oom"
                        if isinstance(error, MemoryError)
                        or type(error).__name__ == "OutOfMemoryError"
                        else "error"
                    )
                    attempt.update(status=status, failure_reason=f"Attempt cleanup failed: {error}")
            budget.timings["cleanup"] = (
                budget.timings.get("cleanup", 0) + budget.elapsed - cleanup_start
            )
            if attempt["status"] == "completed" and not budget.remaining:
                attempt.update(status="timeout", failure_reason="Budget expired during cleanup")
            attempt["elapsed_seconds"] = budget.elapsed - start
            attempt["timings"] = {k: v - old_timings.get(k, 0) for k, v in budget.timings.items()}
            attempt["tool_calls"] = state["tool_calls"]
            attempt["rebuilds"] = state["rebuilds"]
            for key, value in _plain(engine.memory_stats()).items():
                if key.startswith("peak_"):
                    value = max(value, attempt["metrics"].get(key, 0))
                attempt["metrics"][key] = value
            write_json(
                directory / "trajectory.json",
                {
                    **state,
                    "raw_token_ids": list(engine.raw_token_ids),
                    "retention_events": getattr(engine, "retention_events", []),
                },
            )
            write_json(directory / "attempt.json", attempt)

    def _trajectory(
        self,
        cell: dict,
        attempt: dict,
        directory: Path,
        condition: Condition,
        engine,
        environment,
        budget: Budget,
        state: dict,
        *,
        stop_after_tools: int | None = None,
    ) -> None:
        from comet.appworld import parse_action

        while True:
            budget.check()
            context = len(engine.raw_token_ids) + len(state["pending_tokens"])
            if context >= self.config.engine.max_context_tokens:
                raise ContextLimit("Full raw token context reached configured limit; no truncation")
            decision = decide(
                condition.recovery,
                self.config.triggers,
                context,
                state["tool_calls"],
                state["rebuilds"],
            )
            event = decision.to_dict()
            if decision.triggered:
                with budget.charge("rebuild"):
                    recovery = _plain(
                        engine.recover(
                            list(engine.raw_token_ids) + state["pending_tokens"],
                            deadline=budget.deadline,
                        )
                    )
                event["result"] = recovery
                attempt["metrics"]["estimated_flops"] = attempt["metrics"].get(
                    "estimated_flops", 0
                ) + recovery.get("estimated_flops", 0)
                admitted = recovery.get("admitted", False)
                if admitted:
                    state["rebuilds"] += 1
                    state["pending_tokens"] = []
                    attempt["metrics"]["rebuild_prefill_tokens"] = recovery.get("input_tokens", 0)
                    attempt["metrics"]["rebuild_seconds"] = recovery.get("seconds", 0)
            attempt["recovery_events"].append(event)
            with budget.charge("inference"):
                generation = engine.generate(
                    state["pending_tokens"],
                    max_new_tokens=min(
                        self.config.sampling.max_new_tokens,
                        self.config.engine.max_context_tokens - context,
                    ),
                    temperature=self.config.sampling.temperature,
                    top_p=self.config.sampling.top_p,
                    deadline=budget.deadline,
                )
            result = _plain(generation)
            for key in ("decode_seconds", "prefill_seconds", "estimated_flops"):
                attempt["metrics"][key] = attempt["metrics"].get(key, 0) + result.get(key, 0)
            attempt["metrics"]["decode_tokens"] = attempt["metrics"].get(
                "decode_tokens", 0
            ) + result.get("decode_tokens", 0)
            attempt["metrics"]["flops_estimation_method"] = self.engine_metadata.get(
                "estimated_flops_method", "unavailable"
            )
            attempt["metrics"]["generated_tokens"] = attempt["metrics"].get(
                "generated_tokens", 0
            ) + len(result["token_ids"])
            attempt["metrics"]["prefill_tokens"] = attempt["metrics"].get(
                "prefill_tokens", 0
            ) + result.get("prompt_tokens", 0)
            response = engine.tokenizer.decode(result["token_ids"], skip_special_tokens=True)
            try:
                action = parse_action(response)
            except ValueError as error:
                action, observation = (
                    None,
                    f"Invalid action: {error}. Return one fenced Python block.",
                )
            else:
                with budget.charge("tool"):
                    observation = environment.execute(action, timeout_seconds=budget.remaining)
                    state["tool_calls"] += 1
            state["turns"].append(
                {"response": response, "action": action, "observation": observation}
            )
            state["pending_tokens"] = self._observation_tokens(
                engine, observation, finished=result["finished"]
            )
            with budget.charge("trajectory_save"):
                write_json(
                    directory / "trajectory.json",
                    {**state, "raw_token_ids": list(engine.raw_token_ids)},
                )
            with budget.charge("completion_observation"):
                completed = environment.completed()
            if completed or (
                stop_after_tools is not None and state["tool_calls"] >= stop_after_tools
            ):
                return


class ContextLimit(RuntimeError):
    pass
