from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

import rfc8785
from ag_ui.core import Context

from agent_core.identity import ExecutionIdentity


@dataclass(frozen=True, slots=True)
class AgentContextRecord:
    key: str
    value: Any
    source: str | None = None


class AgentContextSource(Protocol):
    @property
    def name(self) -> str: ...

    async def load(
        self, execution: ExecutionIdentity
    ) -> Sequence[AgentContextRecord]: ...


@dataclass(frozen=True, slots=True)
class LoadedAgentContext:
    request_context: tuple[Context, ...]
    request_state: Any
    agent_records: tuple[AgentContextRecord, ...]

    def as_untrusted_payload(self) -> dict[str, Any]:
        return {
            "request_context": [
                item.model_dump(mode="json", by_alias=True)
                for item in self.request_context
            ],
            "request_state": self.request_state,
            "agent_records": [
                {
                    "source": record.source,
                    "key": record.key,
                    "value": record.value,
                }
                for record in self.agent_records
            ],
        }


class ContextLoader:
    def __init__(self, sources: Iterable[AgentContextSource] = ()) -> None:
        registered: list[AgentContextSource] = []
        names: set[str] = set()
        for source in sources:
            if not source.name or source.name in names:
                raise ValueError(f"invalid context source name: {source.name!r}")
            names.add(source.name)
            registered.append(source)
        self._sources = tuple(registered)

    async def load(
        self,
        *,
        execution: ExecutionIdentity,
        request_context: Sequence[Context],
        request_state: Any,
    ) -> LoadedAgentContext:
        records: list[AgentContextRecord] = []
        for source in self._sources:
            loaded = await source.load(execution)
            for record in loaded:
                if record.source is not None:
                    raise ValueError("context source records must not set source")
                if not record.key:
                    raise ValueError("context record key must not be empty")
                records.append(replace(record, source=source.name))
        result = LoadedAgentContext(
            request_context=tuple(request_context),
            request_state=request_state,
            agent_records=tuple(records),
        )
        rfc8785.dumps(result.as_untrusted_payload())
        return result


__all__ = [
    "AgentContextRecord",
    "AgentContextSource",
    "ContextLoader",
    "LoadedAgentContext",
]
