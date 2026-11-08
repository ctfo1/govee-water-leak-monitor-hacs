# Govee Water Leak Monitor

Home Assistant custom integration for Govee Water sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433) and published through Home Assistant MQTT.

## Features

- Automatically discovers rtl_433 `Govee-Water` sensors through Home Assistant MQTT discovery.
- Adds monitor entities to the existing rtl_433 MQTT device; it does not create a separate device.
- Uses the existing rtl_433 moisture binary sensor / `detect_wet` MQTT state as the authoritative wet/dry condition.
- Sends email, mobile, and persistent notifications when a new continuous leak episode starts.
- Repeated `detect_wet=1` packets update Last Wet Event without generating duplicate initial alerts.
- Provides a Leak Acknowledged switch, Reset to Dry button, and Test Notification button.
- The Leak Acknowledged switch stops reminders while the current leak remains active; it resets automatically when the sensor reports dry.
- Reset to Dry publishes `0` to the sensor's actual `detect_wet` topic so the existing MQTT moisture entity follows the same state.
- Exposes Last Battery Report, Last Wet Event, Last Leak Started, Last Notification, and Last Event.
- Does not duplicate battery percentage, battery voltage, or signal diagnostics already supplied by rtl_433.
- Reads the existing MQTT device's current name and assigned area for notifications.
- If the MQTT device is deleted, monitor entities become unavailable. Rediscovery reattaches them without losing monitor state or settings.

## Requirements

- Home Assistant MQTT integration configured and running.
- rtl_433 publishes topics in the form `rtl_433/<instance>/devices/Govee-Water/<sensor_id>/<field>`.
- MQTT discovery for the moisture entity identifies the device with `manufacturer: rtl_433`, `model: Govee-Water`, and a device identifier.

## Installation

1. Back up the current integration.
2. Replace `custom_components/govee_water_leak_monitor` with the directory from this release.
3. Restart Home Assistant.
4. Add **Govee Water Leak Monitor** if it is not already configured.
5. Configure notification targets and reminder frequency in the integration options.

## Entity behavior

| Entity | Meaning |
|---|---|
| Existing rtl_433 Water Sensor | Authoritative wet/dry state |
| Leak Acknowledged | Toggle acknowledgment for the current active leak |
| Last Wet Event | Timestamp of the most recent `detect_wet=1` report |
| Last Leak Started | Timestamp when the most recent continuous leak episode began; retained after dry and replaced when a new leak episode starts |
| Last Battery Report | Timestamp of the `event=Battery Report` message |
| Last Notification | Timestamp of the most recent successfully sent notification (including alerts, reminders, recovery, and test notifications) |
| Last Event | Most recent rtl_433 event label |
| Reset to Dry | Publishes `0` to the sensor's actual MQTT state topic |
| Test Notification | Sends a test notification without changing leak state |

Battery percentage, battery voltage, and signal measurements remain provided by rtl_433.
