import asyncio

import pytest
from pydantic import ValidationError
from pydantic_ai import CancellationToken

from agent_core.supervisor import (
    ExecutionSettings,
    RunCapacityExceeded,
    RunSupervisor,
)

RUN_ID = "019504e8-4b7d-7a31-9c2d-123456789abc"


@pytest.mark.asyncio
async def test_supervisor_owns_one_task_until_execution_finishes() -> None:
    supervisor = RunSupervisor(capacity=2)
    release = asyncio.Event()

    async def execute(token: CancellationToken) -> None:
        assert token.cancelled is False
        await release.wait()

    assert supervisor.start(RUN_ID, execute) is True
    assert supervisor.start(RUN_ID, execute) is False
    await asyncio.sleep(0)
    assert supervisor.contains(RUN_ID)

    release.set()
    await supervisor.drain(timeout=1)

    assert not supervisor.contains(RUN_ID)


@pytest.mark.asyncio
async def test_capacity_fails_fast_without_queueing() -> None:
    supervisor = RunSupervisor(capacity=1)
    release = asyncio.Event()

    async def execute(_: CancellationToken) -> None:
        await release.wait()

    supervisor.start("run-1", execute)
    with pytest.raises(RunCapacityExceeded):
        supervisor.start("run-2", execute)

    release.set()
    await supervisor.drain(timeout=1)


@pytest.mark.asyncio
async def test_abort_cancels_the_named_task_and_token() -> None:
    supervisor = RunSupervisor(capacity=2)
    observed: list[bool] = []

    async def execute(token: CancellationToken) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            observed.append(token.cancelled)

    supervisor.start(RUN_ID, execute)
    await asyncio.sleep(0)

    assert supervisor.abort(RUN_ID) is True
    assert supervisor.abort("missing") is False
    await supervisor.drain(timeout=1)

    assert observed == [True]


@pytest.mark.asyncio
async def test_drain_timeout_cancels_pending_task_and_token() -> None:
    supervisor = RunSupervisor(capacity=1)
    observed: list[bool] = []

    async def execute(token: CancellationToken) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            observed.append(token.cancelled)

    supervisor.start(RUN_ID, execute)
    await asyncio.sleep(0)
    await supervisor.drain(timeout=0)

    assert observed == [True]
    assert not supervisor.contains(RUN_ID)


def test_execution_settings_are_positive() -> None:
    assert ExecutionSettings().capacity == 32
    assert ExecutionSettings().shutdown_timeout_seconds == 35.0

    with pytest.raises(ValidationError):
        ExecutionSettings(capacity=0)
    with pytest.raises(ValidationError):
        ExecutionSettings(shutdown_timeout_seconds=0)
