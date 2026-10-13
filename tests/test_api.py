"""Exercise parsing and HTTP failures independently of platform setup."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.sim_waste_collection_schedule.api import (
    Route,
    SimApi,
    SimConnectionError,
    SimResponseError,
    waste_keys,
    waste_label,
)


def client(payload=None, status=200, json_error=None):
    response = MagicMock(status=status)
    response.json = AsyncMock(return_value=payload, side_effect=json_error)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = context
    return SimApi(session), session


async def test_address_ids_are_route_ids_and_filtering():
    api, session = client(
        {
            "data": {
                "routes": [
                    {
                        "id": 49,
                        "address": "Testveg 12",
                        "area": "STORD",
                        "name": "Tysdag B",
                    },
                    {
                        "id": 49,
                        "address": "Testveg 14",
                        "area": "STORD",
                        "name": "Tysdag B",
                    },
                    {
                        "id": 18,
                        "address": "Testveg 12",
                        "area": "BØMLO",
                        "name": "Måndag A",
                    },
                ]
            }
        }
    )
    routes = await api.search_routes("Testveg", "stord")
    assert len(routes) == 2
    assert routes[0].unique_id != routes[1].unique_id
    assert (
        routes[0].unique_id == Route(99, " TESTVEG  12 ", "stord", "Ny rute").unique_id
    )
    assert session.get.call_args.kwargs["params"] == {"address": "Testveg"}


@pytest.mark.parametrize("route_id", [49.5, True])
async def test_invalid_route_id_is_not_coerced(route_id):
    api, _ = client(
        {
            "data": {
                "routes": [
                    {
                        "id": route_id,
                        "address": "Testveg 12",
                        "area": "Stord",
                        "name": "Tysdag B",
                    }
                ]
            }
        }
    )
    with pytest.raises(SimResponseError):
        await api.search_routes("Testveg")


async def test_collections_sorted_deduplicated_and_filtered():
    base = {"waste_types": "Rest/bio", "exception": 0, "exception_comment": None}
    api, session = client(
        {
            "data": {
                "collections": [
                    {**base, "collection_date": "2027-01-03"},
                    {
                        **base,
                        "collection_date": "2026-12-31",
                        "exception": "1",
                        "exception_comment": "Flytta tømmedagen fordi me hadde lyst.",
                    },
                    {
                        **base,
                        "collection_date": "2026-12-31",
                        "exception": "1",
                        "exception_comment": "Flytta tømmedagen fordi me hadde lyst.",
                    },
                    {**base, "collection_date": "2026-12-30"},
                    {**base, "collection_date": "2027-01-01", "waste_types": "nothing"},
                ]
            }
        }
    )
    result = await api.collections(49, date(2026, 12, 31), date(2027, 1, 4))
    assert [item.day.isoformat() for item in result] == ["2026-12-31", "2027-01-03"]
    assert (
        result[0].exception
        and result[0].comment == "Flytta tømmedagen fordi me hadde lyst."
    )
    assert session.get.call_args.kwargs["params"]["from"] == "2026-12-31"


def test_glass_variant_and_unknown_fraction():
    assert waste_keys("Glas/metall B") == ("glass_and_metal",)
    assert waste_label("Glas/metall B") == "Glass and metal packaging (B)"
    assert waste_keys("Glass/Metall A") == ("glass_and_metal",)
    assert waste_label("Unknown") == "Unknown"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": None},
        {"data": {"collections": None}},
        {
            "data": {
                "collections": [
                    {"collection_date": "2026-02-30", "waste_types": "Rest"}
                ]
            }
        },
    ],
)
async def test_bad_response_is_not_empty_schedule(payload):
    api, _ = client(payload)
    with pytest.raises(SimResponseError):
        await api.collections(49, date(2026, 1, 1), date(2026, 12, 31))


async def test_http_and_json_errors():
    api, _ = client(status=503)
    with pytest.raises(SimConnectionError, match="HTTP 503"):
        await api.search_routes("Testveg")
    api, _ = client(json_error=ValueError("not JSON"))
    with pytest.raises(SimResponseError):
        await api.search_routes("Testveg")


async def test_network_error_hides_address_url():
    api, session = client()
    session.get.side_effect = aiohttp.ClientConnectionError("private address URL")
    with pytest.raises(SimConnectionError, match="Unable to contact SIM") as error:
        await api.search_routes("Testveg")
    assert "private" not in str(error.value)
