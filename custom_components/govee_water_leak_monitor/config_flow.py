"""Config and options flows for Govee Water Leak Monitor."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EMAIL_TARGETS,
    CONF_MOBILE_TARGETS,
    CONF_REMINDER_INTERVAL,
    DEFAULT_OPTIONS,
    DOMAIN,
)


class GoveeWaterLeakMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the integration; Govee sensors are discovered automatically."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Require MQTT and create a single integration entry."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if "mqtt" not in self.hass.config.components:
            return self.async_abort(reason="mqtt_not_loaded")
        if user_input is not None:
            return self.async_create_entry(
                title="Govee Water Leak Monitor", data={}, options=dict(DEFAULT_OPTIONS)
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GoveeWaterLeakMonitorOptionsFlow()


class GoveeWaterLeakMonitorOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage notification targets and reminder frequency."""

    @property
    def options(self) -> dict[str, Any]:
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    async def async_step_init(self, user_input=None):
        return await self.async_step_settings(user_input)

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            options = dict(self.options)
            options.update(user_input)
            options[CONF_EMAIL_TARGETS] = self._as_list(user_input.get(CONF_EMAIL_TARGETS, []))
            options[CONF_MOBILE_TARGETS] = self._as_list(user_input.get(CONF_MOBILE_TARGETS, []))
            return self.async_create_entry(title="", data=options)

        schema = vol.Schema({
            vol.Required(
                CONF_REMINDER_INTERVAL,
                default=self.options[CONF_REMINDER_INTERVAL],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=1440, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_EMAIL_TARGETS,
                default=self._as_list(self.options[CONF_EMAIL_TARGETS]),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="notify", integration="smtp", multiple=True)
            ),
            vol.Optional(
                CONF_MOBILE_TARGETS,
                default=self._as_list(self.options[CONF_MOBILE_TARGETS]),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=self._mobile_notify_options(),
                    multiple=True,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })
        return self.async_show_form(step_id="settings", data_schema=schema)

    @staticmethod
    def _as_list(value):
        """Normalize legacy comma/newline-separated target settings."""
        if isinstance(value, str):
            return [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]
        return list(value or [])

    def _mobile_notify_options(self):
        """Return currently registered notify services for the dropdown."""
        services = self.hass.services.async_services().get("notify", {})
        return [
            {"value": f"notify.{name}", "label": f"notify.{name}"}
            for name in sorted(services)
            if name not in {"send_message", "notify"}
        ]
