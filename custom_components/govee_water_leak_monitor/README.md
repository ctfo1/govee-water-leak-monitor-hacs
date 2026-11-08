# Govee Water Leak Monitor

Home Assistant custom integration for Govee Water sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433) and published through Home Assistant MQTT.

See the repository [README](https://github.com/ctfo1/govee-water-leak-monitor#readme) for installation, requirements, entity behavior, and Lovelace card configuration.

## Lovelace card

The standalone card is `custom:govee-water-leak-card`. Configure one card per moisture sensor:

```yaml
type: custom:govee-water-leak-card
entity: binary_sensor.your_govee_water_sensor
```

The card displays wet/dry status, the last-detected time when known, and battery level when available. It shows acknowledgment and Reset to Dry controls while wet. It does not display Test Notification, Last Leak Started, Last Battery Report, or Last Notification.
