import time


def monotonic() -> float:
    """AppWorld freezes Python's time functions; resource accounting must remain real."""
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def wall_time() -> float:
    return time.clock_gettime(time.CLOCK_REALTIME)
