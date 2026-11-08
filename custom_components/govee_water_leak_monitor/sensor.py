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
                LastBatteryReportSensor(coordinator, config),
                LastWetSensor(coordinator, config),
                LeakStartedSensor(coordinator, config),
                LastNotificationSensor(coordinator, config),
                LastEventSensor(coordinator, config),
            ))
        return entities

    coordinator.register_entity_adder("sensor", async_add_entities, create)


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


class LeakStartedSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Leak Started", "leak_started")
        # Keep the existing unique ID so the entity registry/history survive
        # the display-name change.
        self._attr_unique_id = f"{self.sensor_id}_leak_started"


class LastNotificationSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Notification", "last_notification")
        # Preserve the existing unique ID across the display-name change.
        self._attr_unique_id = f"{self.sensor_id}_last_alert"


class LastEventSensor(WaterLeakEntity, SensorEntity):
    """Most recent rtl_433 event label."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Event")

    @property
    def native_value(self):
        return self.coordinator.sensor_state(self.sensor_id).get("last_event")
