"""Disposable browser harness: real composition, Google boundary and model doubles only."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Mapping
from uuid import NAMESPACE_URL, uuid5

import psycopg
import uvicorn
from pydantic_ai.messages import ModelMessage, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from sot.bootstrap.app import build_app
from sot.bootstrap.migrate import MIGRATIONS_PATH, run_migrations
from sot.bootstrap.settings import Settings
from tests.postgres import disposable_database

GOOGLE_CLIENT_ID = "sot-browser-test-client"


def fixture_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://sot.test/{name}"))


class StaticGoogleTokenVerifier:
    async def verify(self, credential: str, audience: str) -> Mapping[str, object]:
        if audience != GOOGLE_CLIENT_ID or credential not in {
            "google-test-alice",
            "google-test-bob",
        }:
            raise ValueError("Unknown test Google credential")
        name = credential.removeprefix("google-test-")
        now = int(time.time())
        return {
            "iss": "https://accounts.google.com",
            "aud": audience,
            "sub": f"test-{name}",
            "email": f"{name}@example.test",
            "email_verified": True,
            "name": name.title(),
            "iat": now,
            "exp": now + 3600,
        }


async def seed_browser_fixtures(database_url: str) -> None:
    """Conflict-safe test data; never called by production startup/migrations."""
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        for name in ("alice", "bob"):
            user, workspace, document, revision = (
                fixture_id(f"{name}/{kind}")
                for kind in ("user", "workspace", "document", "revision")
            )
            await connection.execute(
                "INSERT INTO sot.sot_user VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (user, f"{name}@example.test", name.title()),
            )
            await connection.execute(
                "INSERT INTO sot.sot_user_identity VALUES (%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (
                    fixture_id(f"{name}/identity"),
                    user,
                    "https://accounts.google.com",
                    f"test-{name}",
                ),
            )
            await connection.execute(
                "INSERT INTO sot.sot_workspace VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (workspace, f"{name.title()} Workspace"),
            )
            await connection.execute(
                "INSERT INTO sot.sot_workspace_member VALUES (%s,%s,'owner') "
                "ON CONFLICT DO NOTHING",
                (workspace, user),
            )
            await connection.execute(
                "INSERT INTO sot.sot_document "
                "(id,workspace_id,created_by,title,version,current_revision_id) "
                "VALUES (%s,%s,%s,%s,1,%s) ON CONFLICT DO NOTHING",
                (document, workspace, user, f"{name.title()} Policy", revision),
            )
            await connection.execute(
                "INSERT INTO sot.sot_document_revision "
                "(id,workspace_id,document_id,number,content,created_by,created_at) "
                "VALUES (%s,%s,%s,1,'Initial agreement',%s,now()) ON CONFLICT DO NOTHING",
                (revision, workspace, document, user),
            )
        # Workspace membership permits proposal decisions, never private Session reads.
        await connection.execute(
            "INSERT INTO sot.sot_workspace_member VALUES (%s,%s,'member') "
            "ON CONFLICT DO NOTHING",
            (fixture_id("alice/workspace"), fixture_id("bob/user")),
        )


def browser_model() -> FunctionModel:
    loser_ready, winner_committed = asyncio.Event(), asyncio.Event()

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        prompt = next(
            part.content
            for message in reversed(messages)
            for part in reversed(message.parts)
            if isinstance(part, UserPromptPart)
        )
        if prompt in {"race winner", "race loser"}:
            if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                winner_committed.set()
                yield "Winner committed"
                return
            if prompt == "race loser":
                loser_ready.set()
                await asyncio.wait_for(winner_committed.wait(), timeout=15)
            else:
                await asyncio.wait_for(loser_ready.wait(), timeout=15)
            yield {
                0: DeltaToolCall(
                    "sot_update",
                    json.dumps(
                        {"edits": [{"find": "", "replace": f"{prompt} proposal"}]}
                    ),
                    tool_call_id=str(prompt),
                )
            }
            return
        if prompt == "what does the document say?":
            # Answered from the document the run was given, which is the whole
            # point of giving it: the agent used to say it could not read one.
            body = str(info.instructions).split("<<<DOCUMENT\n", 1)[-1]
            yield "The document says: " + body.split("\nDOCUMENT>>>", 1)[0]
            return
        yield "Public reasoning: "
        yield "isolate each user's work."

    return FunctionModel(stream_function=stream)


async def main() -> None:
    settings = Settings()
    if settings.environment != "test":
        raise RuntimeError("The browser harness requires SOT_ENVIRONMENT=test")
    async with disposable_database() as database_url:
        await run_migrations(database_url, MIGRATIONS_PATH)
        await seed_browser_fixtures(database_url)
        application = build_app(
            settings.model_copy(
                update={
                    "database_url": database_url,
                    "google_client_id": GOOGLE_CLIENT_ID,
                    "models": ("test",),
                    "development_auth": False,
                }
            ),
            google_token_verifier=StaticGoogleTokenVerifier(),
        )
        with application.state.canonical_agent.override(model=browser_model()):
            await uvicorn.Server(
                uvicorn.Config(
                    application,
                    host="127.0.0.1",
                    port=int(os.environ.get("SOT_E2E_BACKEND_PORT", "18001")),
                    log_level="warning",
                    access_log=False,
                )
            ).serve()


if __name__ == "__main__":
    asyncio.run(main())
