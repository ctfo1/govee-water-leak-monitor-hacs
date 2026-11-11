"""Diagnostic sensors for discovered Govee water sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util, slugify

from .entity import WaterLeakEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Register diagnostic entities for discovered sensors."""
    coordinator = hass.data["govee_water_leak_monitor"][entry.entry_id]

    def create(configs):
        entities = []
        for config in configs:
            entities.extend((
                LastBatteryReportSensor(coordinator, config),
                LastWetSensor(coordinator, config),
                LeakStartedSensor(coordinator, config),
                LastNotificationSensor(coordinator, config),
                LastEventSensor(coordinator, config),
            ))
        return entities

    coordinator.register_entity_adder("sensor", async_add_entities, create)


class _TimestampSensor(WaterLeakEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config, description, key):
        self.key = key
        super().__init__(coordinator, config, description)

    @property
    def native_value(self):
        value = self.coordinator.sensor_state(self.sensor_id).get(self.key)
        return dt_util.parse_datetime(value) if value else None


class LastBatteryReportSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Battery Report", "last_battery_report")


class LastWetSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Wet Event", "last_wet")


class LeakStartedSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Leak Started", "leak_started")
        # Preserve the existing unique ID so HA keeps the entity registry row
        # and history while giving automation-facing IDs a stable prefix.
        self._attr_unique_id = f"{self.sensor_id}_leak_started"
        device_name = config.get("device_name") or config.get("sensor_number") or self.sensor_id
        self._attr_suggested_object_id = (
            f"govee_water_leak_monitor_{slugify(device_name)}_leak_started"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return
        target_entity_id = (
            f"sensor.govee_water_leak_monitor_"
            f"{slugify(self.sensor_config.get('device_name') or self.sensor_id)}_leak_started"
        )
        if entry.entity_id == target_entity_id:
            return
        try:
            registry.async_update_entity(
                entry.entity_id, new_entity_id=target_entity_id
            )
        except ValueError:
            # Do not prevent the integration from loading if another entity
            # already owns the requested object ID.
            _LOGGER.warning(
                "Could not migrate %s to %s because that entity ID is already in use",
                entry.entity_id, target_entity_id,
            )


class LastNotificationSensor(_TimestampSensor):
    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Notification", "last_notification")
        # Preserve the existing unique ID across the display-name change.
        self._attr_unique_id = f"{self.sensor_id}_last_alert"


class LastEventSensor(WaterLeakEntity, SensorEntity):
    """Most recent rtl_433 event label."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config):
        super().__init__(coordinator, config, "Last Event")

    @property
    def native_value(self):
        return self.coordinator.sensor_state(self.sensor_id).get("last_event")
