# Changelog

## 0.3.3
- Renamed Last Alert to Last Notification and update it whenever an integration notification is successfully sent.
- Renamed Leak Started to Last Leak Started; retain its timestamp after the sensor reports dry, replacing it only when a new leak episode starts.
- Preserve existing entity registry IDs and migrate the prior Last Alert timestamp so existing entity history and stored data are retained.


## 0.3.1

- Fixed device association: monitor entities are now linked directly to the existing rtl_433 MQTT device instead of registering a second device. This accounts for Home Assistant scoping device identifiers to config entries.
- Migrates existing v0.3.0 monitor entities onto their corresponding MQTT devices and removes empty duplicate monitor devices owned by this integration.
- If an MQTT device is deleted, monitor entities become unavailable without creating a replacement device. Rediscovery of the same sensor reattaches existing entities to the newly registered MQTT device while preserving monitor state and settings.
- Moved all four action buttons into the Controls group; none are classified as Configuration entities.
- Fixed notifications for devices without an assigned area: the device name is shown once and the message no longer contains a fabricated location.
- Test and recovery notifications now resolve the current device name dynamically.

## 0.3.0

- Replaced manual moisture-entity setup with automatic rtl_433 Govee Water MQTT discovery.
- Matched discovered sensors to the existing MQTT device using the rtl_433 discovery device identifier; no separate device is created by this integration.
- Switched leak state to the `detect_wet` MQTT field (`1` wet, `0` dry).
- Changed Reset to Dry to publish `0` to the sensor's real MQTT state topic, allowing the existing MQTT moisture entity to update too.
- Prevented repeated wet packets from starting duplicate leak episodes or duplicate notifications.
- Added battery voltage, raw battery_ok, last battery report, and last rtl_433 event diagnostics.
- Preserved notification targets, reminder interval, acknowledgment, and test notification behavior.
- Migrates existing v0.2.x config entries and retains their notification settings while discarding manual sensor selections.

## 0.3.4

- Add a standalone Lovelace card, with no Mushroom, stack-in-card, or card-mod dependencies.
- Automatically serve and register the card as a Lovelace resource in storage mode; document manual resource registration for YAML mode.
- Support one card per sensor, discovering related monitor and rtl_433 battery entities through their shared device association.
