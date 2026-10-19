# Qube Heat Pump Dashboard Examples

This folder contains ready-to-use Lovelace YAML snippets that showcase the Qube heat pump entities in a structured way.

## Using `dashboard_qube_overview.yaml`

1. Copy `assets/qube_heatpump_dashboard.png` into your Home Assistant `config/www/` directory (create the folder if it does not exist). Home Assistant will then serve the image at `/local/qube_heatpump_dashboard.png`, which the dashboard references.
2. In Home Assistant, go to **Settings → Dashboards** and create a new manual dashboard (or select an existing manual dashboard). When prompted, enable the **Sections** layout (Home Assistant 2024.8 or newer) so the view supports headings and grids.
3. Open the dashboard view, click the pencil icon in the top bar to enter edit mode (the bar turns dark grey to confirm you are editing).
4. While still in edit mode, click the pencil icon next to the view name in the status bar to open the view editor.
5. In the view editor, open the three-dot menu in the top-right corner.
6. Choose **Edit in YAML**. For dashboards using the Sections layout via the UI, the YAML editor expects the root keys `title:` and `sections:` (no wrapping `views:` block).
7. Replace the YAML content with the contents of `examples/dashboard_qube_overview.yaml` from this repository.
8. Save the YAML, close the editor, and reload the dashboard page to apply the new layout.

## Adjusting entity IDs

Entity IDs are `<platform>.<device name>_<key>`; the device name is slugified and used as **prefix**. The example uses `qube_1`, the prefix for the default device name "qube 1". With another device name, search and replace `.qube_1_` with `.<your device-name slug>_` in the YAML.

- Run multiple heat pumps: each entry has its own device name, so use that name's slug as prefix for the entities of that heat pump.
- Renamed entities manually: update the YAML to match your preferred IDs.
- The room temperature label shows `sensor.qube_1_modbus_roomtemp`, the value a LinQ sends to the heat pump. Without a LinQ it stays at 0; if a room sensor is connected to the heat pump itself, enable `sensor.qube_1_temp_room` (disabled by default) and use that in the YAML instead.
- The SG Ready controls use `select.qube_1_sg_ready_mode`. The two underlying Modbus coils are not exposed as switch entities; the select writes both.

Once saved, the dashboard shows a System snapshot picture card (with state labels overlaying the included photo; their positions are percentages of the picture, so they stay in place at any card width), followed by Controls and the grouped sensor sections (alarms, operating hours, temperature/setpoints, power/energy, performance metrics, binary inputs, and diagnostics).

The integration also exposes `binary_sensor.qube_1_alarm_sensors_active`, which is on while any alarm binary sensor is active; the example dashboard uses it for conditional visibility of the alarm section.
