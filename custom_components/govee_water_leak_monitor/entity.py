"""Base entities attached to the existing rtl_433 MQTT device."""
from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import SIGNAL_UPDATE


class WaterLeakEntity(Entity):
    """Base class for entities belonging to an rtl_433-discovered device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, sensor_config: dict, description: str) -> None:
        self.coordinator = coordinator
        self.sensor_config = sensor_config
        self.sensor_id = sensor_config["key"]
        self._attr_name = description
        self._attr_unique_id = f"{self.sensor_id}_{slugify(description)}"
        # Device association is assigned to the existing MQTT device in
        # async_added_to_hass; no DeviceInfo is supplied here because HA
        # scopes device identifiers to individual config entries.

    @property
    def device_available(self) -> bool:
        """Return whether the original rtl_433 MQTT device still exists."""
        device_id = self.sensor_config.get("device_id")
        return bool(device_id and self.coordinator.device_exists(device_id))

    @property
    def available(self) -> bool:
        """Keep entities usable while dry, but not after source-device deletion."""
        return self.device_available

    async def async_added_to_hass(self) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_connect

        # Link this entity to the existing MQTT device. Device identifiers are
        # unique only within a config entry; DeviceInfo with the MQTT
        # identifier would therefore create a duplicate integration device.
        target_device_id = self.sensor_config.get("device_id")
        entity_registry = er.async_get(self.coordinator.hass)
        registry_entry = entity_registry.async_get(self.entity_id)
        if (
            target_device_id
            and self.coordinator.device_exists(target_device_id)
            and registry_entry is not None
            and registry_entry.device_id != target_device_id
        ):
            old_device_id = registry_entry.device_id
            entity_registry.async_update_entity(
                self.entity_id, device_id=target_device_id
            )
            # Clean up the empty duplicate device left by v0.3.0, but only
            # when it belongs exclusively to this integration.
            if old_device_id:
                device_registry = dr.async_get(self.coordinator.hass)
                old_device = device_registry.async_get(old_device_id)
                remaining = er.async_entries_for_device(
                    entity_registry, old_device_id, include_disabled_entities=True
                )
                if (
                    old_device
                    and not remaining
                    and old_device.config_entries == {self.coordinator.entry.entry_id}
                ):
                    device_registry.async_remove_device(old_device_id)

        self.async_on_remove(async_dispatcher_connect(
            self.coordinator.hass,
            f"{SIGNAL_UPDATE}_{self.coordinator.entry.entry_id}_{self.sensor_id}",
            self._handle_update,
        ))

    def _handle_update(self) -> None:
        """Schedule a state refresh safely on Home Assistant's event loop."""
        self.coordinator.hass.add_job(self.async_write_ha_state)
