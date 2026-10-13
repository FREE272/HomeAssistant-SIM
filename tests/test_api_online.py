"""Live smoke test for SIM's address and collection API."""

import os
import socket
from datetime import date, timedelta
from urllib.parse import urlsplit

import aiohttp
import pytest
from pytest_socket import enable_socket, socket_allow_hosts

from custom_components.sim_waste_collection_schedule.api import SimApi
from custom_components.sim_waste_collection_schedule.const import API_BASE

LIVE_ADDRESS = os.environ.get("SIM_LIVE_ADDRESS")
LIVE_MUNICIPALITY = os.environ.get("SIM_LIVE_MUNICIPALITY")
_REAL_GETADDRINFO = socket.getaddrinfo


@pytest.fixture
def allow_sim_api_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow the smoke test to connect only to SIM's API host."""
    host = urlsplit(API_BASE).hostname
    if host is None:
        raise RuntimeError("SIM API URL has no hostname")

    def getaddrinfo_for_sim(
        queried_host: str | None, *args: object, **kwargs: object
    ) -> object:
        if queried_host != host:
            raise socket.gaierror("DNS lookups are restricted to the SIM API host")
        return _REAL_GETADDRINFO(queried_host, *args, **kwargs)

    enable_socket()
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo_for_sim)
    socket_allow_hosts([host])


@pytest.mark.skipif(
    not LIVE_ADDRESS or not LIVE_MUNICIPALITY,
    reason="Set SIM_LIVE_ADDRESS and SIM_LIVE_MUNICIPALITY for a live API test",
)
@pytest.mark.usefixtures("allow_sim_api_network")
async def test_live_api_returns_address_and_collection_data():
    """Check both live endpoints using a configured residential address."""
    async with aiohttp.ClientSession() as session:
        api = SimApi(session)
        routes = await api.search_routes(LIVE_ADDRESS, LIVE_MUNICIPALITY)

        assert routes, "SIM did not return a route for the configured test address"

        today = date.today()
        collections = await api.collections(
            routes[0].route_id,
            today,
            today + timedelta(days=180),
        )
        assert collections, "SIM returned no upcoming collections for the test route"
