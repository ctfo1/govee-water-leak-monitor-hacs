"""Leak-management and test buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Register buttons for discovered sensors."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        entities = []
        for config in configs:
            entities.extend((
                ResetToDryButton(coordinator, config),
                TestNotificationButton(coordinator, config),
            ))
        return entities

    coordinator.register_entity_adder("button", async_add_entities, create)


class ResetToDryButton(WaterLeakEntity, ButtonEntity):
    """Publish dry to the sensor's actual MQTT state topic."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Reset to Dry")

    @property
    def available(self) -> bool:
        # Keep the command available even while the rtl_433 device is absent.
        # The coordinator retains the topic/configuration and MQTT publish
        # failures are handled by Home Assistant's service layer.
        return True

    async def async_press(self):
        await self.coordinator.async_reset_to_dry(self.sensor_id)


class TestNotificationButton(WaterLeakEntity, ButtonEntity):
    """Send a test email and mobile notification."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Test Notification")

    @property
    def available(self) -> bool:
        return self.device_available

    async def async_press(self):
        await self.coordinator.async_test_notifications(self.sensor_id)
