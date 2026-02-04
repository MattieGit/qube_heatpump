# Claude Code Notes

This file contains important conventions and guidelines for working on this codebase.

## Entity ID Naming Convention

Entity IDs in this integration use **vendor_id** (from modbus.yaml) as the basis for stable, predictable entity IDs.

### How it works

1. Each entity has a `vendor_id` field that matches the modbus register identifier
2. The `_attr_suggested_object_id` is set to the vendor_id in each entity class
3. Home Assistant generates entity IDs as: `{platform}.{device_name}_{vendor_id}`

### Example

| vendor_id | Device Name | Resulting Entity ID |
|-----------|-------------|---------------------|
| `temp_supply` | Qube | `sensor.qube_temp_supply` |
| `bms_summerwinter` | Qube | `switch.qube_bms_summerwinter` |
| `sg_ready_mode` | Qube | `select.qube_sg_ready_mode` |

### Benefits

- **Stable**: Entity IDs won't change when translations are updated
- **Predictable**: Direct mapping from modbus.yaml vendor_id to entity_id
- **Short**: Vendor IDs are concise (e.g., `temp_supply` vs `supply_temperature_cv`)
- **Traceable**: Easy to find modbus register documentation from entity_id

### Implementation

In each entity class (`sensor.py`, `binary_sensor.py`, `switch.py`, `select.py`, `number.py`, `button.py`):

```python
# Use vendor_id for stable, predictable entity IDs
if ent.vendor_id:
    self._attr_suggested_object_id = ent.vendor_id
```

For entities without vendor_id (computed sensors, diagnostic sensors), the `translation_key` is used as the `suggested_object_id`.

### Entity Name vs Entity ID

- **Entity ID** (e.g., `sensor.qube_temp_supply`): Based on vendor_id, stable
- **Entity Name** (e.g., "Supply temperature CV"): Based on translation, user-friendly

Both `_attr_has_entity_name = True` and `translation_key` are used so the UI shows translated names while entity IDs remain stable.
