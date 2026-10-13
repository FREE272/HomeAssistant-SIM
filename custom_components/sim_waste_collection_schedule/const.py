"""Constants for the SIM waste collection integration."""

from datetime import timedelta

DOMAIN = "sim_waste_collection_schedule"
NAME = "SIM Waste Collection Schedule"
API_BASE = "https://sim.as/wp-json/tommekalender/v1/"
CONF_ADDRESS = "address"
CONF_MUNICIPALITY = "municipality"
CONF_ROUTE_ID = "route_id"
CONF_ROUTE_NAME = "route_name"
CONF_ENABLE_CALENDAR = "enable_calendar"
CONF_FULL_CALENDAR_NAMES = "full_calendar_names"
CONF_FULL_SENSOR_NAMES = "full_sensor_names"
CONF_FULL_SENSOR_VALUES = "full_sensor_values"
DEFAULT_FULL_CALENDAR_NAMES = True
DEFAULT_FULL_SENSOR_NAMES = True
DEFAULT_FULL_SENSOR_VALUES = True
# SIM returns a 180-day schedule and route changes are rare; one daily refresh
# keeps the data current without polling the API more often than needed.
UPDATE_INTERVAL = timedelta(hours=24)
# Alert only after repeated failures so a brief SIM outage does not notify users.
API_FAILURE_NOTIFICATION_THRESHOLD = 3
CHANGE_NOTIFICATION_LOOKAHEAD_DAYS = 90
LOOKAHEAD_DAYS = 180
MUNICIPALITIES = (
    "Austevoll",
    "Bømlo",
    "Fitjar",
    "Kvinnherad",
    "Stord",
    "Sveio",
    "Tysnes",
)
WASTE_NAMES = {
    "residual_waste": "Residual waste",
    "organic_waste": "Food waste",
    "paper": "Paper",
    "plastic_packaging": "Plastic packaging",
    "glass_and_metal": "Glass and metal packaging",
}
WASTE_SHORT_NAMES = {
    "residual_waste": "Residual",
    "organic_waste": "Bio",
    "paper": "Paper",
    "plastic_packaging": "Plastic",
    "glass_and_metal": "Glass & metal",
}
