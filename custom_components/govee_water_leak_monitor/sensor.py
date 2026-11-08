"""Diagnostic sensors for discovered Govee water sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Register diagnostic entities for discovered sensors."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        entities = []
        for config in configs:
            entities.extend((
                BatteryVoltageSensor(coordinator, config),
                BatteryOkSensor(coordinator, config),
                LastBatteryReportSensor(coordinator, config),
                LastWetSensor(coordinator, config),
                LastAlertSensor(coordinator, config),
                LastEventSensor(coordinator, config),
            ))
        return entities

    coordinator.register_entity_adder("sensor", async_add_entities, create)


class BatteryVoltageSensor(WaterLeakEntity, SensorEntity):
    """Most recently reported battery voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = "mV"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Battery Voltage")

    @property
    def native_value(self):
        return self.coordinator.sensor_state(self.sensor_id).get("battery_mv")


class BatteryOkSensor(WaterLeakEntity, SensorEntity):
    """Raw battery_ok value reported by rtl_433 (decoder-specific)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Battery OK (raw)")

    @property
    def native_value(self):
        return self.coordinator.sensor_state(self.sensor_id).get("battery_ok")


class _TimestampSensor(WaterLeakEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config, description, key):
        self.key = key
        super().__init__(coordinator, config, description)

    @property
    def native_value(self):
        value = self.coordinator.sensor_state(self.sensor_id).get(self.key)
        return dt_util.parse_datetime(value) if value else None


class LastBatteryReportSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Battery Report", "last_battery_report")


class LastWetSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Wet Event", "last_wet")


class LastAlertSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Alert", "last_alert")


class LastEventSensor(WaterLeakEntity, SensorEntity):
    """Most recent rtl_433 event label."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Event")

    @property
    def native_value(self):
        return self.coordinator.sensor_state(self.sensor_id).get("last_event")
