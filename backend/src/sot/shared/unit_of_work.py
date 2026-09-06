from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class TransactionContext(Protocol):
    """Opaque transaction marker; application code may only pass it through."""


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[TransactionContext]: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


__all__ = ["TransactionContext", "UnitOfWork", "UnitOfWorkFactory"]
