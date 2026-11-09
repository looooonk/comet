from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from comet.engine.contracts import retention_target, validate_model


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _number(value: object, name: str, minimum: float, maximum: float = math.inf) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}]")


@dataclass(frozen=True)
class Sampling:
    temperature: float
    top_p: float
    max_new_tokens: int
    enable_thinking: bool


@dataclass(frozen=True)
class Triggers:
    fixed_tool_calls: int
    dynamic_context_tokens: int
    dynamic_tool_calls: int
    dynamic_rule: str


@dataclass(frozen=True)
class Engine:
    model: str
    model_revision: str
    tokenizer_revision: str
    dtype: str
    max_context_tokens: int
    workspace_reserve_bytes: int
    prefill_chunk_tokens: int
    device_name: str | None = None


@dataclass(frozen=True)
class Condition:
    id: str
    method: str
    retention: float
    recovery: str
    max_attempts: int


@dataclass(frozen=True)
class AgentProtocol:
    max_consecutive_errors: int = 0
    require_executable: bool = False


@dataclass(frozen=True)
class Experiment:
    schema_version: int
    experiment_id: str
    stage: str
    split: str
    task_ids: list[str]
    seeds: list[int]
    budget_seconds: float
    peak_vram_bytes: int
    max_attempts: int
    engine: Engine
    sampling: Sampling
    triggers: Triggers
    conditions: list[Condition]
    prompt: str
    checkpoint_after_tool_calls: int | None
    frozen: dict | None
    notes: str
    agent: AgentProtocol = field(default_factory=AgentProtocol)

    @classmethod
    def load(cls, path: str | Path, *, allow_unfrozen: bool = False) -> Experiment:
        return cls.from_dict(_load(Path(path), set()), allow_unfrozen=allow_unfrozen)

    @classmethod
    def from_dict(cls, data: dict, *, allow_unfrozen: bool = False) -> Experiment:
        data = dict(data)
        for name, kind in (("engine", Engine), ("sampling", Sampling), ("triggers", Triggers)):
            data[name] = kind(**data[name])
        data["agent"] = AgentProtocol(**data.get("agent", {}))
        data["conditions"] = [Condition(**c) for c in data["conditions"]]
        result = cls(**data)
        result.validate(allow_unfrozen=allow_unfrozen)
        return result

    def validate(self, *, allow_unfrozen: bool = False) -> None:
        if self.schema_version != 1 or self.stage not in {"pilot", "diagnostic", "final"}:
            raise ValueError("Unsupported schema version or experiment stage")
        if self.split not in {"train", "dev", "test_normal", "test_challenge"}:
            raise ValueError("Use an explicit AppWorld split")
        if self.stage != "final" and self.split not in {"train", "dev"}:
            raise ValueError("Pilot and diagnostic tuning must use train/dev")
        if self.stage == "final" and self.split not in {"test_normal", "test_challenge"}:
            raise ValueError("Final evaluation requires an explicit test split")
        if self.stage == "final" and not allow_unfrozen:
            if not self.frozen or self.frozen.get("settings_digest") != self.settings_digest:
                raise ValueError("Final evaluation requires a matching frozen settings record")
            if not self.frozen.get("pilot_evidence"):
                raise ValueError("Freeze must identify measured train/dev pilot evidence")
        for name, values in (("task_ids", self.task_ids), ("seeds", self.seeds)):
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{name} must be nonempty and unique")
        if any(
            not isinstance(t, str) or not t or not t.replace("_", "").isalnum()
            for t in self.task_ids
        ):
            raise ValueError("Invalid AppWorld task ID")
        if not self.experiment_id or not self.prompt.strip():
            raise ValueError("experiment_id and prompt are required")
        for seed in self.seeds:
            _number(seed, "seed", 0, 2**32 - 1)
            if not isinstance(seed, int):
                raise ValueError("seeds must be integers")
        for name, value in (
            ("max_attempts", self.max_attempts),
            ("peak_vram_bytes", self.peak_vram_bytes),
            ("max_context_tokens", self.engine.max_context_tokens),
            ("workspace_reserve_bytes", self.engine.workspace_reserve_bytes),
            ("prefill_chunk_tokens", self.engine.prefill_chunk_tokens),
            ("max_new_tokens", self.sampling.max_new_tokens),
            ("fixed_tool_calls", self.triggers.fixed_tool_calls),
            ("dynamic_context_tokens", self.triggers.dynamic_context_tokens),
            ("dynamic_tool_calls", self.triggers.dynamic_tool_calls),
        ):
            _number(value, name, 1)
            if not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        _number(self.budget_seconds, "budget_seconds", 0.001)
        _number(self.sampling.temperature, "temperature", 0)
        _number(self.sampling.top_p, "top_p", 1e-9, 1)
        if not isinstance(self.sampling.enable_thinking, bool):
            raise ValueError("enable_thinking must be boolean")
        _number(self.agent.max_consecutive_errors, "max_consecutive_errors", 0)
        if not isinstance(self.agent.max_consecutive_errors, int):
            raise ValueError("max_consecutive_errors must be an integer")
        if not isinstance(self.agent.require_executable, bool):
            raise ValueError("require_executable must be boolean")
        if self.triggers.dynamic_rule not in {"and", "or"}:
            raise ValueError("dynamic_rule must be and or or")
        if self.engine.dtype != "bfloat16":
            raise ValueError("All supported models require BF16")
        if self.engine.device_name is not None and (
            not isinstance(self.engine.device_name, str) or not self.engine.device_name.strip()
        ):
            raise ValueError("device_name must be an explicit GPU model name")
        profile = validate_model(self.engine.model, self.engine.model_revision,
                                 self.engine.tokenizer_revision)
        if self.engine.model != "Qwen/Qwen3-8B" and self.stage != "pilot":
            raise ValueError(f"{self.engine.model} is an exploratory pilot model; "
                             "the research contract uses Qwen3-8B")
        if self.sampling.enable_thinking and not profile["supports_thinking"]:
            raise ValueError(f"{self.engine.model} requires enable_thinking=false")
        if self.engine.workspace_reserve_bytes >= self.peak_vram_bytes:
            raise ValueError("Workspace reserve must fit inside the total VRAM cap")
        if self.sampling.max_new_tokens > self.engine.max_context_tokens:
            raise ValueError("Generation limit cannot exceed context limit")
        if not self.conditions or len({c.id for c in self.conditions}) != len(self.conditions):
            raise ValueError("Conditions must be nonempty with unique IDs")
        for c in self.conditions:
            if not c.id or any(x not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for x in c.id):
                raise ValueError("Condition IDs must be safe lowercase names")
            if c.method not in {"full", "streamingllm", "rkv", "agentkv"}:
                raise ValueError(f"Unknown eviction method: {c.method}")
            if c.recovery not in {"never", "fixed", "dynamic"}:
                raise ValueError(f"Unknown recovery policy: {c.recovery}")
            retention_target(0, c.retention, c.method)
            if c.method == "full":
                if c.retention != 1 or c.recovery != "never":
                    raise ValueError("Full-cache controls disable eviction and recovery")
            if (
                isinstance(c.max_attempts, bool)
                or not isinstance(c.max_attempts, int)
                or c.max_attempts not in {1, self.max_attempts}
            ):
                raise ValueError("Condition attempt limit must be 1 or the shared N")
        if self.checkpoint_after_tool_calls is not None:
            _number(self.checkpoint_after_tool_calls, "checkpoint_after_tool_calls", 1)
            if not isinstance(self.checkpoint_after_tool_calls, int):
                raise ValueError("Checkpoint tool count must be integer")
        if self.stage == "diagnostic" and self.checkpoint_after_tool_calls is None:
            raise ValueError("Diagnostics require an explicit checkpoint boundary")
        if self.stage == "diagnostic" and self.max_attempts != 1:
            raise ValueError("A diagnostic cell is one continuation of its shared checkpoint")

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.engine.device_name is None:
            del data["engine"]["device_name"]
        if not self.agent.require_executable:
            del data["agent"]["require_executable"]
        return data

    @property
    def settings_digest(self) -> str:
        data = self.to_dict()
        data.pop("frozen")
        data.pop("notes")
        return digest(data)

    @property
    def digest(self) -> str:
        return digest(self.to_dict())


def comparison_matrix(max_attempts: int) -> list[Condition]:
    controls = [
        Condition("full_once", "full", 1.0, "never", 1),
        Condition("full_best_of_n", "full", 1.0, "never", max_attempts),
    ]
    return controls + [
        Condition(
            f"{method}_{int(retention * 100)}_{policy}", method, retention, policy, max_attempts
        )
        for method in ("streamingllm", "rkv", "agentkv")
        for retention in (0.8, 0.5, 0.25)
        for policy in ("never", "fixed", "dynamic")
    ]


def attempt_seed(seed: int, attempt_index: int) -> int:
    return int(digest([seed, attempt_index])[:8], 16)


def _load(path: Path, seen: set[Path]) -> dict:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"Configuration inheritance cycle: {path}")
    data = json.loads(path.read_text())
    parent = data.pop("extends", None)
    if parent is None:
        return data
    base = _load(path.parent / parent, seen | {path})
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base
