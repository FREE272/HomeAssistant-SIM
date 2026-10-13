"""Real Home Assistant fixtures and a deterministic SIM schedule."""

from datetime import date
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sim_waste_collection_schedule.api import Collection, Route
from custom_components.sim_waste_collection_schedule.const import DOMAIN

ROUTE = Route(49, "Testveg 12", "STORD", "Tysdag B")
TODAY = date(2026, 10, 10)
COLLECTIONS = (
    Collection(date(2026, 10, 10), "Rest/bio"),
    Collection(date(2026, 10, 13), "Rest/bio", True, "Flyttet hentedag"),
    Collection(date(2026, 11, 3), "Papir/plast"),
    Collection(date(2026, 11, 17), "Glas/metall B"),
)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in the real HA test harness."""


@pytest.fixture
def sim_api(freezer):
    freezer.move_to("2026-10-10T12:00:00+00:00")
    with (
        patch(
            "custom_components.sim_waste_collection_schedule.api.SimApi.search_routes",
            return_value=[ROUTE],
        ) as search,
        patch(
            "custom_components.sim_waste_collection_schedule.api.SimApi.collections",
            return_value=COLLECTIONS,
        ) as collections,
    ):
        yield search, collections


@pytest.fixture
async def setup_entry(hass, sim_api):
    async def setup(calendar=True):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Testveg 12, STORD",
            unique_id=ROUTE.unique_id,
            data={**ROUTE.as_entry_data(), "enable_calendar": calendar},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return setup
