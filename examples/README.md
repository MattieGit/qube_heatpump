# Qube Heatpump Dashboard Examples

This folder contains ready-to-use Lovelace YAML snippets that showcase the Qube Heatpump entities in a structured way.

## Using `dashboard_qube_overview.yaml`

1. In Home Assistant, go to **Settings → Dashboards** and create a new dashboard (or pick an existing manual dashboard).
2. Open the dashboard, click the three-dot menu in the top-right, and choose **Edit dashboard**.
3. If prompted, switch the dashboard to **YAML mode**.
4. Replace the dashboard YAML with the contents of `dashboard_qube_overview.yaml`.
5. Save the changes.

## Adjusting entity IDs

The example uses the default entity IDs created by the Qube integration. If you:

- Run multiple heat pumps, append the hub label (e.g. `_qube1`, `_qube2`) to each entity ID so it matches the registry entries.
- Renamed entities manually, update the YAML to match your preferred IDs.

Once saved, the dashboard will show the Controls card first and then the grouped sensor sections (alarms, operating hours, temperature/setpoints, power/energy, performance metrics, binary inputs, and diagnostics).
