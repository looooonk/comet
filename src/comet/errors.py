class BudgetExpired(TimeoutError):
    """The shared task budget has expired."""


class MemoryCapExceeded(MemoryError):
    """An operation cannot stay within the experiment's memory cap."""


class UnsupportedPath(RuntimeError):
    """An integration cannot preserve the required experimental semantics."""
