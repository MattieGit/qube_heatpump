# wp-qube
Qube heat pump integration Home Asssistant

This integration will integrate the Qube heat pump (sold by HR-Energy) into Home Assistant.
The Home Assistant Modbus integration is required for this integration.

During configuration you only have to specify the local IP of your Qube heat pump. This IP can be checked on the display that is connected to the heat pump.
The default port is 502 and should not be changed, unless you are using a custom setup.

The integration will setup up sensors, binary sensors (alarms) and switches.

The switches enable SG Ready implementations as well as automations to run the anti-legionella program, for example when surplus solar energy is available.

This is an initial version of the integration and might still have issues. Please report any issues.