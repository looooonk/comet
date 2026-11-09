from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path
from typing import Callable

from comet.agent import execution_feedback
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
            raise ValueError("Final evaluation requires the selected qualified hardware")

    def run(self, *, resume: bool = False, max_cells: int | None = None) -> dict:
        if max_cells is not None:
            if type(max_cells) is not int or max_cells <= 0:
                raise ValueError("max_cells must be a positive integer")
            if self.config.stage == "diagnostic":
                raise ValueError("max_cells is unsupported for diagnostic checkpoint preparation")
        with run_lock(self.output):
            manifest = self._manifest(resume)
            if manifest["status"] == "completed":
                return manifest
            launch = {"at_unix": wall_time(), "max_cells": max_cells, "completed_cells": 0}
            manifest.setdefault("launches", []).append(launch)
            write_json(self.output / "manifest.json", manifest)
            initial = (
                Condition("diagnostic_source", "full", 1.0, "never", 1)
                if self.config.stage == "diagnostic"
                else self.config.conditions[0]
            )
            try:
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
                            self._interrupt_cell(cell)
                        cell.update(completed=True, infeasible=True, failure_reason=str(error))
                        write_json(path, cell)
                        launch["completed_cells"] += 1
                        if launch["completed_cells"] == max_cells:
                            break
                    return self._finish_launch(manifest, launch)
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
                    launch["engine"] = self.engine_metadata
                    write_json(self.output / "manifest.json", manifest)
                    self._warmup_environment(manifest, launch)
                    if self.config.stage == "diagnostic":
                        from comet.diagnostic import prepare_checkpoints

                        prepare_checkpoints(self, manifest, engine)
                    for condition in self.config.conditions:
                        if launch["completed_cells"] == max_cells:
                            break
                        pending = [
                            c
                            for c in manifest["cells"]
                            if c["condition_id"] == condition.id and not self._done(c)
                        ]
                        if max_cells is not None:
                            pending = pending[:max_cells - launch["completed_cells"]]
                        if not pending:
                            continue
                        engine.set_policy(condition.method, condition.retention)
                        for reference in pending:
                            self._run_cell(manifest, reference, condition, engine)
                            launch["completed_cells"] += 1
                finally:
                    engine.close()
                return self._finish_launch(manifest, launch)
            except BaseException as error:
                try:
                    write_json(self.output / "manifest.json", manifest)
                except Exception as journal_error:
                    error.add_note(f"Could not preserve launch progress: {journal_error}")
                raise

    def _warmup_environment(self, manifest: dict, launch: dict) -> None:
        settings = self.config.environment_warmup
        if settings is None:
            return
        from comet.appworld import validate_tasks

        directory = self.output / "initialization" / f"launch-{len(manifest['launches']) - 1:03d}"
        record = {
            "status": "running", "task_id": settings.task_id, "seed": settings.seed,
            "split": "train", "charged_to_task_budget": False, "tool_calls": 0,
            "model_observations": 0, "artifact_dir": str(directory.relative_to(self.output)),
        }
        launch["environment_initialization"] = record
        write_json(self.output / "manifest.json", manifest)
        started = self.clock()
        try:
            validate_tasks("train", [settings.task_id])
            environment = self.environment_factory()
            try:
                environment.reset(settings.task_id, settings.seed, directory / "environment")
            finally:
                environment.close()
            record["status"] = "completed"
        except BaseException as error:
            record.update(status="failed", failure_reason=f"{type(error).__name__}: {error}")
            raise
        finally:
            record["seconds"] = self.clock() - started
            write_json(self.output / "manifest.json", manifest)

    def _finish_launch(self, manifest: dict, launch: dict) -> dict:
        completed = all(self._done(reference) for reference in manifest["cells"])
        launch.update(finished_at_unix=wall_time(),
                      stop_reason="all_cells_completed" if completed else "max_cells")
        manifest["status"] = "completed" if completed else "running"
        if completed:
            manifest["finished_at_unix"] = launch["finished_at_unix"]
        else:
            manifest.pop("finished_at_unix", None)
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
                self._interrupt_cell(cell)
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

    def _interrupt_cell(self, cell: dict) -> None:
        reserved = max(0.0, self.config.budget_seconds - cell["elapsed_seconds"])
        for attempt in cell["attempts"]:
            if attempt["status"] == "running":
                path = self.output / attempt["artifact_dir"] / "attempt.json"
                if path.exists():
                    latest = read_json(path)
                    if any(latest.get(key) != attempt.get(key)
                           for key in ("attempt_index", "seed", "artifact_dir")):
                        raise ValueError("Interrupted attempt journal has a different identity")
                    attempt.update(latest)
                if attempt["status"] != "running":
                    observed = max(
                        attempt.get("budget_elapsed_seconds", 0),
                        cell["elapsed_seconds"] + attempt.get("elapsed_seconds", 0),
                    )
                    cell["observed_elapsed_seconds"] = observed
                    cell["reserved_budget_seconds"] = max(0.0, self.config.budget_seconds - observed)
                    if attempt["status"] == "completed" and observed >= self.config.budget_seconds:
                        attempt.update(
                            status="timeout",
                            failure_reason="Durable attempt journal reached or exceeded the shared budget",
                            budget_elapsed_seconds=observed,
                        )
                        write_json(path, attempt)
                    continue
                attempt.update(
                    status="interrupted",
                    failure_reason="process_interrupted",
                    budget_elapsed_seconds=self.config.budget_seconds,
                    reserved_budget_seconds=reserved,
                )
                metrics = attempt.setdefault("metrics", {})
                coverage = metrics.setdefault("metric_coverage", {})
                for key in ("estimated_flops", "generated_tokens", "prefill_tokens", "decode_tokens",
                            "rebuild_prefill_tokens", "peak_kv_bytes", "peak_total_vram_bytes",
                            "prefill_seconds", "decode_seconds", "rebuild_seconds"):
                    if isinstance(metrics.get(key), (int, float)):
                        coverage[key] = "partial" if key.endswith("seconds") else "lower_bound"
                write_json(path, attempt)
        cell.update(elapsed_seconds=max(self.config.budget_seconds, cell.get("observed_elapsed_seconds", 0)),
                    completed=True, inflight=False)

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
            return_dict=False,
            add_generation_prompt=True,
            enable_thinking=self.config.sampling.enable_thinking,
        )

    def _observation_tokens(self, engine, observation: str, *, finished: bool) -> list[int]:
        prefix = "" if finished else "<|im_end|>"
        if self.config.engine.model == "Qwen/Qwen3-4B-Instruct-2507":
            turn = engine.tokenizer.apply_chat_template(
                [{"role": "user", "content": f"<tool_response>\n{observation}\n</tool_response>"}],
                tokenize=False, add_generation_prompt=True,
            )
            return engine.tokenizer.encode(prefix + "\n" + turn, add_special_tokens=False)
        suffix = "" if self.config.sampling.enable_thinking else "<think>\n\n</think>\n\n"
        # The pinned 3.5 template rejects isolated tool turns; its suffix is checked on a full dialogue.
        if self.config.engine.model == "Qwen/Qwen3.5-9B" and self.config.sampling.enable_thinking:
            suffix = "<think>\n"
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
        engine_started = False
        try:
            if self.config.stage == "diagnostic":
                from comet.diagnostic import charge_checkpoint_preparation, restore_checkpoint

                charge_checkpoint_preparation(self, cell, attempt, budget)
            with budget.charge("reset"):
                engine_started = True
                engine.start(attempt["seed"])
                environment.reset(cell["task_id"], attempt["seed"], directory / "environment")
                state["pending_tokens"] = self._initial_tokens(engine, environment)
            if self.config.stage == "diagnostic":
                state = restore_checkpoint(self, cell, environment, engine, budget)
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
            cleanup = ([engine.synchronize] if engine_started and hasattr(engine, "synchronize") else []) + [
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
                    attempt.setdefault("cleanup_errors", []).append(f"{type(error).__name__}: {error}")
                    if attempt["status"] == "completed":
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
            try:
                memory = _plain(engine.memory_stats()) if engine_started else {}
            except Exception as error:
                attempt["metrics"]["memory_error"] = f"{type(error).__name__}: {error}"
                if attempt["status"] == "completed":
                    attempt.update(status="error", failure_reason=f"Final memory measurement failed: {error}")
            else:
                for key, value in memory.items():
                    if key.startswith("peak_"):
                        value = max(value, attempt["metrics"].get(key, 0))
                    attempt["metrics"][key] = value
            write_json(
                directory / "trajectory.json",
                {
                    **state,
                    "raw_token_ids": list(engine.raw_token_ids) if engine_started else [],
                    "retention_events": getattr(engine, "retention_events", []) if engine_started else [],
                },
            )
            write_json(directory / "attempt.json", attempt)

    def _record_operation(self, attempt: dict, result: dict, *, recovery: bool = False) -> None:
        metrics = attempt["metrics"]
        coverage = metrics.setdefault("metric_coverage", {})
        fields = {"estimated_flops": "estimated_flops"}
        if "compaction_seconds" in result:
            fields["compaction_seconds"] = "compaction_seconds"
        if recovery:
            fields.update(rebuild_seconds="seconds", rebuild_prefill_tokens="prompt_tokens")
        else:
            fields.update(decode_seconds="decode_seconds", prefill_seconds="prefill_seconds",
                          prefill_tokens="prompt_tokens", decode_tokens="decode_tokens",
                          generated_tokens="generated_tokens")
            if "token_ids" in result:
                result = {**result, "generated_tokens": len(result["token_ids"])}
        failed = result.get("status") == "failed"
        for name, source in fields.items():
            previous = coverage.get(name, "complete")
            if source not in result:
                coverage[name] = ("partial" if name.endswith("seconds") else "lower_bound") \
                    if name in metrics else "unavailable"
                continue
            metrics[name] = metrics.get(name, 0) + result[source]
            current = "complete"
            if failed and name != "generated_tokens":
                current = "partial" if name.endswith("seconds") else "lower_bound"
            if previous != "complete":
                current = "partial" if name.endswith("seconds") else "lower_bound"
            coverage[name] = current
        for name in ("incomplete_forward_tokens", "incomplete_forward_estimated_flops"):
            if name in result:
                metrics[name] = metrics.get(name, 0) + result[name]
        for name, value in result.get("memory", {}).items():
            if name.startswith("peak_"):
                metrics[name] = max(metrics.get(name, 0), value)
        metrics["flops_estimation_method"] = self.engine_metadata.get(
            "estimated_flops_method", "unavailable"
        )

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
            attempt["recovery_events"].append(event)
            if decision.triggered:
                event["result"] = {"status": "pending", "admitted": None,
                                   "allowance_consumed": None}
                write_json(directory / "recovery_events.json", attempt["recovery_events"])
                write_json(directory / "attempt.json", attempt)
                recovery, error, called = {}, None, False
                started = budget.elapsed
                try:
                    with budget.charge("rebuild"):
                        called = True
                        recovery = _plain(engine.recover(
                            list(engine.raw_token_ids) + state["pending_tokens"],
                            deadline=budget.deadline,
                        ))
                except BaseException as failure:
                    error = failure
                    raise
                finally:
                    progress = getattr(engine, "last_recovery", {}) if called else {}
                    recovery = {**recovery, **progress}
                    recovery.setdefault("status", "failed" if error else
                                        "completed" if recovery.get("admitted") else "denied")
                    recovery.setdefault("admitted", None)
                    recovery.setdefault("allowance_consumed", recovery["admitted"])
                    recovery.setdefault("seconds", budget.elapsed - started)
                    if error is not None:
                        recovery.setdefault("failure_reason", f"{type(error).__name__}: {error}")
                    event["result"] = recovery
                    if recovery["allowance_consumed"]:
                        state["rebuilds"] += 1
                        if len(engine.raw_token_ids) >= context:
                            state["pending_tokens"] = []
                    attempt["rebuilds"] = state["rebuilds"]
                    self._record_operation(attempt, recovery, recovery=True)
                    write_json(directory / "recovery_events.json", attempt["recovery_events"])
                    write_json(directory / "attempt.json", attempt)
            result, called, error = {}, False, None
            try:
                with budget.charge("inference"):
                    called = True
                    result = _plain(engine.generate(
                        state["pending_tokens"],
                        max_new_tokens=min(
                            self.config.sampling.max_new_tokens,
                            self.config.engine.max_context_tokens - context,
                        ),
                        temperature=self.config.sampling.temperature,
                        top_p=self.config.sampling.top_p,
                        deadline=budget.deadline,
                    ))
            except BaseException as failure:
                error = failure
                raise
            finally:
                progress = getattr(engine, "last_generation", {}) if called else {}
                recorded = {**result, **progress}
                recorded.setdefault("status", "failed" if error else "completed")
                self._record_operation(attempt, recorded)
                if error is not None:
                    recorded.setdefault("failure_reason", f"{type(error).__name__}: {error}")
                    attempt.setdefault("generation_failures", []).append(recorded)
                    write_json(directory / "attempt.json", attempt)
            response = engine.tokenizer.decode(result["token_ids"], skip_special_tokens=True)
            try:
                action = parse_action(
                    response, require_executable=(self.config.agent.require_executable
                                                  or bool(self.config.agent.max_consecutive_errors))
                )
            except ValueError as error:
                action, observation = (
                    None,
                    f"Invalid action: {error}. Return one fenced Python block.",
                )
            else:
                with budget.charge("tool"):
                    observation = environment.execute(action, timeout_seconds=budget.remaining)
                    state["tool_calls"] += 1
            turn = {"response": response, "action": action, "observation": observation}
            feedback = ""
            limit = self.config.agent.max_consecutive_errors
            if limit:
                with budget.charge("agent_protocol"):
                    streak, feedback = execution_feedback(
                        observation, state.get("consecutive_errors", 0), limit
                    )
                    state["consecutive_errors"] = streak
                    turn.update(consecutive_errors=streak, agent_feedback=feedback)
            state["turns"].append(turn)
            visible_observation = observation
            if feedback:
                visible_observation += f"\n\n<execution_feedback>\n{feedback}\n</execution_feedback>"
            state["pending_tokens"] = self._observation_tokens(
                engine, visible_observation, finished=result["finished"]
            )
            with budget.charge("trajectory_save"):
                write_json(
                    directory / "trajectory.json",
                    {**state, "raw_token_ids": list(engine.raw_token_ids)},
                )
            with budget.charge("completion_observation"):
                completed = environment.completed()
            if completed:
                return
            if limit and state["consecutive_errors"] >= limit:
                raise AgentProtocolError(f"{limit} consecutive execution/action failures")
            if stop_after_tools is not None and state["tool_calls"] >= stop_after_tools:
                return


class ContextLimit(RuntimeError):
    pass


class AgentProtocolError(RuntimeError):
    pass
