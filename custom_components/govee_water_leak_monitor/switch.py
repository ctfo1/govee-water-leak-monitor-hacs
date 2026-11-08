"""Leak acknowledgment switch."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import WaterLeakEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Register acknowledgment switches for discovered sensors."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        return [AcknowledgedSwitch(coordinator, config) for config in configs]

    coordinator.register_entity_adder("switch", async_add_entities, create)


class AcknowledgedSwitch(WaterLeakEntity, SwitchEntity):
    """Toggle acknowledgment for the current leak episode."""

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Leak Acknowledged")

    @property
    def is_on(self):
        return bool(self.coordinator.sensor_state(self.sensor_id).get("acknowledged"))

    @property
    def available(self) -> bool:
        return self.device_available

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_acknowledged(self.sensor_id, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_acknowledged(self.sensor_id, False)
