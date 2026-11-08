# Govee Water Leak Monitor

Home Assistant custom integration for Govee Water sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433) and published through the Home Assistant MQTT integration.

## Features

- Automatically discovers rtl_433 `Govee-Water` devices from Home Assistant MQTT discovery.
- Adds monitoring entities to the **existing rtl_433 MQTT device**. It does not create a separate device. Device names and areas remain controlled by Home Assistant.
- Uses the sensor's `detect_wet` MQTT topic as the authoritative wet/dry state.
- Sends email, mobile, and persistent notifications when a new leak episode starts.
- Suppresses duplicate alerts while rtl_433 repeats wet packets; a subsequent `detect_wet=0` ends the episode.
- Provides Acknowledge, Reset Acknowledgment, Reset to Dry, and Test Notification buttons.
- Reset to Dry publishes `0` to the sensor's actual `detect_wet` topic. The existing MQTT moisture entity and this integration then follow the MQTT state update.
- Exposes battery voltage, the raw `battery_ok` decoder value, last battery report, last wet event, last alert, and last rtl_433 event.
- Reads the existing MQTT device's current name and assigned area for notifications.

## Requirements

- Home Assistant MQTT integration configured and running.
- rtl_433 publishing MQTT messages in the standard topic structure:

  ```text
  rtl_433/<instance>/devices/Govee-Water/<sensor_id>/<field>
  ```

- Home Assistant MQTT discovery enabled for rtl_433. The moisture entity discovery config must identify the device as `manufacturer: rtl_433`, `model: Govee-Water`, and include its device identifier. For example:

  ```json
  {
    "state_topic": "rtl_433/your-instance/devices/Govee-Water/8098/detect_wet",
    "unique_id": "Govee-Water-8098-moisture",
    "device": {
      "identifiers": ["Govee-Water-8098"],
      "name": "Govee-Water-8098",
      "model": "Govee-Water",
      "manufacturer": "rtl_433"
    }
  }
  ```

## Installation

1. Install the `govee_water_leak_monitor` directory under `custom_components` (or install through HACS once the repository is published there).
2. Restart Home Assistant.
3. Add **Govee Water Leak Monitor** from Settings → Devices & services.
4. Configure notification targets and reminder frequency in the integration options.
5. Discovered sensors appear automatically as entities on their existing rtl_433 devices.

## MQTT fields used

| Field | Behavior |
|---|---|
| `detect_wet=1` | Starts a leak episode |
| `detect_wet=0` | Clears the active leak episode |
| `battery_mV` | Updates battery voltage |
| `battery_ok` | Preserves the raw decoder value as a diagnostic |
| `event` | Updates the last event diagnostic |

The `event` field is informational only. Wet/dry state is determined exclusively by `detect_wet`, because rtl_433 publishes these fields as separate MQTT messages.

## Device matching

The integration reads the identifiers from the rtl_433 MQTT discovery payload and looks up the corresponding Home Assistant MQTT device. Because Home Assistant scopes device identifiers to config entries, the integration links its entity-registry entries directly to the existing MQTT device rather than trying to register a second device with the same identifier. If the MQTT device is deleted, monitor entities become unavailable; rediscovery of the same sensor reattaches them without losing monitor state.
