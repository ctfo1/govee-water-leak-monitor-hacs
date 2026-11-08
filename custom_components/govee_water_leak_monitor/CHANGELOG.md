# Changelog

## 0.3.2

- Replaced the separate Acknowledge Leak and Reset Acknowledgment buttons with one Leak Acknowledged switch. Turning it on acknowledges the active episode; turning it off re-enables reminders. Acknowledgment resets automatically when the sensor reports dry.
- Removed Leak Alert Active; the existing rtl_433 moisture binary sensor remains the authoritative wet/dry state.
- Last Wet Event now updates on every `detect_wet=1` report, including repeated reports during an ongoing leak.
- Added Leak Started to record the beginning of the current continuous leak episode; it clears when the sensor reports dry.
- Retained Last Battery Report and timestamp it from the rtl_433 `event=Battery Report` message.
- Removed duplicate Battery Voltage and Battery OK entities because rtl_433 already supplies battery measurements.
- Removed obsolete v0.3.0/v0.3.1 entities from the entity registry during upgrade.
- Preserved the v0.3.1 device-association, notification formatting, and deleted-device recovery behavior.

## 0.3.1

- Fixed device association: monitor entities are linked directly to the existing rtl_433 MQTT device instead of registering a second device.
- Migrates existing v0.3.0 monitor entities onto their corresponding MQTT devices and removes empty duplicate monitor devices owned by this integration.
- If an MQTT device is deleted, monitor entities become unavailable without creating a replacement device. Rediscovery reattaches existing entities while preserving monitor state and settings.
- Moved action buttons into Controls and fixed notifications for devices without an assigned area.

## 0.3.0

- Replaced manual moisture-entity setup with automatic rtl_433 Govee Water MQTT discovery.
- Uses `detect_wet` as the authoritative wet/dry state and publishes `0` to that topic for Reset to Dry.
- Preserves notification targets, reminder interval, acknowledgment, and test notification behavior.
