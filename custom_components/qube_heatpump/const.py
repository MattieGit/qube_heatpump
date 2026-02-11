"""Constants for the Qube Heat Pump integration."""

DOMAIN = "qube_heatpump"
PLATFORMS = ["binary_sensor", "button", "climate", "number", "select", "sensor", "switch"]

TARIFF_OPTIONS = ("CH", "DHW")

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_NAME = "name"
CONF_ENTITY_PREFIX = "entity_prefix"  # Deprecated, kept for migration
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_ENTITY_PREFIX = "qube"

# Virtual thermostat
CONF_THERMOSTAT_ENABLED = "thermostat_enabled"
CONF_THERMOSTAT_SENSOR = "thermostat_sensor"
THERMOSTAT_MIN_TEMP = 15.0
THERMOSTAT_MAX_TEMP = 25.0
THERMOSTAT_STEP = 0.5
THERMOSTAT_COLD_TOLERANCE = 0.3
THERMOSTAT_HOT_TOLERANCE = 0.3
THERMOSTAT_SENSOR_TIMEOUT = 1800  # 30 minutes in seconds

# DHW schedule
CONF_DHW_SCHEDULE_ENABLED = "dhw_schedule_enabled"
CONF_DHW_SETPOINT = "dhw_setpoint"
CONF_DHW_START_TIME = "dhw_start_time"
CONF_DHW_END_TIME = "dhw_end_time"
DEFAULT_DHW_SETPOINT = 50.0
DEFAULT_DHW_START_TIME = "13:00"
DEFAULT_DHW_END_TIME = "15:00"
