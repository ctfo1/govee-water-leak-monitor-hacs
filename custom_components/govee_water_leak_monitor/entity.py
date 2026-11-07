"""Base entity for configured water leak sensors."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_ENTITY_ID, DOMAIN, SIGNAL_UPDATE


class WaterLeakEntity(Entity):
    """Base class for one monitored water sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, sensor_config: dict, description: str) -> None:
        self.coordinator = coordinator
        self.sensor_config = sensor_config
        self.sensor_id = sensor_config["id"]
        self._attr_name = description
        self._attr_unique_id = f"{self.sensor_id}_{description.lower().replace(' ', '_')}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.sensor_id)},
            name=sensor_config["name"],
            manufacturer="Govee",
            model="Monitored water sensor",
        )

    @property
    def available(self) -> bool:
        state = self.coordinator.hass.states.get(self.sensor_config[CONF_ENTITY_ID])
        return state is not None and state.state not in ("unknown", "unavailable")

    async def async_added_to_hass(self) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_connect
        self.async_on_remove(async_dispatcher_connect(
            self.coordinator.hass,
            f"{SIGNAL_UPDATE}_{self.coordinator.entry.entry_id}_{self.sensor_id}",
            self._handle_update,
        ))

    def _handle_update(self) -> None:
        """Refresh entity state safely, even if a signal arrives off-loop."""
        # Dispatcher callbacks can be invoked from a worker thread when an
        # integration callback crosses thread boundaries. add_job is the
        # thread-safe Home Assistant API for scheduling work on the event loop.
        self.coordinator.hass.add_job(self.async_write_ha_state)
