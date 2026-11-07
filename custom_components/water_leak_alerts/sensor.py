"""Timestamp sensors for Water Leak Alerts."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["water_leak_alerts"][entry.entry_id]
    entities = []
    for config in coordinator.sensors:
        entities.extend([LastWetSensor(coordinator, config), LastAlertSensor(coordinator, config)])
    async_add_entities(entities)


class _TimestampSensor(WaterLeakEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        value = self.coordinator.sensor_state(self.sensor_id).get(self.key)
        return dt_util.parse_datetime(value) if value else None


class LastWetSensor(_TimestampSensor):
    """Most recent wet event timestamp."""

    key = "last_wet"

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Wet Event")


class LastAlertSensor(_TimestampSensor):
    """Most recent alert start timestamp."""

    key = "last_alert"

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Alert")
