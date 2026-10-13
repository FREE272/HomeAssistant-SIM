"""Live smoke test for SIM's address and collection API."""

from datetime import date, timedelta
import os

import aiohttp
import pytest

from custom_components.sim_waste_collection_schedule.api import SimApi


LIVE_ADDRESS = os.environ.get("SIM_LIVE_ADDRESS")
LIVE_MUNICIPALITY = os.environ.get("SIM_LIVE_MUNICIPALITY")


@pytest.mark.skipif(
    not LIVE_ADDRESS or not LIVE_MUNICIPALITY,
    reason="Set SIM_LIVE_ADDRESS and SIM_LIVE_MUNICIPALITY for a live API test",
)
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
