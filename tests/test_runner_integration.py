import hashlib
import json
import os
import pickle
import random
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from comet.appworld import AppWorldAdapter, validate_tasks
from comet.artifacts import read_json, write_json
from comet.config import Condition, Experiment
from comet.engine import EngineSettings, MiniSGLangEngine, retention_target
from comet.history_benchmark import force_recorded_tokens
from comet.runner import Runner


def _config():
    base = Experiment.load(Path(__file__).resolve().parents[1] / "configs/pilot-smoke.json")
    config = replace(
        base, experiment_id="runner-checkpoint-integration-v1", stage="diagnostic", split="dev",
        task_ids=["0d8a4ee_1"], seeds=[17], budget_seconds=120, max_attempts=1,
        peak_vram_bytes=40 << 30,
        engine=replace(base.engine, max_context_tokens=8192, workspace_reserve_bytes=6 << 30,
                       prefill_chunk_tokens=256, device_name=None),
        sampling=replace(base.sampling, temperature=0.6, top_p=0.95,
                         max_new_tokens=512, enable_thinking=False),
        triggers=replace(base.triggers, fixed_tool_calls=1), checkpoint_after_tool_calls=1,
        conditions=[Condition("full", "full", 1.0, "never", 1),
                    Condition("agentkv_never", "agentkv", 0.5, "never", 1),
                    Condition("agentkv_fixed", "agentkv", 0.5, "fixed", 1)],
        notes="Synthetic forced-output integration check; no task-success or policy-quality claim.",
    )
    config.validate()
    return config


def _action(label, index):
    if label == "source" and index == 0:
        return """import random
import numpy as np
profile = apis.supervisor.show_profile()
password = next(row['password'] for row in apis.supervisor.show_account_passwords()
                if row['account_name'] == 'phone')
token = apis.phone.login(username=profile['phone_number'], password=password)['access_token']
marker = {'events': ['prefix'], 'python': random.random(), 'numpy': float(np.random.random())}
print(apis.phone.send_text_message(phone_number=profile['phone_number'],
      message='COMET checkpoint prefix', access_token=token))"""
    if label != "source" and index == 0:
        return f"""marker['events'].append({label!r})
marker['branch_python'] = random.random()
marker['branch_numpy'] = float(np.random.random())
print(apis.phone.send_text_message(phone_number=profile['phone_number'],
      message='COMET checkpoint branch ' + {label!r}, access_token=token))"""
    if label != "source" and index == 1:
        return "print(marker)\napis.supervisor.complete_task()"
    raise AssertionError(f"Unexpected validation action: {label}/{index}")


def _hash(value):
    return hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def _files(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def _rng(torch):
    import numpy

    return {"python": _hash(random.getstate()), "numpy": _hash(numpy.random.get_state()),
            "torch": _hash(torch.get_rng_state().tolist()),
            "cuda": [_hash(state.tolist()) for state in torch.cuda.get_rng_state_all()]}


def _environment(environment):
    from appworld.apps.phone import models as phone

    world = environment.world
    messages = ["COMET checkpoint prefix"] + [
        f"COMET checkpoint branch {label}" for label in ("full", "agentkv_never", "agentkv_fixed")
    ]
    return {"global_messages": phone.GlobalTextMessage.size(),
            "user_messages": phone.UserTextMessage.size(),
            "probe_messages": {message: sorted((row.id, row.record_hash)
                                               for row in phone.GlobalTextMessage.find_all(message=message))
                               for message in messages},
            "marker": deepcopy(world.shell.user_ns.get("marker")),
            "interactions": world.num_interactions,
            "sub_interactions": world.num_sub_interactions,
            "requests": _hash(world.requester.request_tracker.requests),
            "environment_io": _hash(world.environment_io),
            "completed": environment.completed()}


def _kv_hash(tensors, torch):
    result = hashlib.sha256()
    for layer in tensors:
        for tensor in layer:
            value = tensor.detach().cpu().contiguous()
            result.update(str((tuple(value.shape), value.dtype)).encode())
            result.update(value.view(torch.uint8).numpy().tobytes())
    return result.hexdigest()


def _check(root):
    config = _config()
    output = root / "run"
    source = output / "checkpoints/0d8a4ee_1-17"
    report = {"status": "running", "integration_only": True, "forced_outputs": True,
              "task_success_claim": False, "config_digest": config.digest,
              "environments": [], "generations": [], "branch_starts": [], "recoveries": []}
    write_json(root / "config.json", config.to_dict())
    write_json(root / "report.json", report)
    environments, engines = [], []
    saved = {}

    def journal():
        write_json(root / "report.json", report)

    class Environment(AppWorldAdapter):
        def __init__(self):
            super().__init__(os.environ["COMET_APPWORLD_ROOT"])
            self.label = (["source"] + [c.id for c in config.conditions])[len(environments)]
            self.record = {"label": self.label, "actions": [], "world_execute": []}
            environments.append(self)
            report["environments"].append(self.record)

        def reset(self, *args):
            super().reset(*args)
            execute = self.world.execute

            def observe(code, *args, **kwargs):
                self.record["world_execute"].append(code)
                return execute(code, *args, **kwargs)

            self.world.execute = observe
            self.record["reset"] = _environment(self)
            assert self.record["reset"]["marker"] is None
            assert not any(self.record["reset"]["probe_messages"].values())
            assert not self.record["reset"]["completed"]
            assert self.world.task.ground_truth is None

        def execute(self, code, **kwargs):
            self.record["actions"].append({"code": code})
            try:
                observation = super().execute(code, **kwargs)
                self.record["actions"][-1].update(observation=observation, state=_environment(self))
                if len(self.record["actions"]) == 1:
                    assert json.loads(observation)["message"] == "Text message sent."
                return observation
            finally:
                journal()

    def factory(condition):
        assert not engines, "Runner must reuse one loaded engine for all branches"
        engine = MiniSGLangEngine(EngineSettings(
            model_path=os.environ["COMET_MODEL_PATH"], model=config.engine.model,
            model_revision=config.engine.model_revision,
            tokenizer_revision=config.engine.tokenizer_revision,
            method=condition.method, retention=condition.retention,
            max_context_tokens=config.engine.max_context_tokens,
            peak_vram_bytes=config.peak_vram_bytes,
            workspace_reserve_bytes=config.engine.workspace_reserve_bytes,
            prefill_chunk_tokens=config.engine.prefill_chunk_tokens, require_a100=False,
        ))
        engines.append(engine)
        generate, recover = engine.generate, engine.recover

        def forced_generate(append, *args, **kwargs):
            if not environments:
                return generate(append, *args, **kwargs)
            assert not args
            environment = environments[-1]
            code = _action(environment.label, len(environment.record["actions"]))
            tokens = engine.tokenizer.encode(f"```python\n{code}\n```", add_special_tokens=False)
            tokens.append(engine.tokenizer.eos_token_id)
            assert len(tokens) <= kwargs["max_new_tokens"]
            before = list(engine.raw_token_ids)
            record = {"environment": environment.label, "append": list(append), "forced": tokens,
                      "raw_before": before, "status": "running"}
            report["generations"].append(record)
            try:
                with force_recorded_tokens(engine, tokens):
                    result = generate(append, **kwargs)
                assert result.token_ids == tokens and result.finished
                assert engine.raw_token_ids == before + list(append) + tokens
                record.update(status="completed", prompt_tokens=result.prompt_tokens)
                return result
            finally:
                record.update(raw_after=list(engine.raw_token_ids), progress=engine.last_generation)
                journal()

        def checked_recover(tokens, **kwargs):
            environment = environments[-1]
            record = {"environment": environment.label, "tokens": list(tokens), "status": "running"}
            report["recoveries"].append(record)
            before, rng = _environment(environment), _rng(engine.torch)
            executions = list(environment.record["world_execute"])
            try:
                assert environment.label == "agentkv_fixed" and not environment.record["actions"]
                assert tokens == saved["payload"]["raw"] + saved["agent"]["pending_tokens"]
                result = recover(tokens, **kwargs)
                assert result.admitted and engine.raw_token_ids == tokens
                assert _environment(environment) == before and _rng(engine.torch) == rng
                assert environment.record["world_execute"] == executions
                record.update(status="completed", environment_unchanged=True, rng_unchanged=True)
                return result
            finally:
                record["progress"] = engine.last_recovery
                journal()

        engine.generate, engine.recover = forced_generate, checked_recover
        return engine

    runner = Runner(config, output, factory, Environment, integration_smoke=True)
    trajectory = runner._trajectory

    def checked_trajectory(cell, attempt, directory, condition, engine, environment, budget, state, **kwargs):
        if environment.label != "source":
            if not saved:
                saved.update(payload=engine.torch.load(source / "engine", map_location="cpu", weights_only=True),
                             agent=read_json(source / "agent.json"), files=_files(source),
                             engine=read_json(source / "engine.json"))
                with (source / "environment/execution.pkl").open("rb") as stream:
                    saved["environment"] = pickle.load(stream)
                payload = saved["payload"]
                saved["rng"] = {"python": _hash(payload["python_rng"]),
                                "numpy": _hash(saved["environment"]["numpy_state"]),
                                "torch": _hash(payload["torch_rng"].tolist()),
                                "cuda": [_hash(value.tolist()) for value in payload["cuda_rng"]]}
                report["source"] = {"files": saved["files"], "rng": saved["rng"],
                                    "environment_python_rng": _hash(saved["environment"]["random_state"]),
                                    "kv_sha256": _kv_hash(payload["kv"], engine.torch)}
            memory = engine.memory_stats()
            entry = {"label": environment.label, "environment": _environment(environment),
                     "rng": _rng(engine.torch), "memory": memory,
                     "raw": list(engine.raw_token_ids), "agent": deepcopy(state)}
            report["branch_starts"].append(entry)
            journal()
            assert state == saved["agent"] and state["pending_tokens"]
            assert state["tool_calls"] == 1 and state["rebuilds"] == 0
            assert engine.raw_token_ids == saved["payload"]["raw"]
            assert entry["rng"] == saved["rng"]
            assert entry["environment"] == environments[0].record["actions"][0]["state"]
            assert not environment.record["actions"]
            assert not any("COMET checkpoint prefix" in code for code in environment.record["world_execute"])
            logical = memory["logical_cached_tokens"]
            assert logical == saved["engine"]["logical_cached_tokens"]
            assert memory["physical_cached_tokens"] == retention_target(logical, condition.retention, condition.method)
            if condition.method == "full":
                req = engine._state().req
                slots = engine.scheduler.engine.page_table[req.table_idx, :req.physical_cached_len].long()
                cache = engine.scheduler.engine.kv_cache
                tensors = ([method(layer).index_select(0, slots) for method in (cache.k_cache, cache.v_cache)]
                           for layer in range(cache.num_layers))
                entry["kv_sha256"] = _kv_hash(tensors, engine.torch)
                assert entry["kv_sha256"] == report["source"]["kv_sha256"]
                del tensors
        trajectory(cell, attempt, directory, condition, engine, environment, budget, state, **kwargs)

    runner._trajectory = checked_trajectory
    try:
        validate_tasks(config.split, config.task_ids)
        manifest = runner.run()
        assert manifest["status"] == "completed" and manifest["integration_smoke"]
        preparation = read_json(source / "preparation.json")
        assert preparation["status"] == "completed" and preparation["checkpoint_eligible"]
        assert not preparation["source_completed"]
        assert _files(source) == saved["files"]
        assert len(report["branch_starts"]) == 3 and len(report["recoveries"]) == 1
        prefix = environments[0].record
        assert len(prefix["actions"]) == 1
        assert sum("COMET checkpoint prefix" in code for env in report["environments"]
                   for code in env["world_execute"]) == 1
        assert prefix["actions"][0]["state"]["global_messages"] == prefix["reset"]["global_messages"] + 1
        prefix_messages = prefix["actions"][0]["state"]["probe_messages"]["COMET checkpoint prefix"]
        assert len(prefix_messages) == 1
        draws = []
        for condition, reference, environment in zip(config.conditions, manifest["cells"], environments[1:], strict=True):
            cell = read_json(output / reference["path"])
            assert cell["completed"] and len(cell["attempts"]) == 1
            attempt = cell["attempts"][0]
            assert attempt["status"] == "completed", attempt
            assert attempt["timings"]["shared_checkpoint_preparation"] == preparation["elapsed_seconds"]
            assert attempt["timings"]["reset"] > 0 and attempt["timings"]["checkpoint_restore"] > 0
            assert preparation["elapsed_seconds"] < attempt["budget_elapsed_seconds"] <= config.budget_seconds
            assert attempt["budget_elapsed_seconds"] >= sum(attempt["timings"].values())
            assert attempt["tool_calls"] == 3 and len(environment.record["actions"]) == 2
            assert attempt["rebuilds"] == int(condition.recovery == "fixed")
            assert attempt["metrics"]["estimated_flops"] > preparation["metrics"]["estimated_flops"] > 0
            assert attempt["metrics"]["peak_total_vram_bytes"] <= config.peak_vram_bytes
            final = environment.record["actions"][-1]["state"]
            assert final["completed"] and final["marker"]["events"] == ["prefix", condition.id]
            assert final["global_messages"] == prefix["reset"]["global_messages"] + 2
            assert len(final["probe_messages"][f"COMET checkpoint branch {condition.id}"]) == 1
            assert final["probe_messages"]["COMET checkpoint prefix"] == prefix_messages
            assert sum(len(rows) for rows in final["probe_messages"].values()) == 2
            draws.append((final["marker"]["branch_python"], final["marker"]["branch_numpy"]))
            calls = [row for row in report["generations"] if row["environment"] == condition.id]
            assert len(calls) == 2
            pending = saved["agent"]["pending_tokens"]
            if condition.recovery == "fixed":
                assert calls[0]["append"] == [] and calls[0]["prompt_tokens"] == 0
                assert calls[0]["raw_before"] == saved["payload"]["raw"] + pending
                assert attempt["recovery_events"][-1]["reason"] == "already_rebuilt"
            else:
                assert calls[0]["append"] == pending
                unforwarded = len(saved["payload"]["raw"]) - saved["engine"]["logical_cached_tokens"]
                assert calls[0]["prompt_tokens"] == len(pending) + unforwarded
            assert calls[0]["raw_after"] == saved["payload"]["raw"] + pending + calls[0]["forced"]
        assert len(set(draws)) == 1
        assert not (output / "scores.json").exists()
        report.update(status="passed", preparation=preparation, source_unchanged=True,
                      branch_random_draws=draws, engine_instances=len(engines))
    except BaseException as error:
        report.update(status="failed", failure=f"{type(error).__name__}: {error}")
        raise
    finally:
        journal()


@pytest.mark.gpu
@pytest.mark.appworld
def test_live_runner_checkpoint_branches():
    directory = os.environ.get("COMET_CHECKPOINT_ARTIFACT_DIR")
    if not directory:
        pytest.skip("Set COMET_CHECKPOINT_ARTIFACT_DIR for the combined Qwen3-8B/AppWorld check")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    try:
        with (root / "process.log").open("w") as stream:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(root)],
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=900)
    except subprocess.TimeoutExpired:
        report = read_json(root / "report.json") if (root / "report.json").exists() else {}
        report.update(status="failed", integration_only=True, failure="900-second harness deadline expired")
        write_json(root / "report.json", report)
        raise
    report = read_json(root / "report.json") if (root / "report.json").exists() else {}
    report["process_returncode"] = result.returncode
    if result.returncode:
        report.update(status="failed", integration_only=True)
        report.setdefault("failure", "Child process failed; inspect process.log")
    write_json(root / "report.json", report)
    assert result.returncode == 0, f"Combined validation failed; inspect {root / 'process.log'}"
    assert read_json(root / "report.json")["status"] == "passed"


def test_checkpoint_validation_config_and_action_bounds():
    config = _config()
    assert config.engine.model == "Qwen/Qwen3-8B" and config.split == "dev"
    assert [c.recovery for c in config.conditions] == ["never", "never", "fixed"]
    assert config.checkpoint_after_tool_calls == config.triggers.fixed_tool_calls == 1
    assert "complete_task" not in _action("source", 0)
    with pytest.raises(AssertionError, match="Unexpected validation action"):
        _action("source", 1)
    with pytest.raises(AssertionError, match="Unexpected validation action"):
        _action("full", 2)


if __name__ == "__main__":
    _check(Path(sys.argv[1]))
