"""Base entities attached to the existing rtl_433 MQTT device."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
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
        # This identifier is supplied by rtl_433's MQTT discovery config.
        # No name/manufacturer/model is supplied here, so the existing MQTT
        # device's metadata and user-assigned area remain authoritative.
        self._attr_device_info = DeviceInfo(
            identifiers={("mqtt", sensor_config["device_identifier"])},
        )

    @property
    def available(self) -> bool:
        """Keep controls (especially Test Notification) usable when dry."""
        return True

    async def async_added_to_hass(self) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_connect

        self.async_on_remove(async_dispatcher_connect(
            self.coordinator.hass,
            f"{SIGNAL_UPDATE}_{self.coordinator.entry.entry_id}_{self.sensor_id}",
            self._handle_update,
        ))

    def _handle_update(self) -> None:
        """Schedule a state refresh safely on Home Assistant's event loop."""
        self.coordinator.hass.add_job(self.async_write_ha_state)
