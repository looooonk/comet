from dataclasses import asdict, dataclass

from comet.config import Triggers


@dataclass(frozen=True)
class Decision:
    policy: str
    context_tokens: int
    tool_calls: int
    rebuilds: int
    triggered: bool
    reason: str
    symptoms: int | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.symptoms is None:
            del data["symptoms"]
        return data


def decide(
    policy: str,
    thresholds: Triggers,
    context_tokens: int,
    tool_calls: int,
    rebuilds: int,
    symptoms: int = 0,
) -> Decision:
    """Symptoms count this attempt's observations that contain a configured marker."""
    if policy not in {"never", "fixed", "dynamic", "symptom"}:
        raise ValueError(f"Unknown recovery policy: {policy}")
    if min(context_tokens, tool_calls, rebuilds, symptoms) < 0:
        raise ValueError("Recovery counters cannot be negative")
    if policy == "never" or rebuilds:
        triggered, reason = False, "disabled" if policy == "never" else "already_rebuilt"
    elif policy == "fixed":
        triggered = tool_calls >= thresholds.fixed_tool_calls
        reason = "threshold_met" if triggered else "below_threshold"
    elif policy == "symptom":
        triggered = symptoms > 0
        reason = "symptom_observed" if triggered else "no_symptom"
    else:
        checks = (
            context_tokens >= thresholds.dynamic_context_tokens,
            tool_calls >= thresholds.dynamic_tool_calls,
        )
        triggered = all(checks) if thresholds.dynamic_rule == "and" else any(checks)
        reason = "threshold_met" if triggered else "below_threshold"
    return Decision(
        policy,
        context_tokens,
        tool_calls,
        rebuilds,
        triggered,
        reason,
        symptoms if policy == "symptom" else None,
    )
