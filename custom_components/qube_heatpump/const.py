"""Constants for the Qube Heat Pump integration."""

# Re-exported so the rest of the integration (and its tests) can keep
# importing the connection keys from here; the values are HA's standard ones.
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    Platform,
)

DOMAIN = "qube_heatpump"
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

TARIFF_OPTIONS = ("CH", "DHW")

# Legacy: the Modbus unit id was once configurable; only read, never written.
CONF_UNIT_ID = "unit_id"
DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 15

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
CONF_DHW_USE_CONTROLLER_SETPOINT = "dhw_use_controller_setpoint"
CONF_DHW_SETPOINT = "dhw_setpoint"
CONF_DHW_START_TIME = "dhw_start_time"
CONF_DHW_END_TIME = "dhw_end_time"
# By default the scheduler only toggles the forced-DHW coil and leaves the
# Modbus DHW setpoint (register 173) as set on the controller.
DEFAULT_DHW_USE_CONTROLLER_SETPOINT = True
# Only used when the scheduler is configured to write its own setpoint.
DEFAULT_DHW_SETPOINT = 50.0
DEFAULT_DHW_START_TIME = "13:00"
DEFAULT_DHW_END_TIME = "15:00"
