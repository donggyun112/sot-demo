import asyncio
from datetime import timedelta

import pytest
from conftest import BlockingFetcher, ControlledSleeper, FakeClock, FakeFetcher

from service_auth import (
    InvalidToken,
    JwksState,
    KeySourceUnavailable,
    VerificationProfile,
)
from service_auth.jwks import AsyncJwksProvider, JwksFetchError


def test_empty_readiness_is_pure_and_not_ready(
    profile: VerificationProfile,
    fake_clock: FakeClock,
) -> None:
    fetcher = FakeFetcher([])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)

    readiness = provider.readiness()

    assert readiness.ready is False
    assert readiness.state is JwksState.EMPTY
    assert readiness.age_seconds is None
    assert fetcher.calls == 0


@pytest.mark.asyncio
async def test_initial_lookup_fetches_and_installs_fresh_key_set(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)

    key = await provider.get_key("key-1", "RS256")

    assert key.kid == "key-1"
    assert fetcher.calls == 1
    assert provider.readiness().state is JwksState.FRESH
    assert provider.readiness().age_seconds == 0


@pytest.mark.asyncio
async def test_exactly_300_seconds_remains_fresh_without_fetch(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(300)

    cached = await provider.get_key("key-1", "RS256")

    assert cached is first
    assert fetcher.calls == 1
    assert provider.readiness().state is JwksState.FRESH
    assert provider.readiness().age_seconds == 300


@pytest.mark.asyncio
async def test_refreshes_and_rotates_key_after_301_seconds(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
    jwks_two: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_two])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)

    rotated = await provider.get_key("key-2", "RS256")

    assert rotated.kid == "key-2"
    assert fetcher.calls == 2
    assert provider.readiness().state is JwksState.FRESH
    assert provider.readiness().age_seconds == 0


@pytest.mark.asyncio
async def test_known_key_survives_transient_refresh_failure(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline detail")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)

    stale = await provider.get_key("key-1", "RS256")

    assert stale is first
    assert fetcher.calls == 2
    assert provider.readiness().state is JwksState.STALE_USABLE
    assert provider.readiness().age_seconds == 301


@pytest.mark.asyncio
async def test_failed_invalid_refresh_does_not_replace_valid_key_set(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, b"not-json"])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)

    stale = await provider.get_key("key-1", "RS256")

    assert stale is first
    assert provider.readiness().state is JwksState.STALE_USABLE


@pytest.mark.asyncio
async def test_exactly_900_seconds_remains_stale_usable(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(900)

    stale = await provider.get_key("key-1", "RS256")

    assert stale is first
    assert provider.readiness().ready is True
    assert provider.readiness().state is JwksState.STALE_USABLE
    assert provider.readiness().age_seconds == 900


@pytest.mark.asyncio
async def test_901_seconds_is_expired_and_failed_refresh_is_unavailable(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    fake_clock.advance(901)

    with pytest.raises(KeySourceUnavailable) as caught:
        await provider.get_key("key-1", "RS256")

    assert str(caught.value) == ""
    assert provider.readiness().ready is False
    assert provider.readiness().state is JwksState.EXPIRED
    assert provider.readiness().age_seconds == 901


@pytest.mark.asyncio
async def test_empty_cache_fetch_failure_is_unavailable(
    profile: VerificationProfile,
    fake_clock: FakeClock,
) -> None:
    fetcher = FakeFetcher([JwksFetchError("secret network detail")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)

    with pytest.raises(KeySourceUnavailable) as caught:
        await provider.get_key("key-1", "RS256")

    assert str(caught.value) == ""
    assert provider.readiness().state is JwksState.EMPTY


@pytest.mark.asyncio
async def test_fresh_unknown_key_forces_refresh_and_finds_rotation(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
    jwks_two: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_two])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")

    rotated = await provider.get_key("key-2", "RS256")

    assert rotated.kid == "key-2"
    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_successful_forced_refresh_without_unknown_key_is_invalid_token(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")

    with pytest.raises(InvalidToken, match="^kid_unknown$"):
        await provider.get_key("missing", "RS256")

    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_stale_unknown_key_during_outage_is_invalid_not_service_unavailable(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)

    with pytest.raises(InvalidToken, match="^kid_unknown$"):
        await provider.get_key("missing", "RS256")


@pytest.mark.asyncio
async def test_readiness_age_uses_monotonic_time_only(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    fake_clock.wall += timedelta(days=365)

    readiness = provider.readiness()

    assert readiness.state is JwksState.FRESH
    assert readiness.age_seconds == 0


@pytest.mark.asyncio
async def test_concurrent_empty_cache_lookups_share_one_fetch(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = BlockingFetcher(jwks_one)
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    lookups = [
        asyncio.create_task(provider.get_key("key-1", "RS256")) for _ in range(20)
    ]

    await fetcher.entered.wait()
    fetcher.release.set()
    keys = await asyncio.gather(*lookups)

    assert fetcher.calls == 1
    assert {key.kid for key in keys} == {"key-1"}


@pytest.mark.asyncio
async def test_random_unknown_kids_share_global_cooldown(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")

    for kid in ("random-1", "random-2", "random-3"):
        with pytest.raises(InvalidToken, match="^kid_unknown$"):
            await provider.get_key(kid, "RS256")

    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_unknown_key_refreshes_again_at_exact_cooldown_boundary(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
    jwks_two: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_one, jwks_two])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    await provider.get_key("key-1", "RS256")
    with pytest.raises(InvalidToken, match="^kid_unknown$"):
        await provider.get_key("missing", "RS256")
    fake_clock.advance(5)

    rotated = await provider.get_key("key-2", "RS256")

    assert rotated.kid == "key-2"
    assert fetcher.calls == 3


@pytest.mark.asyncio
async def test_failed_fetch_uses_five_second_backoff(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([JwksFetchError("offline"), jwks_one])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)

    with pytest.raises(KeySourceUnavailable):
        await provider.get_key("key-1", "RS256")
    with pytest.raises(KeySourceUnavailable):
        await provider.get_key("key-1", "RS256")
    assert fetcher.calls == 1

    fake_clock.advance(5)
    key = await provider.get_key("key-1", "RS256")

    assert key.kid == "key-1"
    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_stale_known_key_reuses_cache_during_failure_backoff(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, JwksFetchError("offline")])
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    first = await provider.get_key("key-1", "RS256")
    fake_clock.advance(301)
    assert await provider.get_key("key-1", "RS256") is first

    assert await provider.get_key("key-1", "RS256") is first
    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_start_is_idempotent_and_performs_one_immediate_refresh(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one])
    sleeper = ControlledSleeper()
    provider = AsyncJwksProvider(profile, fetcher, fake_clock, sleeper)

    await provider.start()
    await provider.start()

    assert fetcher.calls == 1
    assert await sleeper.delays.get() == 300
    await provider.close()


@pytest.mark.asyncio
async def test_initial_start_failure_remains_not_ready_and_retries_after_backoff(
    profile: VerificationProfile,
    fake_clock: FakeClock,
) -> None:
    fetcher = FakeFetcher([JwksFetchError("offline")])
    sleeper = ControlledSleeper()
    provider = AsyncJwksProvider(profile, fetcher, fake_clock, sleeper)

    await provider.start()

    assert provider.readiness().ready is False
    assert provider.readiness().state is JwksState.EMPTY
    assert await sleeper.delays.get() == 5
    await provider.close()


@pytest.mark.asyncio
async def test_maintenance_refreshes_at_freshness_deadline(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
    jwks_two: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one, jwks_two])
    sleeper = ControlledSleeper()
    provider = AsyncJwksProvider(profile, fetcher, fake_clock, sleeper)
    await provider.start()
    assert await fetcher.call_events.get() == 1
    assert await sleeper.delays.get() == 300
    fake_clock.advance(300)

    await sleeper.release_next()
    assert await fetcher.call_events.get() == 2

    assert fetcher.calls == 2
    assert provider.readiness().age_seconds == 0
    await provider.close()


@pytest.mark.asyncio
async def test_close_is_idempotent_and_closes_fetcher_once(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = FakeFetcher([jwks_one])
    sleeper = ControlledSleeper()
    provider = AsyncJwksProvider(profile, fetcher, fake_clock, sleeper)
    await provider.start()

    await provider.close()
    await provider.close()

    assert fetcher.closed is True
    assert fetcher.close_calls == 1


@pytest.mark.asyncio
async def test_close_cancels_provider_owned_refresh(
    profile: VerificationProfile,
    fake_clock: FakeClock,
    jwks_one: bytes,
) -> None:
    fetcher = BlockingFetcher(jwks_one)
    provider = AsyncJwksProvider(profile, fetcher, fake_clock)
    lookup = asyncio.create_task(provider.get_key("key-1", "RS256"))
    await fetcher.entered.wait()

    await provider.close()
    result = await asyncio.gather(lookup, return_exceptions=True)

    assert isinstance(result[0], asyncio.CancelledError)
    assert fetcher.closed is True
    assert fetcher.close_calls == 1
