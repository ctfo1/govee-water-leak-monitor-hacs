"""Leak-management and test buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Register buttons for discovered sensors."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        entities = []
        for config in configs:
            entities.extend((
                AcknowledgeButton(coordinator, config),
                ResetToDryButton(coordinator, config),
                ResetAcknowledgmentButton(coordinator, config),
                TestNotificationButton(coordinator, config),
            ))
        return entities

    coordinator.register_entity_adder("button", async_add_entities, create)


class AcknowledgeButton(WaterLeakEntity, ButtonEntity):
    """Acknowledge the active leak and stop email reminders."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Acknowledge Leak")

    @property
    def available(self) -> bool:
        data = self.coordinator.sensor_state(self.sensor_id)
        return bool(data.get("active") and not data.get("acknowledged"))

    async def async_press(self):
        await self.coordinator.async_acknowledge(self.sensor_id)


class ResetToDryButton(WaterLeakEntity, ButtonEntity):
    """Publish dry to the sensor's actual MQTT state topic."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Reset to Dry")

    @property
    def available(self) -> bool:
        return bool(self.coordinator.sensor_state(self.sensor_id).get("active"))

    async def async_press(self):
        await self.coordinator.async_reset_to_dry(self.sensor_id)


class ResetAcknowledgmentButton(WaterLeakEntity, ButtonEntity):
    """Re-enable reminders for an active leak."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Reset Acknowledgment")

    @property
    def available(self) -> bool:
        data = self.coordinator.sensor_state(self.sensor_id)
        return bool(data.get("active") and data.get("acknowledged"))

    async def async_press(self):
        await self.coordinator.async_reset_acknowledgment(self.sensor_id)


class TestNotificationButton(WaterLeakEntity, ButtonEntity):
    """Send a test email and mobile notification."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Test Notification")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self):
        await self.coordinator.async_test_notifications(self.sensor_id)
