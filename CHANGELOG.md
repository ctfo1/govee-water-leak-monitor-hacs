# Changelog

## 0.3.0

- Replaced manual moisture-entity setup with automatic rtl_433 Govee Water MQTT discovery.
- Matched discovered sensors to the existing MQTT device using the rtl_433 discovery device identifier; no separate device is created by this integration.
- Switched leak state to the `detect_wet` MQTT field (`1` wet, `0` dry).
- Changed Reset to Dry to publish `0` to the sensor's real MQTT state topic, allowing the existing MQTT moisture entity to update too.
- Prevented repeated wet packets from starting duplicate leak episodes or duplicate notifications.
- Added battery voltage, raw battery_ok, last battery report, and last rtl_433 event diagnostics.
- Preserved notification targets, reminder interval, acknowledgment, and test notification behavior.
- Migrates existing v0.2.x config entries and retains their notification settings while discarding manual sensor selections.
