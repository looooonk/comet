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

    def to_dict(self) -> dict:
        return asdict(self)


def decide(
    policy: str, thresholds: Triggers, context_tokens: int, tool_calls: int, rebuilds: int
) -> Decision:
    if policy not in {"never", "fixed", "dynamic"}:
        raise ValueError(f"Unknown recovery policy: {policy}")
    if min(context_tokens, tool_calls, rebuilds) < 0:
        raise ValueError("Recovery counters cannot be negative")
    if policy == "never" or rebuilds:
        triggered, reason = False, "disabled" if policy == "never" else "already_rebuilt"
    elif policy == "fixed":
        triggered = tool_calls >= thresholds.fixed_tool_calls
        reason = "threshold_met" if triggered else "below_threshold"
    else:
        checks = (
            context_tokens >= thresholds.dynamic_context_tokens,
            tool_calls >= thresholds.dynamic_tool_calls,
        )
        triggered = all(checks) if thresholds.dynamic_rule == "and" else any(checks)
        reason = "threshold_met" if triggered else "below_threshold"
    return Decision(policy, context_tokens, tool_calls, rebuilds, triggered, reason)
