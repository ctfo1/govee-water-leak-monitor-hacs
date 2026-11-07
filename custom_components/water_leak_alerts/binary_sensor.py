"""Binary sensors for Water Leak Alerts."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["water_leak_alerts"][entry.entry_id]
    entities = []
    for config in coordinator.sensors:
        entities.extend([LeakActiveBinarySensor(coordinator, config), AcknowledgedBinarySensor(coordinator, config)])
    async_add_entities(entities)


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
