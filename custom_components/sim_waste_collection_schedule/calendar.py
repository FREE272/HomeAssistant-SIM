"""Read-only all-day calendar with actual SIM collection days."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SimConfigEntry
from .api import Collection, SimApiError
from .const import CONF_ENABLE_CALENDAR, DOMAIN
from .entity import SimEntity

if TYPE_CHECKING:
    from .coordinator import SimCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    enabled = entry.options.get(
        CONF_ENABLE_CALENDAR, entry.data.get(CONF_ENABLE_CALENDAR, True)
    )
    registry = er.async_get(hass)
    unique_id = f"{entry.runtime_data.route.unique_id}_calendar"
    if entity_id := registry.async_get_entity_id("calendar", DOMAIN, unique_id):
        registered = registry.async_get(entity_id)
        if registered is not None and registered.disabled_by in (
            None,
            er.RegistryEntryDisabler.INTEGRATION,
        ):
            registry.async_update_entity(
                entity_id,
                disabled_by=None if enabled else er.RegistryEntryDisabler.INTEGRATION,
            )
            if not enabled:
                # Unloading can leave an unavailable restored state behind.
                hass.states.async_remove(entity_id)
    entity = SimCalendar(entry.runtime_data, "calendar")
    entity._attr_entity_registry_enabled_default = enabled
    async_add_entities([entity])


class SimCalendar(SimEntity, CalendarEntity):
    """Expose collections to calendar cards and calendar-triggered automations."""

    _attr_has_entity_name = False
    _attr_translation_key = None
    _attr_icon = "mdi:calendar"

    def __init__(self, coordinator: SimCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        name_template = coordinator.translations.get(
            f"component.{DOMAIN}.entity.calendar.collections.name",
            "Schedule",
        )
        self._attr_name = name_template.format(
            address=coordinator.route.address,
            municipality=coordinator.route.municipality.title(),
        )

    def _event(self, item: Collection) -> CalendarEvent:
        translations = self.coordinator.translations
        description = translations.get(
            f"component.{DOMAIN}.common.calendar_event_instructions",
            "Remember to put the bin out by 6:00 a.m. on collection day. "
            "Remember to bring the bin back home after collection.",
        )
        if item.exception:
            changed_date = translations.get(
                f"component.{DOMAIN}.common.calendar_event_changed_date",
                "Collection day changed. Use the date shown in the calendar.",
            )
            description += f" {changed_date}"
        if item.comment:
            description += f" {item.comment}"
        return CalendarEvent(
            start=item.day,
            end=item.day + timedelta(days=1),
            summary=item.translated_label(self.coordinator.calendar_waste_names),
            description=description,
            location=(
                f"{self.coordinator.route.address}, "
                f"{self.coordinator.route.municipality}"
            ),
        )

    @property
    def event(self) -> CalendarEvent | None:
        item = self.coordinator.data.next_collection()
        return self._event(item) if item else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        # CalendarEvent dates are interpreted in HA's configured timezone.
        local_start, local_end = (
            dt_util.as_local(start_date),
            dt_util.as_local(end_date),
        )
        if local_end <= local_start:
            return []
        try:
            records = await self.coordinator.async_calendar_collections(
                local_start.date(), local_end.date()
            )
        except SimApiError as err:
            raise HomeAssistantError("Unable to fetch SIM calendar") from err
        return [
            self._event(item)
            for item in records
            if dt_util.start_of_local_day(item.day) < local_end
            and dt_util.start_of_local_day(item.day + timedelta(days=1)) > local_start
        ]
