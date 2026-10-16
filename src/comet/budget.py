from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from typing import Callable

from comet.clocks import monotonic
from comet.errors import BudgetExpired


class Budget:
    def __init__(self, seconds: float, consumed: float = 0, *, clock: Callable = monotonic):
        if seconds <= 0 or consumed < 0:
            raise ValueError("Budget must be positive and consumed time nonnegative")
        self.seconds, self.consumed, self.clock = seconds, consumed, clock
        self.started = clock()
        self.timings: dict[str, float] = {}

    @property
    def elapsed(self) -> float:
        return self.consumed + self.clock() - self.started

    @property
    def remaining(self) -> float:
        return max(0.0, self.seconds - self.elapsed)

    @property
    def deadline(self) -> float:
        return self.started + self.seconds - self.consumed

    def check(self) -> None:
        if self.remaining <= 0:
            raise BudgetExpired("Shared task/configuration wall-clock budget expired")

    @contextmanager
    def charge(self, component: str, *, interrupt: bool = True):
        self.check()
        start = self.clock()
        use_signal = interrupt and threading.current_thread() is threading.main_thread()
        previous = None
        if use_signal:
            previous = signal.getsignal(signal.SIGALRM)
            if signal.getitimer(signal.ITIMER_REAL)[0]:
                raise RuntimeError("Cannot replace an existing deadline timer")

            def expired(_signum, _frame):
                raise BudgetExpired(f"Budget expired during {component}")

            signal.signal(signal.SIGALRM, expired)
            signal.setitimer(signal.ITIMER_REAL, self.remaining)
        try:
            yield
            self.check()
        finally:
            if use_signal:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
            self.timings[component] = self.timings.get(component, 0) + self.clock() - start
