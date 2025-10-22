# Qube Heatpump Dashboard Examples

This folder contains ready-to-use Lovelace YAML snippets that showcase the Qube Heatpump entities in a structured way.

## Using `dashboard_qube_overview.yaml`

1. In Home Assistant, go to **Settings → Dashboards** and create a new dashboard (or pick an existing manual dashboard). Enable the **Sections** layout (Home Assistant 2024.8 or newer) so the view supports headings and grids.
2. Open the dashboard, click the three-dot menu in the top-right, and choose **Edit dashboard**.
3. Choose **Edit in YAML**. For sections dashboards created via the UI this YAML editor expects the root keys `title:` and `sections:` (no `views:` block).
4. Copy `assets/qube_heatpump_dashboard.png` from this repository into your Home Assistant `config/www/` directory so it is served as `/local/qube_heatpump_dashboard.png`.
5. Replace the dashboard YAML with the contents of `dashboard_qube_overview.yaml`.
6. Save the changes and reload the dashboard page.

## Adjusting entity IDs

The example uses the default entity IDs created by the Qube integration. If you:

- Run multiple heat pumps, append the hub label (e.g. `_qube1`, `_qube2`) to each entity ID so it matches the registry entries.
- Renamed entities manually, update the YAML to match your preferred IDs.

Once saved, the dashboard shows a System snapshot picture card (with state labels overlaying the included photo), followed by Controls and the grouped sensor sections (alarms, operating hours, temperature/setpoints, power/energy, performance metrics, binary inputs, and diagnostics).
