# Govee Water Leak Monitor

Home Assistant custom integration for Govee Water sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433) and published through Home Assistant MQTT.

## Features

- Automatically discovers rtl_433 `Govee-Water` sensors through Home Assistant MQTT discovery.
- Adds monitor entities to the existing rtl_433 MQTT device; it does not create a separate device.
- Uses the existing rtl_433 moisture binary sensor / `detect_wet` MQTT state as the authoritative wet/dry condition.
- Sends notifications when a new continuous leak episode starts and supports reminders and acknowledgment.
- Repeated `detect_wet=1` packets update Last Wet Event without generating duplicate initial alerts.
- Provides a Leak Acknowledged switch and Reset to Dry button.
- Reset to Dry publishes `0` to the sensor's actual `detect_wet` topic so the existing MQTT moisture entity follows the same state.
- Exposes Last Wet Event, Last Leak Started, Last Battery Report, Last Notification, and Last Event as integration entities.
- Does not duplicate battery percentage, battery voltage, or signal diagnostics already supplied by rtl_433.
- Reads the existing MQTT device's current name and assigned area for notifications.
- If the MQTT device is deleted, monitor entities become unavailable. Rediscovery reattaches them without losing monitor state or settings.
- Includes a standalone Lovelace card with automatic discovery of related monitor entities and battery level.

## Requirements

- Home Assistant MQTT integration configured and running.
- rtl_433 publishes topics in the form `rtl_433/<instance>/devices/Govee-Water/<sensor_id>/<field>`.
- MQTT discovery for the moisture entity identifies the device with `manufacturer: rtl_433`, `model: Govee-Water`, and a device identifier.

## Installation

### HACS

1. Add this repository as a custom repository in HACS (Integration category), if it is not already added.
2. Install **Govee Water Leak Monitor**.
3. Restart Home Assistant.
4. Add the integration if it is not already configured.
5. Configure notification targets and reminder frequency in the integration options.

### Manual

1. Copy `custom_components/govee_water_leak_monitor` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration if it is not already configured.

## Lovelace card

The integration includes a standalone Lovelace card (no Mushroom, stack-in-card, card-mod, or other custom-card dependencies). In the default storage-mode dashboard configuration, the integration serves and registers the card automatically. If Lovelace is configured in YAML mode, add this resource manually:

```yaml
url: /govee_water_leak_monitor/govee-water-leak-card.js?v=0.3.9
type: module
```

Add a single card to display all discovered Govee leak monitors, each in its own compact section:

```yaml
type: custom:govee-water-leak-card
```

The card displays the sensor name, wet/dry state, water-last-detected time (only after a wet report has been received), and battery level when known. While wet, it displays the acknowledgment and Reset to Dry controls. It intentionally omits Test Notification and diagnostic timestamp details. The card automatically discovers the integration-managed moisture sensors and their related battery, acknowledgment, and reset entities. No per-sensor selection is required.

## Entity behavior

| Entity | Meaning |
|---|---|
| Existing rtl_433 Water Sensor | Authoritative wet/dry state |
| Leak Acknowledged | Toggle acknowledgment for the current active leak |
| Last Wet Event | Timestamp of the most recent `detect_wet=1` report |
| Last Leak Started | Timestamp when the most recent continuous leak episode began; retained after dry and replaced when a new leak episode starts |
| Last Battery Report | Timestamp of the `event=Battery Report` message |
| Last Notification | Timestamp of the most recent successfully sent notification |
| Last Event | Most recent rtl_433 event label |
| Reset to Dry | Publishes `0` to the sensor's actual MQTT state topic |
| Test Notification | Sends a test notification without changing leak state |

Battery percentage, battery voltage, and signal measurements remain provided by rtl_433.
