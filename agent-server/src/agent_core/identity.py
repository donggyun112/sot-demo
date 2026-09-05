from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    run_id: str
    conversation_id: str
    subject: str
