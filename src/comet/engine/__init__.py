"""Native, persistent Mini-SGLang sessions with explicit experimental accounting."""

from .contracts import EngineSettings, GenerationResult, RecoveryResult, retention_target
from .native import MiniSGLangEngine


def create_engine(settings: EngineSettings):
    if settings.backend == "transformers_hybrid":
        from .hybrid import HybridEngine

        return HybridEngine(settings)
    return MiniSGLangEngine(settings)


__all__ = [
    "EngineSettings",
    "GenerationResult",
    "MiniSGLangEngine",
    "RecoveryResult",
    "retention_target",
    "create_engine",
]
