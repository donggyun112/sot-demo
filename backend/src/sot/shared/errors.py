from __future__ import annotations


class SOTError(Exception):
    """A domain-safe error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFound(SOTError):
    pass


class Forbidden(SOTError):
    pass


class Conflict(SOTError):
    pass


class InvalidInput(SOTError):
    pass


__all__ = [
    "Conflict",
    "Forbidden",
    "InvalidInput",
    "NotFound",
    "SOTError",
]
