"""Govee Water Leak Monitor integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_OPTIONS, DOMAIN, PLATFORMS
from .coordinator import WaterLeakCoordinator


def _options(entry: ConfigEntry) -> dict:
    """Return global options with defaults for older entries."""
    return {**DEFAULT_OPTIONS, **entry.options}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (config-entry only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Govee Water Leak Monitor config entry."""
    coordinator = WaterLeakCoordinator(hass, entry, _options(entry))
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Start discovery after platforms register their dynamic entity adders.
    await coordinator.async_start_discovery()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy manually configured sensors to automatic discovery."""
    if entry.version > 2:
        return False
    if entry.version < 2:
        old = entry.options
        entity_registry = er.async_get(hass)
        await entity_registry.async_wait_loaded()
        device_registry = dr.async_get(hass)
        await device_registry.async_wait_loaded()

        # If the old integration device had a user-assigned name or area,
        # preserve it on the matching rtl_433 device when that device has no
        # corresponding user setting yet. The MQTT entity is the bridge
        # between the old manually selected entity and the existing device.
        for sensor in old.get("sensors", []):
            old_sensor_id = sensor.get("id")
            source_entity_id = sensor.get("entity_id")
            if not old_sensor_id or not source_entity_id:
                continue
            old_device = device_registry.async_get_device_by_identifier(
                (DOMAIN, old_sensor_id), entry.entry_id
            )
            source_entity = entity_registry.async_get(source_entity_id)
            mqtt_device = (
                device_registry.async_get(source_entity.device_id)
                if source_entity and source_entity.device_id else None
            )
            if old_device and mqtt_device:
                changes = {}
                if old_device.area_id and not mqtt_device.area_id:
                    changes["area_id"] = old_device.area_id
                if old_device.name_by_user and not mqtt_device.name_by_user:
                    changes["name_by_user"] = old_device.name_by_user
                if changes:
                    device_registry.async_update_device(mqtt_device.id, **changes)

        # Remove entities/devices created by the old manual-monitoring model.
        # The rtl_433 MQTT entities and their device belong to the mqtt entry.
        entity_registry.async_clear_config_entry(entry.entry_id)
        device_registry.async_clear_config_entry(entry.entry_id, DOMAIN)

        options = {
            "reminder_interval": old.get("reminder_interval", DEFAULT_OPTIONS["reminder_interval"]),
            "email_targets": old.get("email_targets", []),
            "mobile_targets": old.get("mobile_targets", []),
        }
        hass.config_entries.async_update_entry(entry, version=2, options=options)
    return True
