"""Govee Water Leak Monitor integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DEFAULT_OPTIONS, DOMAIN, PLATFORMS
from .coordinator import WaterLeakCoordinator


def _options(entry: ConfigEntry) -> dict:
    """Return options with defaults for older entries."""
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
