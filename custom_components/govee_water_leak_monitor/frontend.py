"""Serve and register the bundled Govee Lovelace card."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
URL_PATH = f"/{DOMAIN}/govee-water-leak-card.js"
RESOURCE_URL = f"{URL_PATH}?v=0.3.7"


async def async_register_static_card(hass: HomeAssistant) -> None:
    """Expose the card JavaScript from the integration package."""
    path = Path(__file__).parent / "www"
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_PATH, str(path / "govee-water-leak-card.js"), False)]
        )
    except RuntimeError:
        # A second config-entry setup should not fail because the route exists.
        _LOGGER.debug("Govee card static path was already registered")


async def async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Add or update the card resource when Lovelace uses storage mode."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.warning(
            "Govee card is available at %s but Lovelace was not loaded; add it as a dashboard resource",
            RESOURCE_URL,
        )
        return

    if getattr(lovelace, "mode", "storage") == "yaml":
        _LOGGER.info(
            "Lovelace is in YAML mode; add resource %s with type 'module' to your lovelace resources",
            RESOURCE_URL,
        )
        return

    resources = getattr(lovelace, "resources", None)
    if resources is None:
        _LOGGER.warning("Lovelace resource manager is unavailable; add %s manually", RESOURCE_URL)
        return

    async def _register(_now=None):
        if not getattr(resources, "loaded", False):
            async_call_later(hass, 2, lambda now: hass.async_create_task(_register(now)))
            return
        try:
            existing = next(
                (item for item in resources.async_items() if item.get("url", "").split("?", 1)[0] == URL_PATH),
                None,
            )
            if existing:
                if existing.get("url") != RESOURCE_URL:
                    await resources.async_update_item(
                        existing["id"], {"res_type": "module", "url": RESOURCE_URL}
                    )
            else:
                await resources.async_create_item({"res_type": "module", "url": RESOURCE_URL})
        except Exception:  # noqa: BLE001 - card registration must not block integration setup
            _LOGGER.exception(
                "Could not register the Govee Lovelace card automatically; add %s as a module resource",
                RESOURCE_URL,
            )

    await _register()
