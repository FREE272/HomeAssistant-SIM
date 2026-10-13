"""Async client for the JSON API used by the address menu on sim.as."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import hashlib
from typing import Any
import unicodedata

import aiohttp

from .const import API_BASE, WASTE_NAMES


class SimApiError(Exception):
    """Base API error; deliberately excludes address-bearing request URLs."""


class SimConnectionError(SimApiError):
    """SIM could not be reached."""


class SimResponseError(SimApiError):
    """SIM returned an unexpected response."""


def normalize(value: str) -> str:
    """Match addresses independently of letter case and repeated spaces."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class Route:
    """An address suggestion; route_id is shared by many addresses."""

    route_id: int
    address: str
    municipality: str
    name: str

    @property
    def unique_id(self) -> str:
        """Identify the address, preserving identity when its route changes."""
        return hashlib.sha256(
            f"{normalize(self.municipality)}:{normalize(self.address)}".encode()
        ).hexdigest()[:32]

    def as_entry_data(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "address": self.address,
            "municipality": self.municipality,
            "route_name": self.name,
        }


def waste_keys(raw: str) -> tuple[str, ...]:
    """Normalize SIM waste fractions to stable English identifiers."""
    result: list[str] = []
    for part in raw.split("/"):
        normalized = normalize(part)
        if normalized.startswith("metall"):
            key = "glass_and_metal"
        else:
            key = {
                "rest": "residual_waste",
                "restavfall": "residual_waste",
                "residual waste": "residual_waste",
                "bio": "organic_waste",
                "bioavfall": "organic_waste",
                "matavfall": "organic_waste",
                "food waste": "organic_waste",
                "organic waste": "organic_waste",
                "papir": "paper",
                "paper": "paper",
                "plast": "plastic_packaging",
                "plastemballasje": "plastic_packaging",
                "plastic": "plastic_packaging",
                "plastic packaging": "plastic_packaging",
                "glas": "glass_and_metal",
                "glass": "glass_and_metal",
                "glass and metal": "glass_and_metal",
                "glass and metal packaging": "glass_and_metal",
            }.get(normalized, normalized)
        if (
            key
            and key
            not in (
                "nothing",
                "no collection",
                "ingen",
                "ingen tømming",
                "ikkje tømming",
            )
            and key not in result
        ):
            result.append(key)
    return tuple(result)


def waste_label(raw: str, names: Mapping[str, str] | None = None) -> str:
    """Use translated names, preserving the original metal route variant."""
    names = names or WASTE_NAMES
    keys = waste_keys(raw)
    labels = [
        names.get(key, WASTE_NAMES.get(key, key.replace("_", " ").capitalize()))
        for key in keys
    ]
    metal = next(
        (
            part.strip()[6:].strip()
            for part in raw.split("/")
            if normalize(part).startswith("metall")
        ),
        "",
    )
    if metal and "glass_and_metal" in keys:
        labels = [
            f"{label} ({metal})" if key == "glass_and_metal" else label
            for key, label in zip(keys, labels, strict=True)
        ]
    return ", ".join(labels) or "No collection"


@dataclass(frozen=True)
class Collection:
    """One real collection; dates are supplied by SIM, never inferred."""

    day: date
    waste: str
    exception: bool = False
    comment: str | None = None

    @property
    def keys(self) -> tuple[str, ...]:
        return waste_keys(self.waste)

    @property
    def label(self) -> str:
        return waste_label(self.waste)

    def translated_label(self, names: Mapping[str, str]) -> str:
        """Return the event/state label in the configured Home Assistant language."""
        return waste_label(self.waste, names)

    def attributes(self) -> dict[str, Any]:
        return {
            "collection_date": self.day.isoformat(),
            "waste_types": list(self.keys),
            "waste_types_raw": self.waste,
            "changed_day": self.exception,
            "comment": self.comment,
        }


class SimApi:
    """Reuse Home Assistant's aiohttp session, without blocking its loop."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.get(
                API_BASE + endpoint,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise SimConnectionError(f"SIM returned HTTP {response.status}")
                try:
                    payload = await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise SimResponseError("SIM did not return valid JSON") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SimConnectionError("Unable to contact SIM") from err
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise SimResponseError("Missing data object in SIM response")
        return payload["data"]

    async def search_routes(
        self, address: str, municipality: str | None = None
    ) -> list[Route]:
        data = await self._request("address_search", {"address": address.strip()})
        if not isinstance(data.get("routes"), list):
            raise SimResponseError("Missing address list in SIM response")
        routes: list[Route] = []
        seen: set[tuple[str, int]] = set()
        for item in data["routes"]:
            try:
                if not isinstance(item, dict):
                    raise ValueError
                raw_route_id = item["id"]
                if isinstance(raw_route_id, bool) or not isinstance(
                    raw_route_id, (int, str)
                ):
                    raise ValueError
                route_id = int(raw_route_id)
                address_value, area = item["address"], item["area"]
                if (
                    route_id <= 0
                    or not isinstance(address_value, str)
                    or not address_value.strip()
                    or not isinstance(area, str)
                    or not area.strip()
                ):
                    raise ValueError
                route = Route(
                    route_id,
                    address_value.strip(),
                    area.strip(),
                    str(item.get("name") or ""),
                )
            except (KeyError, ValueError, TypeError) as err:
                raise SimResponseError("Invalid address suggestion from SIM") from err
            if municipality and normalize(route.municipality) != normalize(
                municipality
            ):
                continue
            identity = (route.unique_id, route.route_id)
            if identity not in seen:
                routes.append(route)
                seen.add(identity)
        return routes

    async def collections(
        self, route_id: int, start: date, end: date
    ) -> tuple[Collection, ...]:
        if end < start:
            return ()
        data = await self._request(
            "route_search",
            {"route": route_id, "from": start.isoformat(), "to": end.isoformat()},
        )
        if not isinstance(data.get("collections"), list):
            raise SimResponseError("Missing collection list in SIM response")
        records: set[Collection] = set()
        for item in data["collections"]:
            try:
                if not isinstance(item, dict):
                    raise ValueError
                day = date.fromisoformat(item["collection_date"])
                raw = item["waste_types"]
                if not isinstance(raw, str) or not raw.strip():
                    raise ValueError
                comment = item.get("exception_comment")
                if comment is not None and not isinstance(comment, str):
                    raise ValueError
                changed = item.get("exception") in (True, 1, "1")
                record = Collection(
                    day,
                    raw.strip(),
                    changed,
                    comment.strip() or None if comment else None,
                )
            except (KeyError, ValueError, TypeError) as err:
                raise SimResponseError("Invalid collection in SIM response") from err
            if start <= day <= end and record.keys:
                records.add(record)
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.day,
                    item.waste,
                    item.exception,
                    item.comment or "",
                ),
            )
        )
