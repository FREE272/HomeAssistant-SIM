"""Load actual calendar/sensor platforms and exercise calendar options."""

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.sim_waste_collection_schedule.api import (
    Collection,
    Route,
    SimConnectionError,
)
from custom_components.sim_waste_collection_schedule.calendar import SimCalendar
from custom_components.sim_waste_collection_schedule.const import DOMAIN

from .conftest import ROUTE, TODAY


def entity_id(hass, platform, key):
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{ROUTE.unique_id}_{key}"
    )


async def test_sensors_and_calendar_load(hass, setup_entry):
    entry = await setup_entry()
    assert (
        len(
            [
                s
                for s in hass.states.async_all("sensor")
                if er.async_get(hass).async_get(s.entity_id).config_entry_id
                == entry.entry_id
            ]
        )
        == 8
    )
    assert (
        hass.states.get(entity_id(hass, "sensor", "next_collection")).state
        == "2026-10-10"
    )
    assert hass.states.get(entity_id(hass, "sensor", "days_until")).state == "0"
    assert (
        hass.states.get(entity_id(hass, "sensor", "glass_and_metal")).state
        == "2026-11-17"
    )
    assert hass.states.get(entity_id(hass, "calendar", "calendar")) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_calendar_toggle_off_on_off(hass, setup_entry):
    entry = await setup_entry(calendar=False)
    calendar_id = entity_id(hass, "calendar", "calendar")
    registry = er.async_get(hass)
    assert (
        registry.async_get(calendar_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert hass.states.get(calendar_id) is None
    options = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            "enable_calendar": True,
            "full_calendar_names": True,
            "full_sensor_names": True,
            "full_sensor_values": True,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert registry.async_get(calendar_id).disabled_by is None
    assert hass.states.get(calendar_id) is not None
    options = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            "enable_calendar": False,
            "full_calendar_names": True,
            "full_sensor_names": True,
            "full_sensor_values": True,
        },
    )
    await hass.async_block_till_done()
    assert (
        registry.async_get(calendar_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert hass.states.get(calendar_id) is None
    assert (
        hass.states.get(entity_id(hass, "sensor", "next_collection")).state
        == "2026-10-10"
    )


async def test_calendar_day_boundaries_and_cached_ranges(hass, setup_entry, sim_api):
    entry = await setup_entry()
    calendar = SimCalendar(entry.runtime_data, "calendar")
    dt_util.set_default_time_zone(ZoneInfo("Europe/Oslo"))
    start = datetime(2026, 10, 10, 12, tzinfo=ZoneInfo("Europe/Oslo"))
    end = datetime(2026, 10, 13, 0, tzinfo=ZoneInfo("Europe/Oslo"))
    initial_calls = sim_api[1].call_count
    events = await calendar.async_get_events(hass, start, end)
    assert len(events) == 1  # Today's event overlaps; Oct 13 at midnight is excluded.
    assert not isinstance(events[0].start, datetime)
    assert events[0].end == date(2026, 10, 11)
    assert sim_api[1].call_count == initial_calls
    assert "6:00 a.m." in events[0].description
    events = await calendar.async_get_events(hass, end, end + timedelta(days=1))
    assert "Collection day changed" in events[0].description
    assert "Flytta tømmedagen fordi me hadde lyst." in events[0].description


async def test_empty_schedule_is_unknown_not_zero_days(hass, setup_entry, sim_api):
    sim_api[1].return_value = ()
    entry = await setup_entry()
    assert hass.states.get(entity_id(hass, "sensor", "days_until")).state == "unknown"
    assert SimCalendar(entry.runtime_data, "calendar").event is None


async def test_route_changes_and_api_failure(hass, setup_entry, sim_api):
    entry = await setup_entry()
    coordinator = entry.runtime_data
    sim_api[0].return_value = [Route(99, ROUTE.address, ROUTE.municipality, "Ny rute")]
    await coordinator.async_refresh()
    assert coordinator.route.route_id == 99
    assert sim_api[1].call_args.args[0] == 99
    sim_api[1].side_effect = SimConnectionError("offline")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    next_collection = hass.states.get(entity_id(hass, "sensor", "next_collection"))
    assert next_collection.state == "2026-10-10"
    assert next_collection.attributes["schedule_stale"] is True
    sim_api[1].side_effect = None
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_calendar_fetches_and_caches_outside_sensor_window(
    hass, setup_entry, sim_api
):
    entry = await setup_entry()
    coordinator = entry.runtime_data
    start, end = date(2028, 1, 1), date(2028, 1, 31)
    sim_api[1].return_value = (Collection(date(2028, 1, 4), "Papir/plast"),)
    count = sim_api[1].call_count
    assert (
        await coordinator.async_calendar_collections(start, end)
        == sim_api[1].return_value
    )
    assert (
        await coordinator.async_calendar_collections(start, end)
        == sim_api[1].return_value
    )
    assert sim_api[1].call_count == count + 1


async def test_failed_future_calendar_fetch_notifies_and_success_dismisses(
    hass, setup_entry, sim_api
):
    entry = await setup_entry()
    coordinator = entry.runtime_data
    start, end = date(2028, 1, 1), date(2028, 1, 31)
    sim_api[1].side_effect = SimConnectionError("offline")

    with (
        patch(
            "custom_components.sim_waste_collection_schedule.coordinator."
            "persistent_notification.async_create"
        ) as create_notification,
        patch(
            "custom_components.sim_waste_collection_schedule.coordinator."
            "persistent_notification.async_dismiss"
        ) as dismiss_notification,
    ):
        with pytest.raises(SimConnectionError):
            await coordinator.async_calendar_collections(start, end)

        create_notification.assert_called_once()
        message = create_notification.call_args.args[1]
        assert coordinator.window_end.isoformat() in message
        assert "Testveg 12" in message

        sim_api[1].side_effect = None
        sim_api[1].return_value = (Collection(start, "Papir"),)
        await coordinator.async_calendar_collections(start, end)

        dismiss_notification.assert_called_once_with(
            hass, coordinator._future_calendar_notification_id
        )


async def test_midnight_recalculates_without_network(
    hass, setup_entry, sim_api, freezer
):
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    freezer.move_to(datetime(2026, 10, 10, 23, 59, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    with patch(
        "custom_components.sim_waste_collection_schedule.coordinator.sim_today",
        return_value=TODAY,
    ):
        entry = await setup_entry()
    count = sim_api[1].call_count
    next_day = date(2026, 10, 11)
    # Simulate HA's date callback with the authoritative SIM date advanced.
    with patch(
        "custom_components.sim_waste_collection_schedule.coordinator.sim_today",
        return_value=next_day,
    ):
        async_fire_time_changed(
            hass, datetime(2026, 10, 11, 0, 0, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        )
        await hass.async_block_till_done()
    assert entry.runtime_data.data.today == next_day
    assert hass.states.get(entity_id(hass, "sensor", "days_until")).state == "2"
    assert sim_api[1].call_count == count
