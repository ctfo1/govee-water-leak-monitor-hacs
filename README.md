# Govee Water Leak Monitor

A Home Assistant custom integration for monitoring existing Govee (and other compatible) water-leak `binary_sensor` entities. It replaces helper-heavy automations with GUI configuration and integration-owned persistent state.

## Features

- Empty initial setup; add sensors through **Settings → Devices & services → Govee Water Leak Monitor → Configure**.
- Entity picker is filtered to `binary_sensor` entities with the **Moisture** device class, which is Home Assistant's wet/dry classification for water leak sensors.
- Optional MQTT topic per sensor refreshes the last-wet timestamp and updates an active alert without sending another initial email.
- One HA device per configured sensor.
- Initial email on a new leak episode; configurable periodic email reminders while wet and unacknowledged.
- Selectable SMTP email notify entities and selectable registered `notify` services for mobile notifications.
- Mobile notifications use a stable tag and include an Acknowledge action.
- Acknowledgment suppresses email reminders only. Persistent/mobile notifications remain until recovery.
- Recovery clears persistent/mobile notifications and sends a recovery email.
- Active alerts are restored after restart without sending another initial email.
- Last-wet time and acknowledgment are stored by the integration; no `input_boolean` or `input_datetime` helpers are created.

## Install manually

Copy `custom_components/govee_water_leak_monitor` into `/config/custom_components/`, restart Home Assistant, then add **Govee Water Leak Monitor** under **Settings → Devices & services → Add integration**.

For HACS, publish this repository and add it as a custom integration repository. The manifest is prefilled for the `ctfo1/govee-water-leak-monitor` repository; change the owner or repository URLs if you choose a different GitHub location. The integration includes local `brand/icon.png`, `icon@2x.png`, and `logo.png` assets for Home Assistant branding.

## Configure

1. Open the integration's **Configure** menu.
2. Set the reminder interval. Select one or more SMTP notify entities for email and one or more registered `notify` services for mobile alerts.
3. Choose **Add water leak sensor**, give it a name, and select a binary sensor with device class **Moisture**.
4. Optionally provide an MQTT topic and wet payload (default `1`) for repeated wet-event timestamps.

The MQTT integration must be configured in Home Assistant if any sensor uses an MQTT topic. Without MQTT, leak start, reminders, acknowledgment, recovery, and startup restoration still work. The last-wet timestamp is set when the HA binary sensor transitions to wet.

## Entities

Each configured sensor gets a leak-active binary sensor, acknowledgment diagnostic binary sensor, last-wet and last-alert timestamp sensors, plus Acknowledge Leak, Reset Acknowledgment, and Test Notification buttons. The integration references the original water-sensor entity; it does not create a duplicate wet/dry sensor.

## Compatibility and migration

Version 0.2.1 refreshes the branding with a simpler, solid-blue water-droplet icon. Version 0.2.0 changes the integration domain from `water_leak_alerts` to `govee_water_leak_monitor`. If you installed the earlier 0.1.0 test package, remove that integration and its old custom-component folder before installing this renamed version. The new domain does not automatically migrate the old config entry.

## Development status

This is an early test release. Python syntax and package metadata should be validated before live use. Test on a backup or staging instance before relying on it for leak protection.
