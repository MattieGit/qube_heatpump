"""Constants for the Qube Heat Pump integration."""

DOMAIN = "qube_heatpump"
PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "switch"]

TARIFF_OPTIONS = ("CH", "DHW")

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_NAME = "name"
CONF_ENTITY_PREFIX = "entity_prefix"  # Deprecated, kept for migration
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_ENTITY_PREFIX = "qube"
