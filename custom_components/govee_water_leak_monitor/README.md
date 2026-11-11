# Govee Water Leak Monitor

Home Assistant custom integration for Govee Water sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433) and published through Home Assistant MQTT.

See the repository [README](https://github.com/ctfo1/govee-water-leak-monitor#readme) for installation, requirements, entity behavior, and Lovelace card configuration.

## Lovelace card

The aggregate card is `custom:govee-water-leak-card`. Add one card to display every discovered Govee leak monitor in its own compact section:

```yaml
type: custom:govee-water-leak-card
```

The card displays the existing rtl_433 device name (without the moisture entity's trailing “Water Sensor” label), wet/dry status, the last-detected time when known, and battery level when available. It shows acknowledgment and Reset to Dry controls while wet. It does not display Test Notification, Last Leak Started, Last Battery Report, or Last Notification.

The card automatically discovers integration-managed moisture sensors and their related battery, acknowledgment, and Reset to Dry entities. No per-sensor selection is required.
