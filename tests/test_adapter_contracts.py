"""
Filename: test_adapter_contracts.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Service contract checks for remote identities, monitoring and search commands.
"""

import httpx
import pytest

from addarr.adapters import ArrClient
from addarr.domain import ServiceConfig, ServiceError


@pytest.mark.parametrize("code", [200, 201, 202, 204])
async def test_all_success_statuses(store, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code))) as http:
        client = ArrClient(ServiceConfig.model_validate(store.setting("service:radarr")), store, http)
        assert await client.call("PUT", "test") is None


async def test_malformed_service_response(store):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not-json"))
    ) as http:
        client = ArrClient(ServiceConfig.model_validate(store.setting("service:radarr")), store, http)
        with pytest.raises(ServiceError, match="invalid JSON"):
            await client.call("GET", "test")


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [("system/status", []), ("qualityprofile", {"error": "invalid"}), ("rootfolder", [{}])],
)
async def test_malformed_choices_raise_service_error(store, fake, endpoint, payload):
    def handler(request):
        if request.url.path.endswith("/" + endpoint):
            return httpx.Response(200, json=payload)
        return fake.handle(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ArrClient(ServiceConfig.model_validate(store.setting("service:radarr")), store, http)
        with pytest.raises(ServiceError):
            await client.capabilities()


async def test_base_path_query_encoding_and_basic_auth(store):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    config = ServiceConfig.model_validate(
        dict(
            kind="radarr",
            url="http://localhost:7878/arr/radarr/",
            api_key="key",
            username="user",
            password="password",
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ArrClient(config, store, http)
        await client.search("A & B / 漢字")
    assert seen[0].url.path == "/arr/radarr/api/v3/movie/lookup"
    assert seen[0].url.params["term"] == "A & B / 漢字"
    assert seen[0].headers["Authorization"].startswith("Basic ")
    assert seen[0].headers["X-Api-Key"] == "key"
