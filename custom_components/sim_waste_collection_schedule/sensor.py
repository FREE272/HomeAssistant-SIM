"""Date, waste fraction and countdown sensors for SIM."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SimConfigEntry
from .coordinator import SimCoordinator
from .entity import SimEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SimSensorDescription(SensorEntityDescription):
    """Describe a sensor for a waste fraction."""

    fraction: str | None = None


SENSORS = (
    SimSensorDescription(
        key="next_collection",
        translation_key="next_collection",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-right",
    ),
    SimSensorDescription(
        key="days_until",
        translation_key="days_until",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:calendar-clock",
    ),
    SimSensorDescription(
        key="waste_types", translation_key="waste_types", icon="mdi:trash-can"
    ),
    SimSensorDescription(
        key="residual_waste",
        translation_key="residual_waste_full",
        fraction="residual_waste",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:trash-can",
    ),
    SimSensorDescription(
        key="organic_waste",
        translation_key="organic_waste_full",
        fraction="organic_waste",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:food-apple",
    ),
    SimSensorDescription(
        key="paper",
        translation_key="paper_full",
        fraction="paper",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:newspaper",
    ),
    SimSensorDescription(
        key="plastic_packaging",
        translation_key="plastic_packaging_full",
        fraction="plastic_packaging",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:recycle",
    ),
    SimSensorDescription(
        key="glass_and_metal",
        translation_key="glass_and_metal_full",
        fraction="glass_and_metal",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:bottle-soda",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    name_style = "full" if entry.runtime_data.full_sensor_names else "short"
    async_add_entities(
        SimSensor(
            entry.runtime_data,
            replace(
                description,
                translation_key=f"{description.fraction}_{name_style}",
            )
            if description.fraction
            else description,
        )
        for description in SENSORS
    )


class SimSensor(SimEntity, SensorEntity):
    """Derive state from memory; no network calls in properties."""

    entity_description: SimSensorDescription

    def __init__(
        self, coordinator: SimCoordinator, description: SimSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> date | int | str | None:
        data = self.coordinator.data
        item = data.next_collection(self.entity_description.fraction)
        if item is None:
            return None
        if self.entity_description.key == "days_until":
            return (item.day - data.today).days
        if self.entity_description.key == "waste_types":
            return item.translated_label(self.coordinator.sensor_value_waste_names)
        return item.day

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        item = data.next_collection(self.entity_description.fraction)
        return {
            **super().extra_state_attributes,
            "address": data.route.address,
            "municipality": data.route.municipality,
            "route_id": data.route.route_id,
            "route_name": data.route.name,
            "data_through": self.coordinator.window_end.isoformat()
            if self.coordinator.window_end
            else None,
            **(item.attributes() if item else {}),
        }
