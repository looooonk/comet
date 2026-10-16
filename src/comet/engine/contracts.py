from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

MINISGL_REVISION = "254c57bc84e4a7895159ba1062bd46c83626f511"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
METHODS = {"full", "streamingllm", "rkv", "agentkv"}


def retention_target(logical_tokens: int, retention: float, method: str) -> int:
    """Count per layer/head; mandatory entries are included in the denominator."""
    if method not in METHODS or logical_tokens < 0:
        raise ValueError("invalid method or logical token count")
    if method == "full":
        if retention != 1:
            raise ValueError("full cache requires retention=1")
        return logical_tokens
    if retention not in (0.8, 0.5, 0.25):
        raise ValueError("compressed retention must be 0.8, 0.5, or 0.25")
    fraction = Fraction(str(retention))
    requested = (logical_tokens * fraction.numerator + fraction.denominator - 1) // fraction.denominator
    mandatory = {"streamingllm": 16, "rkv": 8, "agentkv": 24}[method]
    return min(logical_tokens, max(requested, mandatory))


@dataclass(frozen=True)
class EngineSettings:
    model_path: str
    model_revision: str
    tokenizer_revision: str
    method: str
    retention: float
    max_context_tokens: int
    peak_vram_bytes: int
    workspace_reserve_bytes: int
    prefill_chunk_tokens: int
    require_a100: bool = True

    def __post_init__(self):
        retention_target(0, self.retention, self.method)
        if self.model_revision != MODEL_REVISION or self.tokenizer_revision != MODEL_REVISION:
            raise ValueError("model and tokenizer must use the recorded Qwen3-8B revision")
        for key in ("max_context_tokens", "peak_vram_bytes", "workspace_reserve_bytes", "prefill_chunk_tokens"):
            if isinstance(getattr(self, key), bool) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if self.workspace_reserve_bytes >= self.peak_vram_bytes:
            raise ValueError("workspace reserve must be smaller than the VRAM cap")
        if self.prefill_chunk_tokens > self.max_context_tokens:
            raise ValueError("prefill chunk exceeds maximum context")

    def fingerprint(self, *, policy: bool = True) -> str:
        data = asdict(self)
        data.pop("model_path")
        if not policy:
            data.pop("method")
            data.pop("retention")
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class GenerationResult:
    token_ids: list[int]
    finished: bool
    decode_seconds: float
    prefill_seconds: float
    prompt_tokens: int
    decode_tokens: int
    memory: dict
    estimated_flops: int = 0
    generated_tokens: int = 0


@dataclass(frozen=True)
class RecoveryResult:
    admitted: bool
    reason: str | None
    seconds: float
    input_tokens: int
    memory: dict
    estimated_flops: int = 0


def model_storage(model_path: str, revision: str) -> tuple[dict, int]:
    """Read tensor headers only; loading weights is excluded from task budgets."""
    path = Path(model_path).resolve()
    if path.name != revision:
        raise ValueError("model_path must be the pinned Hugging Face snapshot directory")
    config = json.loads((path / "config.json").read_text())
    if config.get("architectures") != ["Qwen3ForCausalLM"] or config.get("hidden_size") != 4096:
        raise ValueError("expected the pinned Qwen3-8B architecture")
    files = sorted(path.glob("*.safetensors"))
    if not files:
        raise ValueError("pinned model snapshot has no safetensors weights")
    parameters = 0
    for file in files:
        with file.open("rb") as stream:
            length = int.from_bytes(stream.read(8), "little")
            if not 0 < length < 100_000_000:
                raise ValueError("invalid safetensors header")
            header = json.loads(stream.read(length))
        for name, tensor in header.items():
            if name == "__metadata__":
                continue
            size = 1
            for dimension in tensor["shape"]:
                size *= dimension
            parameters += size
    return config, parameters
