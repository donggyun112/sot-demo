import httpx
import pytest

from service_auth.jwks import HttpxJwksFetcher, JwksFetchError

MAX_JWKS_BYTES = 256 * 1024


@pytest.mark.asyncio
async def test_fetcher_returns_200_body_with_bounded_request_settings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == httpx.URL("https://issuer.example/jwks")
        assert request.extensions["timeout"] == {
            "connect": 2.0,
            "read": 3.0,
            "write": 3.0,
            "pool": 3.0,
        }
        return httpx.Response(200, content=b'{"keys":[]}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        assert await fetcher.fetch() == b'{"keys":[]}'


@pytest.mark.asyncio
async def test_fetcher_never_follows_redirects_from_injected_client() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.host == "issuer.example":
            return httpx.Response(
                302, headers={"location": "https://evil.example/jwks"}
            )
        return httpx.Response(200, content=b"attacker-controlled")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        with pytest.raises(JwksFetchError, match="^jwks_fetch_failed$"):
            await fetcher.fetch()

    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 500])
async def test_fetcher_rejects_non_200_status(status_code: int) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(status_code))

    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        with pytest.raises(JwksFetchError, match="^jwks_fetch_failed$"):
            await fetcher.fetch()


@pytest.mark.asyncio
async def test_fetcher_maps_transport_timeout_to_bounded_error() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret endpoint detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        with pytest.raises(JwksFetchError, match="^jwks_fetch_failed$") as caught:
            await fetcher.fetch()

    assert "secret endpoint detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_fetcher_accepts_exactly_256_kib() -> None:
    body = b"a" * MAX_JWKS_BYTES
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=body))

    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        assert await fetcher.fetch() == body


@pytest.mark.asyncio
async def test_fetcher_rejects_262145_streamed_bytes() -> None:
    body = b"a" * (MAX_JWKS_BYTES + 1)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=body))

    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

        with pytest.raises(JwksFetchError, match="^jwks_fetch_failed$"):
            await fetcher.fetch()


def test_fetcher_rejects_non_https_uri_before_network_access() -> None:
    with pytest.raises(ValueError, match="^HTTPS jwks_uri is required$"):
        HttpxJwksFetcher("http://issuer.example/jwks")


@pytest.mark.asyncio
async def test_close_closes_an_internally_created_client() -> None:
    fetcher = HttpxJwksFetcher("https://issuer.example/jwks")

    await fetcher.close()

    assert fetcher._client.is_closed


@pytest.mark.asyncio
async def test_close_does_not_close_an_injected_client() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200))
    client = httpx.AsyncClient(transport=transport)
    fetcher = HttpxJwksFetcher("https://issuer.example/jwks", client=client)

    await fetcher.close()
    response = await client.get("https://issuer.example/still-open")

    assert response.status_code == 200
    await client.aclose()
