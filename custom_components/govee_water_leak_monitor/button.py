"""Buttons for Govee Water Leak Monitor."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]
    entities = []
    for config in coordinator.sensors:
        entities.extend([
            AcknowledgeButton(coordinator, config),
            ResetAcknowledgmentButton(coordinator, config),
            TestNotificationButton(coordinator, config),
        ])
    async_add_entities(entities)


class AcknowledgeButton(WaterLeakEntity, ButtonEntity):
    """Acknowledge the active leak and stop email reminders."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Acknowledge Leak")

    async def async_press(self):
        await self.coordinator.async_acknowledge(self.sensor_id)


class ResetAcknowledgmentButton(WaterLeakEntity, ButtonEntity):
    """Re-enable email reminders for an active leak."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Reset Acknowledgment")

    async def async_press(self):
        await self.coordinator.async_reset_acknowledgment(self.sensor_id)


class TestNotificationButton(WaterLeakEntity, ButtonEntity):
    """Send a test email and mobile notification."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Test Notification")

    async def async_press(self):
        await self.coordinator.async_test_notifications(self.sensor_id)
