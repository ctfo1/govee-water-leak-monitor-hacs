## 0.3.12

- Display the existing rtl_433 device name in the Lovelace card instead of appending the moisture entity label "Water Sensor".
- Process retained and live `event` messages; use the rtl_433 MQTT `time` field for event and wet-report timestamps, with HA reception time as a fallback.
- Keep `detect_wet` as the sole authority for current Wet/Dry state; event messages update history only.
- Reset to Dry publishes retained `detect_wet=0` and retained `event=HA Button Press`.

## 0.3.11

- Do not treat retained rtl_433 event messages replayed at MQTT reconnect as new events; preserve the actual Last Battery Report time across HA restarts. Retained wet/dry state messages continue to be processed.

## 0.3.10

- Refresh persistent and mobile leak alerts at each reminder using the latest wet-detection timestamp; dismissed mobile alerts return until acknowledged.
- Synchronize mobile notification acknowledgment with the Leak Acknowledged switch and clear active notifications when acknowledged.
- Retain the Reset to Dry MQTT state publication so a stale retained wet value is replaced across Home Assistant restarts.
- Add a battery last-report timestamp tooltip when a valid report time exists, and reduce the battery percentage text size.
- Standardize the Last Leak Started entity ID to `sensor.govee_water_leak_monitor_[device_name]_leak_started` while preserving its unique ID.

# Changelog

## 0.3.9
- Lovelace card now automatically displays all discovered Govee leak monitors, each in its own compact card section.
- Removed the per-sensor selection requirement and retained individual acknowledgment and Reset to Dry controls.
- Standardized sensor name, status, Water last detected, and battery text sizing/alignment.

## 0.3.8
- Compact Lovelace card spacing to better match the original automation cards.
- Align Wet/Dry and Water last detected on one baseline with a hyphen separator.
- Center battery percentage vertically with its charge-level icon.

## 0.3.7
- Hide Water last detected on the Lovelace card when the value is Never.
- Include the complete GitHub repository files in the release archive.

## 0.3.6
- Removed Last Leak Started from the Lovelace card.
- Removed the duplicate icon beside Wet/Dry status.
- Removed the circular background behind the large water icon and increased its visual size.
- Battery icon reflects charge level; hide battery when unknown or unavailable.

## 0.3.5
- Fixed card editor selector closing during interaction.
- Removed Test Notification, Last Battery Report, and Last Notification from the card.
- Moved Water last detected onto the Wet/Dry status line.
- Used Material Design icons matching the example card.

## 0.3.4
- Added a standalone Lovelace card and automatic resource registration in storage mode.
- Added manual resource registration instructions for YAML mode.
- Supports one card per sensor and discovers related monitor and rtl_433 battery entities through their shared device association.

## 0.3.3
- Renamed Last Alert to Last Notification.
- Renamed Leak Started to Last Leak Started and retain its timestamp after dry.
- Preserve existing entity registry IDs and migrate the prior Last Alert timestamp.

## 0.3.1
- Fixed device association so monitor entities are linked to the existing rtl_433 MQTT device.
- Preserve monitor state and settings if the MQTT device is deleted; reattach on rediscovery.
- Moved action buttons into the Controls group.
- Fixed notification formatting for devices without an assigned area.

## 0.3.0
- Replaced manual moisture-entity setup with automatic rtl_433 Govee Water MQTT discovery.
- Uses the `detect_wet` MQTT field as the authoritative wet/dry state.
- Reset to Dry publishes `0` to the sensor's real MQTT state topic.
- Prevented repeated wet packets from starting duplicate leak episodes or notifications.
