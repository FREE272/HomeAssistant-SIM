"""SIM waste collection schedule using its direct JSON API."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_get_translations

from .api import SimApi
from .const import DOMAIN
from .coordinator import SimCoordinator

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]
SimConfigEntry = ConfigEntry[SimCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SimConfigEntry) -> bool:
    """Fetch once before setting up platforms; retry setup on API failures."""
    translations = await async_get_translations(
        hass, hass.config.language, "entity", integrations=(DOMAIN,)
    )
    # Common strings are used by both calendar events and coordinator notifications.
    translations.update(
        await async_get_translations(
            hass, hass.config.language, "common", integrations=(DOMAIN,)
        )
    )
    coordinator = SimCoordinator(
        hass, entry, SimApi(async_get_clientsession(hass)), translations
    )
    await coordinator.async_load_notification_state()
    # Fetch immediately. Home Assistant retries ConfigEntryNotReady with
    # exponential backoff (currently 5 seconds up to 10 minutes); no custom
    # startup retry timer should wait for the regular 24-hour poll.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_midnight_updates()
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    # Only forward platforms after the initial schedule has been populated.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SimConfigEntry) -> bool:
    """Unload entities, polling and the registered date-change listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: SimConfigEntry) -> None:
    """Apply changed integration options."""
    await hass.config_entries.async_reload(entry.entry_id)
