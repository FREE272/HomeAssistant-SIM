"""Real Home Assistant setup and options flow tests."""

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sim_waste_collection_schedule.api import SimConnectionError
from custom_components.sim_waste_collection_schedule.const import DOMAIN

from .conftest import ROUTE


async def test_search_select_and_calendar_toggle(hass, sim_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"address": "Testveg", "municipality": "Stord"},
    )
    assert result["step_id"] == "select"
    with patch(
        "custom_components.sim_waste_collection_schedule.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": "0"}
        )
        assert result["step_id"] == "settings"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "enable_calendar": False,
                "full_calendar_names": True,
                "full_sensor_names": False,
                "full_sensor_values": True,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"]["route_id"] == 49
    assert result["data"]["enable_calendar"] is False
    assert result["data"]["full_calendar_names"] is True
    assert result["data"]["full_sensor_names"] is False
    assert result["data"]["full_sensor_values"] is True
    assert result["result"].unique_id == ROUTE.unique_id


async def test_duplicate_address_rejected(hass, sim_api):
    MockConfigEntry(
        domain=DOMAIN, unique_id=ROUTE.unique_id, data=ROUTE.as_entry_data()
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"address": "Testveg"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "0"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_search_errors(hass, sim_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"address": "ab"}
    )
    assert result["errors"]["address"] == "invalid_address"
    sim_api[0].return_value = []
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Ukjentveg"}
    )
    assert result["errors"]["base"] == "no_addresses"
    sim_api[0].side_effect = SimConnectionError("offline")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Testveg"}
    )
    assert result["errors"]["base"] == "cannot_connect"
