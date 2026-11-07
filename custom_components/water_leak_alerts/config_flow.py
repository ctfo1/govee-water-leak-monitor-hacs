"""Config and options flows for Water Leak Alerts."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_EMAIL_TARGETS,
    CONF_ENABLED,
    CONF_ENTITY_ID,
    CONF_MOBILE_TARGETS,
    CONF_MQTT_PAYLOAD,
    CONF_MQTT_TOPIC,
    CONF_REMINDER_INTERVAL,
    CONF_SENSOR_NAME,
    CONF_SENSORS,
    DEFAULT_MQTT_PAYLOAD,
    DEFAULT_OPTIONS,
    DOMAIN,
)


class WaterLeakConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the integration with no sensors preconfigured."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create an empty integration entry."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            return self.async_create_entry(
                title="Water Leak Alerts", data={}, options=dict(DEFAULT_OPTIONS)
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WaterLeakOptionsFlow()


class WaterLeakOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage global settings and individual sensors."""

    def __init__(self):
        self._selected_sensor: str | None = None

    @property
    def options(self) -> dict[str, Any]:
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "add_sensor", "manage_sensors"],
        )

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            options = dict(self.options)
            options.update(user_input)
            options[CONF_EMAIL_TARGETS] = user_input[CONF_EMAIL_TARGETS].strip()
            options[CONF_MOBILE_TARGETS] = user_input[CONF_MOBILE_TARGETS].strip()
            return self.async_create_entry(title="", data=options)
        schema = vol.Schema({
            vol.Required(CONF_REMINDER_INTERVAL, default=self.options[CONF_REMINDER_INTERVAL]): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_EMAIL_TARGETS, default=self.options[CONF_EMAIL_TARGETS]): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_MOBILE_TARGETS, default=self.options[CONF_MOBILE_TARGETS]): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        })
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_add_sensor(self, user_input=None):
        if user_input is not None:
            sensors = list(self.options[CONF_SENSORS])
            entity_id = user_input[CONF_ENTITY_ID]
            if any(item[CONF_ENTITY_ID] == entity_id for item in sensors):
                return self.async_show_form(
                    step_id="add_sensor", data_schema=self._add_sensor_schema(user_input),
                    errors={"base": "sensor_already_added"}
                )
            sensor_id = slugify(user_input[CONF_SENSOR_NAME]) or entity_id.split(".", 1)[-1]
            used_ids = {item["id"] for item in sensors}
            base_id, suffix = sensor_id, 2
            while sensor_id in used_ids:
                sensor_id = f"{base_id}_{suffix}"
                suffix += 1
            sensors.append({
                "id": sensor_id,
                CONF_SENSOR_NAME: user_input[CONF_SENSOR_NAME].strip(),
                CONF_ENTITY_ID: entity_id,
                CONF_MQTT_TOPIC: user_input.get(CONF_MQTT_TOPIC, "").strip(),
                CONF_MQTT_PAYLOAD: user_input.get(CONF_MQTT_PAYLOAD, DEFAULT_MQTT_PAYLOAD).strip(),
                CONF_ENABLED: True,
            })
            options = dict(self.options)
            options[CONF_SENSORS] = sensors
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(step_id="add_sensor", data_schema=self._add_sensor_schema())

    @staticmethod
    def _add_sensor_schema(defaults=None):
        defaults = defaults or {}
        return vol.Schema({
            vol.Required(CONF_SENSOR_NAME, default=defaults.get(CONF_SENSOR_NAME, "")): selector.TextSelector(),
            vol.Required(CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(CONF_MQTT_TOPIC, default=defaults.get(CONF_MQTT_TOPIC, "")): selector.TextSelector(),
            vol.Optional(CONF_MQTT_PAYLOAD, default=defaults.get(CONF_MQTT_PAYLOAD, DEFAULT_MQTT_PAYLOAD)): selector.TextSelector(),
        })

    async def async_step_manage_sensors(self, user_input=None):
        sensors = self.options[CONF_SENSORS]
        if not sensors:
            return self.async_abort(reason="no_sensors_configured")
        if user_input is not None:
            self._selected_sensor = user_input["sensor_id"]
            return await self.async_step_edit_sensor()
        return self.async_show_form(step_id="manage_sensors", data_schema=vol.Schema({
            vol.Required("sensor_id"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{"value": item["id"], "label": item[CONF_SENSOR_NAME]} for item in sensors],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ))
        }))

    async def async_step_edit_sensor(self, user_input=None):
        sensors = list(self.options[CONF_SENSORS])
        current = next((item for item in sensors if item["id"] == self._selected_sensor), None)
        if current is None:
            return self.async_abort(reason="sensor_not_found")
        if user_input is not None:
            if user_input.pop("delete_sensor", False):
                sensors = [item for item in sensors if item["id"] != self._selected_sensor]
            else:
                current.update({
                    CONF_SENSOR_NAME: user_input[CONF_SENSOR_NAME].strip(),
                    CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                    CONF_MQTT_TOPIC: user_input.get(CONF_MQTT_TOPIC, "").strip(),
                    CONF_MQTT_PAYLOAD: user_input.get(CONF_MQTT_PAYLOAD, DEFAULT_MQTT_PAYLOAD).strip(),
                    CONF_ENABLED: user_input[CONF_ENABLED],
                })
            options = dict(self.options)
            options[CONF_SENSORS] = sensors
            return self.async_create_entry(title="", data=options)
        schema = vol.Schema({
            vol.Required(CONF_SENSOR_NAME, default=current[CONF_SENSOR_NAME]): selector.TextSelector(),
            vol.Required(CONF_ENTITY_ID, default=current[CONF_ENTITY_ID]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(CONF_MQTT_TOPIC, default=current.get(CONF_MQTT_TOPIC, "")): selector.TextSelector(),
            vol.Optional(CONF_MQTT_PAYLOAD, default=current.get(CONF_MQTT_PAYLOAD, DEFAULT_MQTT_PAYLOAD)): selector.TextSelector(),
            vol.Required(CONF_ENABLED, default=current.get(CONF_ENABLED, True)): selector.BooleanSelector(),
            vol.Optional("delete_sensor", default=False): selector.BooleanSelector(),
        })
        return self.async_show_form(step_id="edit_sensor", data_schema=schema)
