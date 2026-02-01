# Qube Heatpump Dashboard Examples

This folder contains ready-to-use Lovelace YAML snippets that showcase the Qube Heatpump entities in a structured way.

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

The example uses the default entity IDs created by the Qube integration. If you:

- Run multiple heat pumps, append the hub label (e.g. `_qube1`, `_qube2`) to each entity ID so it matches the registry entries.
- Renamed entities manually, update the YAML to match your preferred IDs.
- The SG Ready controls now use `select.qube1_sgready_mode`. The integration keeps the underlying `switch.qube1_bms_sgready_a` and `switch.qube1_bms_sgready_b` entities hidden by default; expose them manually only if you need per-coil automation.

Once saved, the dashboard shows a System snapshot picture card (with state labels overlaying the included photo), followed by Controls and the grouped sensor sections (alarms, operating hours, temperature/setpoints, power/energy, performance metrics, binary inputs, and diagnostics).

The integration also exposes `binary_sensor.qube1_alarm_sensors`, which mirrors whether any alarm binary sensor is active; the example dashboard uses this helper for conditional visibility.
