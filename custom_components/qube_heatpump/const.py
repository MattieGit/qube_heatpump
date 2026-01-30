"""Constants for the Qube Heat Pump integration."""

DOMAIN = "qube_heatpump"
PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "switch"]

TARIFF_OPTIONS = ("CH", "DHW")

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_FRIENDLY_NAME_LANGUAGE = "friendly_name_language"
DEFAULT_FRIENDLY_NAME_LANGUAGE = "nl"
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 10
