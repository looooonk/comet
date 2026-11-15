from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

from comet.errors import MemoryCapExceeded, UnsupportedPath

MINISGL_REVISION = "254c57bc84e4a7895159ba1062bd46c83626f511"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
MODEL_PROFILES = {
    "Qwen/Qwen3.5-9B": {
        "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "parameters": 9653104368,
        "supports_thinking": True,
        "backend": "transformers_hybrid",
        "dimensions": {
            "hidden_size": 4096,
            "num_hidden_layers": 32,
            "num_attention_heads": 16,
            "intermediate_size": 12288,
        },
    },
    "Qwen/Qwen3-8B": {
        "revision": MODEL_REVISION,
        "parameters": 8190735360,
        "supports_thinking": True,
        "dimensions": {
            "hidden_size": 4096,
            "num_hidden_layers": 36,
            "num_attention_heads": 32,
            "intermediate_size": 12288,
        },
    },
    "Qwen/Qwen3-14B": {
        "revision": "40c069824f4251a91eefaf281ebe4c544efd3e18",
        "parameters": 14768307200,
        "supports_thinking": True,
        "dimensions": {
            "hidden_size": 5120,
            "num_hidden_layers": 40,
            "num_attention_heads": 40,
            "intermediate_size": 17408,
        },
    },
    "Qwen/Qwen3-4B-Instruct-2507": {
        "revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "parameters": 4022468096,
        "supports_thinking": False,
        "dimensions": {
            "hidden_size": 2560,
            "num_hidden_layers": 36,
            "num_attention_heads": 32,
            "intermediate_size": 9728,
        },
        "architecture": {
            "tie_word_embeddings": True,
            "rope_theta": 5000000,
            "max_position_embeddings": 262144,
        },
    },
}
METHODS = {"full", "streamingllm", "rkv", "agentkv"}


def validate_model(model: str, revision: str, tokenizer_revision: str) -> dict:
    profile = MODEL_PROFILES.get(model)
    if profile is None or revision != profile["revision"] or tokenizer_revision != revision:
        raise ValueError("model and tokenizer must match a recorded model/revision pair")
    return profile


def retention_target(logical_tokens: int, retention: float, method: str, protected: int = 0) -> int:
    """Count per layer/head; mandatory and protected entries are inside the denominator."""
    if method not in METHODS or logical_tokens < 0:
        raise ValueError("invalid method or logical token count")
    if isinstance(retention, bool) or not isinstance(retention, (int, float)):
        raise ValueError("retention must be numeric")
    if isinstance(protected, bool) or not isinstance(protected, int) or protected < 0:
        raise ValueError("protected prefix must be a nonnegative token count")
    if method == "full":
        if retention != 1 or protected:
            raise ValueError("full cache requires retention=1 and no protected prefix")
        return logical_tokens
    if not 0 < retention < 1:
        raise ValueError("compressed retention must be strictly between 0 and 1")
    fraction = Fraction(str(retention))
    requested = (
        logical_tokens * fraction.numerator + fraction.denominator - 1
    ) // fraction.denominator
    mandatory = {"streamingllm": 16, "rkv": 8, "agentkv": 24}[method] + protected
    return min(logical_tokens, max(requested, mandatory))


def selector_overrides(method: str, target: int, sink_tokens: int, protected: int = 0) -> dict:
    """Selector parameters for one compaction; a protected prefix extends the selector's own sink."""
    sink = max(sink_tokens, protected)
    if method == "streamingllm":
        sink = min(target, sink)
        return {"sink_tokens": sink, "window_tokens": target - sink}
    return {"budget": target, "sink_tokens": sink} if protected else {"budget": target}


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
    model: str = "Qwen/Qwen3-8B"
    device_name: str | None = None
    backend: str = "native_minisgl"
    protected_prefix_tokens: int = 0

    def __post_init__(self):
        retention_target(0, self.retention, self.method, self.protected_prefix_tokens)
        profile = validate_model(self.model, self.model_revision, self.tokenizer_revision)
        if self.backend != profile.get("backend", "native_minisgl"):
            raise ValueError("model architecture does not match the selected backend")
        for key in (
            "max_context_tokens",
            "peak_vram_bytes",
            "workspace_reserve_bytes",
            "prefill_chunk_tokens",
        ):
            if isinstance(getattr(self, key), bool) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if self.workspace_reserve_bytes >= self.peak_vram_bytes:
            raise ValueError("workspace reserve must be smaller than the VRAM cap")
        if self.prefill_chunk_tokens > self.max_context_tokens:
            raise ValueError("prefill chunk exceeds maximum context")
        if self.device_name is not None and (
            not isinstance(self.device_name, str) or not self.device_name.strip()
        ):
            raise ValueError("device_name must be an explicit GPU model name")

    def validate_device(self, name: str, total_bytes: int) -> None:
        if self.device_name is not None:
            if name != self.device_name:
                raise UnsupportedPath(f"Configured GPU {self.device_name!r}; found {name!r}")
        elif self.require_a100 and ("A100" not in name or total_bytes < 79_000_000_000):
            raise UnsupportedPath(
                "Legacy configs require A100 80GB; select device_name for qualified hardware"
            )
        if self.peak_vram_bytes > total_bytes:
            raise MemoryCapExceeded("configured VRAM cap exceeds device capacity")

    def fingerprint(self, *, policy: bool = True) -> str:
        data = asdict(self)
        data.pop("model_path")
        if self.device_name is None:
            data.pop("device_name")
        if self.backend == "native_minisgl":
            data.pop("backend")
        if not policy or not self.protected_prefix_tokens:
            data.pop("protected_prefix_tokens")
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


def model_storage(model_path: str, revision: str, model: str = "Qwen/Qwen3-8B") -> tuple[dict, int]:
    """Read tensor headers only; loading weights is excluded from task budgets."""
    path = Path(model_path).resolve()
    profile = validate_model(model, revision, revision)
    if path.name != revision:
        raise ValueError("model_path must be the pinned Hugging Face snapshot directory")
    config = json.loads((path / "config.json").read_text())
    hybrid = profile.get("backend") == "transformers_hybrid"
    expected = {
        "architectures": ["Qwen3ForCausalLM"],
        "model_type": "qwen3",
        "num_key_value_heads": 8,
        "head_dim": 128,
        "vocab_size": 151936,
        "hidden_act": "silu",
        "attention_bias": False,
        "tie_word_embeddings": False,
        "rope_scaling": None,
        "rope_theta": 1000000,
        "max_position_embeddings": 40960,
        "sliding_window": None,
        "use_sliding_window": False,
        "rms_norm_eps": 1e-6,
        "torch_dtype": "bfloat16",
        **profile["dimensions"],
        **profile.get("architecture", {}),
    }
    if hybrid:
        if config.get("architectures") != ["Qwen3_5ForConditionalGeneration"]:
            raise ValueError("expected the pinned Qwen3.5 hybrid architecture")
        config = config["text_config"]
        expected = {
            **profile["dimensions"],
            "model_type": "qwen3_5_text",
            "dtype": "bfloat16",
            "head_dim": 256,
            "num_key_value_heads": 4,
            "vocab_size": 248320,
            "linear_num_key_heads": 16,
            "linear_num_value_heads": 32,
            "linear_key_head_dim": 128,
            "linear_value_head_dim": 128,
            "linear_conv_kernel_dim": 4,
            "layer_types": ["linear_attention"] * 3 + ["full_attention"],
        }
        expected["layer_types"] *= 8
    if any(key not in config or config[key] != value for key, value in expected.items()):
        raise ValueError(f"expected the pinned {model} architecture and BF16 configuration")
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
            if tensor.get("dtype") not in ({"BF16", "F32"} if hybrid else {"BF16"}):
                raise ValueError("pinned model weights must be BF16")
            size = 1
            for dimension in tensor["shape"]:
                size *= dimension
            parameters += size
    if parameters != profile["parameters"]:
        raise ValueError(f"parameter count does not match the pinned {model} weights")
    return config, parameters
