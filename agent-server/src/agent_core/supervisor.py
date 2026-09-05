from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import Field
from pydantic_ai import CancellationToken
from pydantic_settings import BaseSettings, SettingsConfigDict

type RunExecution = Callable[[CancellationToken], Awaitable[None]]


class RunCapacityExceeded(Exception):
    pass


class ExecutionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_RUN_", extra="ignore")

    capacity: int = Field(default=32, gt=0)
    shutdown_timeout_seconds: float = Field(default=35.0, gt=0)
    lease_ttl_seconds: float = Field(default=60.0, gt=0)


@dataclass(slots=True)
class _OwnedRun:
    token: CancellationToken
    task: asyncio.Task[None]


class RunSupervisor:
    def __init__(self, *, capacity: int = 32) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._runs: dict[str, _OwnedRun] = {}

    @property
    def active(self) -> int:
        return len(self._runs)

    def contains(self, run_id: str) -> bool:
        return run_id in self._runs

    def start(self, run_id: str, execute: RunExecution) -> bool:
        if run_id in self._runs:
            return False
        if len(self._runs) >= self._capacity:
            raise RunCapacityExceeded

        token = CancellationToken()

        async def owned() -> None:
            try:
                await execute(token)
            finally:
                self._runs.pop(run_id, None)

        task = asyncio.create_task(owned(), name=f"agent-run:{run_id}")
        self._runs[run_id] = _OwnedRun(token=token, task=task)
        return True

    def abort(self, run_id: str) -> bool:
        owned = self._runs.get(run_id)
        if owned is None:
            return False
        owned.token.cancel()
        owned.task.cancel()
        return True

    async def drain(self, *, timeout: float) -> None:
        owned_runs = list(self._runs.values())
        if not owned_runs:
            return
        tasks = [owned.task for owned in owned_runs]
        _done, pending = await asyncio.wait(tasks, timeout=timeout)
        for owned in owned_runs:
            if owned.task in pending:
                owned.token.cancel()
                owned.task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "ExecutionSettings",
    "RunCapacityExceeded",
    "RunExecution",
    "RunSupervisor",
]
