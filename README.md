<h1><img src="custom_components/sim_waste_collection_schedule/brand/icon.png" width="40" height="40" align="top" alt=""> SIM Waste Collection Schedule for Home Assistant</h1>

[![Live API][live-api-badge]][live-api-url]
[![Tests][tests-badge]][tests-url]
[![Validate][validate-badge]][validate-url]
[![HACS Custom][hacs-badge]][hacs-url]
[![License][license-badge]][license-url]

[live-api-badge]: https://img.shields.io/github/actions/workflow/status/FREE272/HomeAssistant-SIM/api-online.yml?branch=main&style=for-the-badge&label=Live%20API
[live-api-url]: https://github.com/FREE272/HomeAssistant-SIM/actions/workflows/api-online.yml
[tests-badge]: https://img.shields.io/github/actions/workflow/status/FREE272/HomeAssistant-SIM/tests.yml?branch=main&style=for-the-badge&label=Tests
[tests-url]: https://github.com/FREE272/HomeAssistant-SIM/actions/workflows/tests.yml
[validate-badge]: https://img.shields.io/github/actions/workflow/status/FREE272/HomeAssistant-SIM/validate.yml?branch=main&style=for-the-badge&label=Validate
[validate-url]: https://github.com/FREE272/HomeAssistant-SIM/actions/workflows/validate.yml
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white
[hacs-url]: https://www.hacs.xyz/docs/faq/custom_repositories/
[license-badge]: https://img.shields.io/github/license/FREE272/HomeAssistant-SIM?style=for-the-badge
[license-url]: https://github.com/FREE272/HomeAssistant-SIM/blob/main/LICENSE

An unofficial Home Assistant integration that retrieves waste collection days directly from [SIM](https://sim.as/). It requires no API key or login and supports addresses in the municipalities of Austevoll, Bømlo, Fitjar, Kvinnherad, Stord, Sveio, and Tysnes.

[Jump to installation](#installation)

## Exposed entities

| Platform | Entity key (unique ID suffix) | Description | Example value |
| -------- | ---------------------------- | ----------- | ------------- |
| `sensor` | `next_collection` | Date of the next collection, regardless of waste type. | `2026-10-13` |
| `sensor` | `days_until` | Number of days until the next collection. | `1` |
| `sensor` | `waste_types` | Waste types included in the next collection. The full or shortened waste names are controlled by the sensor value setting. | `Residual waste, Food waste` (or `Residual, Bio`) |
| `sensor` | `residual_waste` | Date of the next residual waste collection. | `2026-10-13` |
| `sensor` | `organic_waste` | Date of the next food waste collection. | `2026-10-13` |
| `sensor` | `paper` | Date of the next paper collection. | `2026-11-03` |
| `sensor` | `plastic_packaging` | Date of the next plastic packaging collection. | `2026-11-03` |
| `sensor` | `glass_and_metal` | Date of the next glass and metal packaging collection. | `2026-11-17` |
| `calendar` | `calendar` | Each address gets its own calendar with all-day collection events. Event names use the full or shortened waste names selected in settings. | [SIM Waste collection calendar for Testveg 12, Stord]<br>`2026-10-13`:<br>`Residual waste, Food waste` (or `Residual, Bio`) |

The entity key is appended to an address-specific unique ID. Home Assistant generates the visible entity ID from the entity name, and it can be changed in the entity registry.

The example values use the test schedule and English translations. Actual dates and waste names depend on the selected address, Home Assistant language, and name settings.

## Integration settings

The settings appear after you select an address during setup. You can change them later in the integration options under **Settings → Devices & services → SIM Waste Collection Schedule**.

| Setting | Description | Default |
| ------- | ----------- | ------- |
| Show collections in the Home Assistant calendar | Enables or disables the calendar entity. Sensors remain available when the calendar is disabled. | Enabled |
| Use full waste names in calendar events | Uses full or shortened waste names in calendar event titles. | Full |
| Use full waste names in sensor names | Uses full or shortened names for the waste fraction date sensors. | Full |
| Use full waste names in sensor values | Uses full or shortened waste names for the `waste_types` sensor state. | Full |

## Notifications

**Changed collection day**

Changes to collection days within the next 90 days trigger a Home Assistant notification. When SIM provides an explanation, it is included after the affected collection day as received from SIM; it may therefore be in Norwegian.

> **SIM collection days changed**
>
> SIM reports changed collection days for Testveg 12, Stord. These now apply:
>
> • 2026-10-13: Residual waste, Food waste — Flytta tømmedagen fordi me hadde lyst.

**API failure**

The API failure notification clears after a successful refresh.

> **SIM schedule update failed**
>
> Home Assistant could not refresh the collection schedule for Testveg 12, Stord after 3 consecutive attempts. The previously downloaded schedule remains in use when available, but may be out of date.

**Future calendar dates unavailable**

A calendar request for dates beyond the currently loaded schedule creates a separate notification if SIM cannot provide them. A later successful request covering those dates clears it.

> **Could not fetch future collection days**
>
> Home Assistant could not fetch collection days for Testveg 12, Stord beyond 2027-04-08. The calendar still shows dates already retrieved. Try again later.

## Data updates

The integration fetches the collection schedule for the next 180 days from SIM for every 24 hours. Date-based sensor values, such as the next collection and days until collection, are recalculated at midnight using the date in Norway.

If a later refresh fails, Home Assistant keeps using the last schedule held in memory. The entities remain available and show `schedule_stale: true` and the last successful refresh time in their attributes.


## Installation

### Step 1: Install the integration

**Prerequisite:** [HACS](https://hacs.xyz/) must be installed in Home Assistant.

Use the button below to open this repository in HACS:

[![Open this repository in the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FREE272&repository=HomeAssistant-SIM&category=integration)

Then:

1. Select **Download** to install the integration.
2. **Restart Home Assistant**.

> [!NOTE]
> The My Home Assistant link opens a landing page first. Select the button there to open the repository in your Home Assistant instance.

<details>
<summary><strong>Manual installation (advanced)</strong></summary>

1. Copy `custom_components/sim_waste_collection_schedule/` from this repository.
2. Place it in the `custom_components/` directory of your Home Assistant configuration.
3. Restart Home Assistant.

</details>

### Step 2: Configure the integration

**Important:** Install the integration and restart Home Assistant before configuring it.

#### Option 1: One-click setup

[![Open your Home Assistant instance and start setting up the SIM integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sim_waste_collection_schedule)

#### Option 2: Manual setup

1. Go to **Settings** → **Devices & Services**.
2. Select **Add Integration**.
3. Search for **SIM Waste Collection Schedule**.
4. Enter an address, optionally select a municipality, and choose the matching address from SIM's results.

## Development and testing

Nix is optional. The provided `shell.nix` selects Python 3.14 and creates and activates `.venv`; enter it with `nix-shell`. Without Nix, create and activate a Python 3.14 virtual environment yourself. In either environment, install the development dependencies with `scripts/setup`:

```sh
# Without Nix
python3.14 -m venv .venv
source .venv/bin/activate

# Run in either environment
scripts/setup
```

Run `pytest` for the test suite, `scripts/lint` to run Ruff and apply formatting and fixes, or `scripts/develop` to start a separate Home Assistant instance with the development configuration. GitHub Actions runs tests and Ruff checks on pushes and pull requests. Hassfest and HACS validation run on pushes, pull requests, and daily.

The live API smoke test runs weekly and can also be started manually from GitHub Actions. It requires a residential address with a regular household waste collection route. Add `SIM_LIVE_ADDRESS` and `SIM_LIVE_MUNICIPALITY` as GitHub Actions repository secrets. Locally, pytest skips the live test when those values are missing; the GitHub workflow reports an error until they are configured. To run it locally, set the same environment variables and run `pytest -q tests/test_api_online.py`.

## AI-assisted development

This integration was developed with the assistance of AI tools.

## Disclaimer

This is an independent project and is not affiliated with Sunnhordland Interkommunale Miljøverk IKS (SIM). It is licensed under the MIT License.
