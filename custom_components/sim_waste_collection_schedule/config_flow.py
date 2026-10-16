"""Address search and selection flow for the SIM integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import Route, SimApi, SimConnectionError, SimResponseError
from .const import (
    CONF_ADDRESS,
    CONF_ENABLE_CALENDAR,
    CONF_FULL_CALENDAR_NAMES,
    CONF_FULL_SENSOR_NAMES,
    CONF_FULL_SENSOR_VALUES,
    CONF_MUNICIPALITY,
    DEFAULT_FULL_CALENDAR_NAMES,
    DEFAULT_FULL_SENSOR_NAMES,
    DEFAULT_FULL_SENSOR_VALUES,
    DOMAIN,
    LOOKAHEAD_DAYS,
    MUNICIPALITIES,
)
from .coordinator import sim_today


class SimConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one independently configurable entry per address."""

    VERSION = 1

    def __init__(self) -> None:
        self._routes: list[Route] = []
        self._selected_route: Route | None = None
        self._enable_calendar = True
        self._full_calendar_names = DEFAULT_FULL_CALENDAR_NAMES
        self._full_sensor_names = DEFAULT_FULL_SENSOR_NAMES
        self._full_sensor_values = DEFAULT_FULL_SENSOR_VALUES

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SimOptionsFlow:
        return SimOptionsFlow()

    def _api(self) -> SimApi:
        return SimApi(async_get_clientsession(self.hass))

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            if len(address) < 3 or len(address) > 120:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                try:
                    self._routes = await self._api().search_routes(
                        address, user_input.get(CONF_MUNICIPALITY)
                    )
                    if self._routes:
                        return await self.async_step_select()
                    errors["base"] = "no_addresses"
                except SimConnectionError:
                    errors["base"] = "cannot_connect"
                except SimResponseError:
                    errors["base"] = "invalid_response"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): TextSelector(),
                    vol.Optional(CONF_MUNICIPALITY): SelectSelector(
                        SelectSelectorConfig(
                            options=list(MUNICIPALITIES),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if not self._routes:
            return await self.async_step_user()
        if user_input is not None:
            choice = user_input.get(CONF_ADDRESS)
            route = next(
                (
                    route
                    for index, route in enumerate(self._routes)
                    if str(index) == choice
                ),
                None,
            )
            if route is None:
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(route.unique_id)
                self._abort_if_unique_id_configured()
                self._selected_route = route
                return await self.async_step_settings()
        options = [
            {
                "value": str(index),
                "label": (
                    f"{route.address}, {route.municipality}"
                    f"{route.name} ({route.route_id})"
                ),
            }
            for index, route in enumerate(self._routes)
        ]
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure collection settings after selecting an address."""
        if self._selected_route is None:
            return await self.async_step_user()

        errors: dict[str, str] = {}
        if user_input is not None:
            self._enable_calendar = user_input.get(CONF_ENABLE_CALENDAR, True)
            self._full_calendar_names = user_input.get(
                CONF_FULL_CALENDAR_NAMES, DEFAULT_FULL_CALENDAR_NAMES
            )
            self._full_sensor_names = user_input.get(
                CONF_FULL_SENSOR_NAMES, DEFAULT_FULL_SENSOR_NAMES
            )
            self._full_sensor_values = user_input.get(
                CONF_FULL_SENSOR_VALUES, DEFAULT_FULL_SENSOR_VALUES
            )
            try:
                today = sim_today()
                await self._api().collections(
                    self._selected_route.route_id,
                    today,
                    today + timedelta(days=LOOKAHEAD_DAYS),
                )
            except SimConnectionError:
                errors["base"] = "cannot_connect"
            except SimResponseError:
                errors["base"] = "invalid_response"
            else:
                return self.async_create_entry(
                    title=(
                        f"{self._selected_route.address}, "
                        f"{self._selected_route.municipality}"
                    ),
                    data={
                        **self._selected_route.as_entry_data(),
                        CONF_ENABLE_CALENDAR: self._enable_calendar,
                        CONF_FULL_CALENDAR_NAMES: self._full_calendar_names,
                        CONF_FULL_SENSOR_NAMES: self._full_sensor_names,
                        CONF_FULL_SENSOR_VALUES: self._full_sensor_values,
                    },
                )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_CALENDAR, default=self._enable_calendar
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_CALENDAR_NAMES, default=self._full_calendar_names
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_SENSOR_NAMES, default=self._full_sensor_names
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_SENSOR_VALUES, default=self._full_sensor_values
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )


class SimOptionsFlow(config_entries.OptionsFlow):
    """Let users change calendar visibility and each waste-name style."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        enabled = self.config_entry.options.get(
            CONF_ENABLE_CALENDAR, self.config_entry.data.get(CONF_ENABLE_CALENDAR, True)
        )
        full_calendar_names = self.config_entry.options.get(
            CONF_FULL_CALENDAR_NAMES,
            self.config_entry.data.get(
                CONF_FULL_CALENDAR_NAMES, DEFAULT_FULL_CALENDAR_NAMES
            ),
        )
        full_sensor_names = self.config_entry.options.get(
            CONF_FULL_SENSOR_NAMES,
            self.config_entry.data.get(
                CONF_FULL_SENSOR_NAMES, DEFAULT_FULL_SENSOR_NAMES
            ),
        )
        full_sensor_values = self.config_entry.options.get(
            CONF_FULL_SENSOR_VALUES,
            self.config_entry.data.get(
                CONF_FULL_SENSOR_VALUES, DEFAULT_FULL_SENSOR_VALUES
            ),
        )
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_ENABLE_CALENDAR: user_input.get(CONF_ENABLE_CALENDAR, enabled),
                    CONF_FULL_CALENDAR_NAMES: user_input.get(
                        CONF_FULL_CALENDAR_NAMES, full_calendar_names
                    ),
                    CONF_FULL_SENSOR_NAMES: user_input.get(
                        CONF_FULL_SENSOR_NAMES, full_sensor_names
                    ),
                    CONF_FULL_SENSOR_VALUES: user_input.get(
                        CONF_FULL_SENSOR_VALUES, full_sensor_values
                    ),
                },
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_CALENDAR, default=enabled
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_CALENDAR_NAMES, default=full_calendar_names
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_SENSOR_NAMES, default=full_sensor_names
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_FULL_SENSOR_VALUES, default=full_sensor_values
                    ): BooleanSelector(),
                }
            ),
        )
