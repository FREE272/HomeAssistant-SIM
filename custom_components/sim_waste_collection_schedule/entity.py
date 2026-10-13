"""Base entity shared by SIM sensors and the calendar."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import SimCoordinator


class SimEntity(CoordinatorEntity[SimCoordinator]):
    """Represent an address rather than a physical waste bin."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SimCoordinator, key: str) -> None:
        super().__init__(coordinator)
        route = coordinator.route
        self._attr_unique_id = f"{route.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, route.unique_id)},
            name=f"SIM {route.address}, {route.municipality}",
            manufacturer="SIM",
            model=NAME,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://sim.as/",
        )

    @property
    def available(self) -> bool:
        """Keep the cached schedule available after a failed refresh.

        DataUpdateCoordinator retains its previous data on UpdateFailed; the
        stale attribute below lets automations distinguish it from fresh data.
        """
        return self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose whether the cached schedule needs a successful refresh."""
        updated = self.coordinator.last_successful_update
        return {
            "schedule_stale": not self.coordinator.last_update_success,
            "schedule_last_updated": updated.isoformat() if updated else None,
        }
