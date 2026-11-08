"""Leak and acknowledgment binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Register entities for sensors discovered from rtl_433 MQTT discovery."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        entities = []
        for config in configs:
            entities.extend((LeakActiveBinarySensor(coordinator, config), AcknowledgedBinarySensor(coordinator, config)))
        return entities

    coordinator.register_entity_adder("binary_sensor", async_add_entities, create)


class LeakActiveBinarySensor(WaterLeakEntity, BinarySensorEntity):
    """Indicate whether a leak episode is active."""

    _attr_device_class = "moisture"

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Leak Alert Active")

    @property
    def is_on(self):
        return self.coordinator.sensor_state(self.sensor_id).get("active", False)


class AcknowledgedBinarySensor(WaterLeakEntity, BinarySensorEntity):
    """Indicate whether the current leak episode is acknowledged."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Acknowledged")

    @property
    def is_on(self):
        return self.coordinator.sensor_state(self.sensor_id).get("acknowledged", False)
