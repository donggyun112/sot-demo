from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from datetime import timedelta
from hashlib import sha256

import pytest

from sot.sharing.application import ReadPublicBundle
from sot.sharing.domain import ShareLinkNotFound
from tests.session.test_application import NOW
from tests.sharing.test_share_link import create_handler, revoke_handler, shared_fixture


@pytest.mark.asyncio
async def test_anonymous_read_is_frozen_public_snapshot_without_source_access() -> None:
    store, actor, workspace_id, bundle_id = await shared_fixture()
    result = await create_handler(store).execute(actor, workspace_id, bundle_id)
    store.names[actor.user_id] = "Changed profile"
    store.source.bundles.clear()
    store.source.sessions.clear()
    store.source.members.clear()
    store.source.workspace_members.clear()
    store.source.reads.clear()
    public = await ReadPublicBundle(store, lambda: store, store).execute(
        result.raw_token
    )
    assert store.last_lookup == sha256(result.raw_token.encode()).digest()
    assert store.source.reads == []
    assert public.bundle_id == bundle_id
    assert public.title == "Public"
    assert [item.content for item in public.items] == ["Q", "private"]
    assert public.attribution.author_display_name == "Publisher"
    assert set(asdict(public)) == {"bundle_id", "title", "items", "attribution"}
    assert set(asdict(public.items[0])) == {
        "source_ids",
        "role",
        "content",
        "provenance",
    }
    assert set(asdict(public.attribution)) == {
        "title",
        "author_display_name",
        "published_at",
    }
    with pytest.raises(FrozenInstanceError):
        public.attribution.author_display_name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        public.items[0].content = "changed"  # type: ignore[misc]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "revoked", "expired", "empty"])
async def test_invalid_capability_cannot_read_snapshot(state: str) -> None:
    store, actor, workspace_id, bundle_id = await shared_fixture()
    result = await create_handler(store).execute(
        actor, workspace_id, bundle_id, expires_at=NOW + timedelta(days=1)
    )
    if state == "revoked":
        await revoke_handler(store).execute(actor, workspace_id, result.link_id)
    if state == "expired":
        store.now_value = NOW + timedelta(days=1)
    token = {"missing": "unknown", "empty": ""}.get(state, result.raw_token)
    with pytest.raises(ShareLinkNotFound):
        await ReadPublicBundle(store, lambda: store, store).execute(token)
