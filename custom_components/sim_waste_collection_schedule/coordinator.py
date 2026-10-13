"""Shared, infrequent API polling and calendar range caching."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import Collection, Route, SimApi, SimApiError, normalize
from .const import (
    API_FAILURE_NOTIFICATION_THRESHOLD,
    CHANGE_NOTIFICATION_LOOKAHEAD_DAYS,
    CONF_FULL_CALENDAR_NAMES,
    CONF_FULL_SENSOR_NAMES,
    CONF_FULL_SENSOR_VALUES,
    DEFAULT_FULL_CALENDAR_NAMES,
    DEFAULT_FULL_SENSOR_NAMES,
    DEFAULT_FULL_SENSOR_VALUES,
    DOMAIN,
    LOOKAHEAD_DAYS,
    UPDATE_INTERVAL,
    WASTE_NAMES,
    WASTE_SHORT_NAMES,
)

_LOGGER = logging.getLogger(__name__)
OSLO = ZoneInfo("Europe/Oslo")


def sim_today() -> date:
    """SIM dates belong to Norway, regardless of the server's timezone."""
    return datetime.now(OSLO).date()


@dataclass(frozen=True)
class Schedule:
    """Keep the reference day in the data so listeners update at midnight."""

    today: date
    route: Route
    collections: tuple[Collection, ...]

    def next_collection(self, fraction: str | None = None) -> Collection | None:
        return next(
            (
                item
                for item in self.collections
                if item.day >= self.today
                and (fraction is None or fraction in item.keys)
            ),
            None,
        )


class SimCoordinator(DataUpdateCoordinator[Schedule]):
    """One coordinator serves all sensors and the calendar for an address."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: SimApi,
        translations: dict[str, str],
    ) -> None:
        # The first refresh is explicit during setup; this interval governs
        # subsequent polls, starting when this config entry successfully loads.
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.api = api
        self.translations = translations
        # Setup retries create a fresh coordinator, so retain failure counts and
        # notification signatures across attempts and Home Assistant restarts.
        self._notification_store: Store[dict[str, object]] = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}"
        )
        self._consecutive_failures = 0
        # HA does not restore these notifications after restart. The saved
        # counts/signature let us recreate an alert if the condition remains.
        self._failure_notification_active = False
        self._schedule_notification_signature: str | None = None
        self._schedule_notification_shown_this_session = False
        self.last_successful_update: datetime | None = None
        self._failure_notification_id = (
            f"{DOMAIN}_{entry.entry_id.replace('-', '_')}_api_failure"
        )
        self._schedule_notification_id = (
            f"{DOMAIN}_{entry.entry_id.replace('-', '_')}_schedule_changes"
        )
        self._future_calendar_notification_id = (
            f"{DOMAIN}_{entry.entry_id.replace('-', '_')}_future_calendar"
        )
        self._future_calendar_failure_end: date | None = None
        self.route = Route(
            entry.data["route_id"],
            entry.data["address"],
            entry.data["municipality"],
            entry.data["route_name"],
        )
        self.full_calendar_names = entry.options.get(
            CONF_FULL_CALENDAR_NAMES,
            entry.data.get(CONF_FULL_CALENDAR_NAMES, DEFAULT_FULL_CALENDAR_NAMES),
        )
        self.full_sensor_values = entry.options.get(
            CONF_FULL_SENSOR_VALUES,
            entry.data.get(CONF_FULL_SENSOR_VALUES, DEFAULT_FULL_SENSOR_VALUES),
        )
        self.full_sensor_names = entry.options.get(
            CONF_FULL_SENSOR_NAMES,
            entry.data.get(CONF_FULL_SENSOR_NAMES, DEFAULT_FULL_SENSOR_NAMES),
        )
        self.calendar_waste_names = localized_waste_names(
            translations, self.full_calendar_names
        )
        self.sensor_value_waste_names = localized_waste_names(
            translations, self.full_sensor_values
        )
        self._lock = asyncio.Lock()
        self._range_cache: dict[
            tuple[int, date, date], tuple[datetime, tuple[Collection, ...]]
        ] = {}
        self.window_start: date | None = None
        self.window_end: date | None = None

    async def _async_update_data(self) -> Schedule:
        try:
            # Each refresh makes two API calls: resolve the address to
            # detect route changes, then fetch the current 180-day schedule.
            candidates = await self.api.search_routes(
                self.route.address, self.route.municipality
            )
            matches = [
                route
                for route in candidates
                if normalize(route.address) == normalize(self.route.address)
            ]
            route = next(
                (item for item in matches if item.route_id == self.route.route_id), None
            )
            if route is None and len(matches) == 1:
                route = matches[0]
            if route is None:
                raise UpdateFailed(
                    "The selected SIM address could not be resolved "
                    "unambiguously; add it again"
                )
            today = sim_today()
            start, end = (
                today - timedelta(days=1),
                today + timedelta(days=LOOKAHEAD_DAYS),
            )
            async with self._lock:
                records = await self.api.collections(route.route_id, start, end)
                self._range_cache.clear()
                self.route = route
                self.window_start, self.window_end = start, end
                if (
                    self._future_calendar_failure_end is not None
                    and end >= self._future_calendar_failure_end
                ):
                    self._dismiss_future_calendar_notification()
                    self._future_calendar_failure_end = None
        except SimApiError as err:
            await self._record_update_failure()
            raise UpdateFailed(str(err)) from err
        except UpdateFailed:
            await self._record_update_failure()
            raise

        schedule = Schedule(today, route, records)
        self.last_successful_update = dt_util.utcnow()
        await self._record_update_success(schedule)
        return schedule

    async def async_load_notification_state(self) -> None:
        """Restore notification deduplication across Home Assistant restarts."""
        try:
            state = await self._notification_store.async_load()
        except Exception:
            _LOGGER.exception("Could not load SIM notification state")
            return
        if not isinstance(state, dict):
            return
        failures = state.get("consecutive_failures", 0)
        if isinstance(failures, int) and not isinstance(failures, bool):
            self._consecutive_failures = max(0, failures)
        signature = state.get("schedule_notification_signature")
        if isinstance(signature, str):
            self._schedule_notification_signature = signature

    async def _record_update_failure(self) -> None:
        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= API_FAILURE_NOTIFICATION_THRESHOLD
            and not self._failure_notification_active
        ):
            try:
                persistent_notification.async_create(
                    self.hass,
                    self._translated(
                        "api_failure_message",
                        "Home Assistant could not refresh the collection schedule "
                        "for {address}, {municipality} after {failures} consecutive "
                        "attempts. The previously downloaded schedule remains in "
                        "use when available, but may be out of date.",
                    ).format(
                        address=self.route.address,
                        municipality=self.route.municipality,
                        failures=self._consecutive_failures,
                    ),
                    title=self._translated(
                        "api_failure_title", "SIM schedule update failed"
                    ),
                    notification_id=self._failure_notification_id,
                )
                self._failure_notification_active = True
            except Exception:
                _LOGGER.exception("Could not create SIM API failure notification")
        await self._save_notification_state()

    async def _record_update_success(self, schedule: Schedule) -> None:
        state_changed = self._consecutive_failures != 0
        self._consecutive_failures = 0
        if state_changed or self._failure_notification_active:
            try:
                # A setup retry can have a new coordinator while the stable
                # notification ID still refers to an alert from an earlier try.
                persistent_notification.async_dismiss(
                    self.hass, self._failure_notification_id
                )
            except Exception:
                _LOGGER.exception("Could not dismiss SIM API failure notification")
            self._failure_notification_active = False
            state_changed = True

        changed = self._changed_collections(schedule)
        # Persist the signature to avoid repeating unchanged alerts on each
        # poll; the stable notification ID updates the alert if details change.
        signature = self._schedule_signature(schedule, changed) if changed else None
        if (
            signature != self._schedule_notification_signature
            and not changed
            and self._schedule_notification_signature is not None
        ):
            try:
                persistent_notification.async_dismiss(
                    self.hass, self._schedule_notification_id
                )
            except Exception:
                _LOGGER.exception("Could not dismiss SIM changed-date notification")
            self._schedule_notification_signature = None
            state_changed = True

        if changed and (
            signature != self._schedule_notification_signature
            or not self._schedule_notification_shown_this_session
        ):
            try:
                message = self._translated(
                    "schedule_change_message",
                    "SIM reports changed collection days for {address}, "
                    "{municipality}. These now apply:\n\n{changes}",
                ).format(
                    address=schedule.route.address,
                    municipality=schedule.route.municipality,
                    changes="\n".join(self._format_change(item) for item in changed),
                )
                persistent_notification.async_create(
                    self.hass,
                    message,
                    title=self._translated(
                        "schedule_change_title", "SIM collection days changed"
                    ),
                    notification_id=self._schedule_notification_id,
                )
            except Exception:
                _LOGGER.exception("Could not create SIM changed-date notification")
                # Keep the prior signature so the notification is retried.
            else:
                self._schedule_notification_signature = signature
                self._schedule_notification_shown_this_session = True
                state_changed = True
        elif not changed:
            self._schedule_notification_shown_this_session = True

        if state_changed:
            await self._save_notification_state()

    def _changed_collections(self, schedule: Schedule) -> tuple[Collection, ...]:
        """Return SIM-marked changes from today through the next 90 days."""
        cutoff = schedule.today + timedelta(days=CHANGE_NOTIFICATION_LOOKAHEAD_DAYS)
        return tuple(
            item
            for item in schedule.collections
            if item.exception and schedule.today <= item.day <= cutoff
        )

    def _schedule_signature(
        self, schedule: Schedule, changed: tuple[Collection, ...]
    ) -> str:
        rows = sorted(
            f"{item.day.isoformat()}|{item.waste}|{item.comment or ''}"
            for item in changed
        )
        value = f"{schedule.route.route_id}\n" + "\n".join(rows)
        return hashlib.sha256(value.encode()).hexdigest()

    def _format_change(self, item: Collection) -> str:
        line = self._translated("schedule_change_item", "{date}: {waste}").format(
            date=item.day.isoformat(),
            waste=item.translated_label(self.calendar_waste_names),
        )
        if item.comment:
            line += self._translated("schedule_change_comment", " — {comment}").format(
                comment=item.comment
            )
        return f"• {line}"

    def _translated(self, key: str, fallback: str) -> str:
        return self.translations.get(f"component.{DOMAIN}.common.{key}", fallback)

    async def _save_notification_state(self) -> None:
        try:
            await self._notification_store.async_save(
                {
                    "consecutive_failures": self._consecutive_failures,
                    "schedule_notification_signature": (
                        self._schedule_notification_signature
                    ),
                }
            )
        except Exception:
            _LOGGER.exception("Could not save SIM notification state")

    def _notify_future_calendar_failure(self, requested_end: date) -> None:
        if self.window_end is None:
            return
        self._future_calendar_failure_end = max(
            self._future_calendar_failure_end or requested_end, requested_end
        )
        try:
            persistent_notification.async_create(
                self.hass,
                self._translated(
                    "calendar_range_failure_message",
                    "Home Assistant could not fetch collection days for {address}, "
                    "{municipality} beyond {last_date}. The calendar still shows "
                    "dates already retrieved. Try again later.",
                ).format(
                    address=self.route.address,
                    municipality=self.route.municipality,
                    last_date=self.window_end.isoformat(),
                ),
                title=self._translated(
                    "calendar_range_failure_title",
                    "Could not fetch future collection days",
                ),
                notification_id=self._future_calendar_notification_id,
            )
        except Exception:
            _LOGGER.exception("Could not create SIM future calendar notification")

    def _dismiss_future_calendar_notification(self) -> None:
        try:
            persistent_notification.async_dismiss(
                self.hass, self._future_calendar_notification_id
            )
        except Exception:
            _LOGGER.exception("Could not dismiss SIM future calendar notification")

    def _clear_future_calendar_notification_if_covered(
        self, start: date, end: date
    ) -> None:
        failed_through = self._future_calendar_failure_end
        if failed_through is not None and start <= failed_through <= end:
            self._dismiss_future_calendar_notification()
            self._future_calendar_failure_end = None

    @callback
    def async_start_midnight_updates(self) -> None:
        """Recompute Norway date-derived states without another API request."""

        @callback
        def midnight(_: datetime) -> None:
            if self.data is not None and self.data.today != sim_today():
                self.data = Schedule(
                    sim_today(), self.data.route, self.data.collections
                )
                self.async_update_listeners()

        # Track local HA midnight; a 15-minute date check also handles HA zones
        # other than Europe/Oslo. Norway-configured homes update at 00:00:01.
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, midnight, hour=0, minute=0, second=1)
        )
        self.config_entry.async_on_unload(
            async_track_time_change(
                self.hass, midnight, minute=[0, 15, 30, 45], second=1
            )
        )

    async def async_calendar_collections(
        self, start: date, end: date
    ) -> tuple[Collection, ...]:
        """Serve cached coverage; fetch other requested calendar months on demand."""
        async with self._lock:
            if (
                self.data is not None
                and self.window_start is not None
                and self.window_end is not None
                and self.window_start <= start <= end <= self.window_end
            ):
                self._clear_future_calendar_notification_if_covered(start, end)
                return tuple(
                    item for item in self.data.collections if start <= item.day <= end
                )
            future_range = self.window_end is not None and end > self.window_end
            key = (self.route.route_id, start, end)
            cached = self._range_cache.get(key)
            if cached and datetime.now(OSLO) - cached[0] < UPDATE_INTERVAL:
                self._clear_future_calendar_notification_if_covered(start, end)
                return cached[1]
            try:
                records = await self.api.collections(self.route.route_id, start, end)
            except SimApiError:
                if future_range:
                    self._notify_future_calendar_failure(end)
                raise
            self._clear_future_calendar_notification_if_covered(start, end)
            if len(self._range_cache) >= 12:
                self._range_cache.pop(next(iter(self._range_cache)))
            self._range_cache[key] = (datetime.now(OSLO), records)
            return records


def localized_waste_names(
    translations: dict[str, str], full_names: bool
) -> dict[str, str]:
    """Read the selected set of localized names from Home Assistant translations."""
    style = "full" if full_names else "short"
    fallbacks = WASTE_NAMES if full_names else WASTE_SHORT_NAMES
    return {
        fraction: translations.get(
            f"component.{DOMAIN}.entity.sensor.{fraction}_{style}.name", fallback
        )
        for fraction, fallback in fallbacks.items()
    }
