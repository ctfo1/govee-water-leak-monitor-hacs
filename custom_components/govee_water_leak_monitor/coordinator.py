"""Runtime monitoring and notification coordinator."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EMAIL_TARGETS,
    CONF_ENABLED,
    CONF_ENTITY_ID,
    CONF_MOBILE_TARGETS,
    CONF_MQTT_PAYLOAD,
    CONF_MQTT_TOPIC,
    CONF_REMINDER_INTERVAL,
    CONF_SENSORS,
    DEFAULT_MQTT_PAYLOAD,
    DOMAIN,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class WaterLeakCoordinator:
    """Coordinate sensor state, persistent episode state and notifications."""

    def __init__(self, hass: HomeAssistant, entry, options: dict[str, Any]) -> None:
        self.hass = hass
        self.entry = entry
        self.options = options
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self.state: dict[str, dict[str, Any]] = {}
        self._unsub_state = None
        self._unsub_timer = None
        self._unsub_ack = None
        self._mqtt_unsubs: list[Any] = []

    @property
    def sensors(self) -> list[dict[str, Any]]:
        return [item for item in self.options.get(CONF_SENSORS, []) if item.get(CONF_ENABLED, True)]

    def sensor_config(self, sensor_id: str) -> dict[str, Any] | None:
        return next((item for item in self.sensors if item["id"] == sensor_id), None)

    def sensor_state(self, sensor_id: str) -> dict[str, Any]:
        return self.state.setdefault(sensor_id, {
            "active": False,
            "acknowledged": False,
            "last_wet": None,
            "last_alert": None,
        })

    async def async_setup(self) -> None:
        """Load state, reconcile active sensors and start listeners."""
        stored = await self.store.async_load() or {}
        self.state = stored.get("sensors", {})
        entity_ids = [item[CONF_ENTITY_ID] for item in self.sensors]
        for item in self.sensors:
            sensor_state = self.sensor_state(item["id"])
            if sensor_state.get("entity_id") not in (None, item[CONF_ENTITY_ID]):
                sensor_state.update({
                    "active": False, "acknowledged": False,
                    "last_wet": None, "last_alert": None,
                })
            sensor_state["entity_id"] = item[CONF_ENTITY_ID]
            current = self.hass.states.get(item[CONF_ENTITY_ID])
            is_wet = current is not None and current.state == "on"
            was_active = sensor_state.get("active", False)
            sensor_state["active"] = is_wet
            if is_wet:
                await self._async_show_alert(item, startup=True)
            elif was_active:
                sensor_state["acknowledged"] = False
                await self._async_clear_notifications(item)
        if entity_ids:
            self._unsub_state = async_track_state_change_event(
                self.hass, entity_ids, self._async_state_changed
            )
        interval = max(1, int(self.options.get(CONF_REMINDER_INTERVAL, 10)))
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_reminder_tick, timedelta(minutes=interval)
        )
        await self._async_subscribe_mqtt()
        self._unsub_ack = self.hass.bus.async_listen(
            "mobile_app_notification_action", self._async_mobile_action
        )
        await self._async_save()

    async def async_shutdown(self) -> None:
        """Remove listeners and subscriptions."""
        if self._unsub_state:
            self._unsub_state()
        if self._unsub_timer:
            self._unsub_timer()
        if self._unsub_ack:
            self._unsub_ack()
        for unsubscribe in self._mqtt_unsubs:
            unsubscribe()
        self._mqtt_unsubs.clear()

    async def _async_subscribe_mqtt(self) -> None:
        """Subscribe to configured optional MQTT wet-event topics."""
        if not any(item.get(CONF_MQTT_TOPIC) for item in self.sensors):
            return
        if "mqtt" not in self.hass.config.components:
            _LOGGER.warning("MQTT topics are configured, but the MQTT integration is not loaded")
            return
        from homeassistant.components import mqtt

        for item in self.sensors:
            topic = item.get(CONF_MQTT_TOPIC)
            if not topic:
                continue
            sensor_id = item["id"]
            expected = item.get(CONF_MQTT_PAYLOAD, DEFAULT_MQTT_PAYLOAD)

            @callback
            def message_received(message, _sensor_id=sensor_id, _expected=expected):
                if message.payload == _expected:
                    self.hass.async_create_task(self._async_mqtt_wet(_sensor_id))

            unsub = await mqtt.async_subscribe(self.hass, topic, message_received, qos=0)
            self._mqtt_unsubs.append(unsub)

    @callback
    def _async_mobile_action(self, event) -> None:
        """Handle acknowledge actions from mobile notifications."""
        action = event.data.get("action", "")
        if not action.startswith("ACK_govee_water_leak_"):
            return
        notification_id = action.removeprefix("ACK_")
        item = next((cfg for cfg in self.sensors if self._notification_id(cfg) == notification_id), None)
        if item:
            self.hass.async_create_task(self.async_acknowledge(item["id"]))

    async def _async_mqtt_wet(self, sensor_id: str) -> None:
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        current = self.hass.states.get(item[CONF_ENTITY_ID])
        data = self.sensor_state(sensor_id)
        # MQTT is supplementary: it refreshes an already-active leak even if
        # the source entity temporarily becomes unavailable. It never creates
        # a new leak episode on its own.
        if not data.get("active") and (current is None or current.state != "on"):
            return
        data["last_wet"] = dt_util.utcnow().isoformat()
        data["entity_id"] = item[CONF_ENTITY_ID]
        await self._async_show_alert(item)
        await self._async_save()
        self._signal_update(sensor_id)

    @callback
    def _async_state_changed(self, event) -> None:
        entity_id = event.data["entity_id"]
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        item = next((cfg for cfg in self.sensors if cfg[CONF_ENTITY_ID] == entity_id), None)
        if item is None:
            return
        if new_state.state == "on" and (old_state is None or old_state.state != "on"):
            if old_state is None or old_state.state in ("unknown", "unavailable"):
                self.hass.async_create_task(self._async_restore_wet(item))
            else:
                self.hass.async_create_task(self._async_leak_started(item))
        elif new_state.state == "off" and old_state is not None and old_state.state == "on":
            self.hass.async_create_task(self._async_leak_cleared(item))

    async def _async_restore_wet(self, item: dict[str, Any]) -> None:
        """Restore a sensor that first becomes available already wet."""
        data = self.sensor_state(item["id"])
        data["active"] = True
        await self._async_show_alert(item, startup=True)
        await self._async_save()
        self._signal_update(item["id"])

    async def _async_leak_started(self, item: dict[str, Any]) -> None:
        data = self.sensor_state(item["id"])
        if data.get("active"):
            return
        data.update({
            "active": True,
            "acknowledged": False,
            "entity_id": item[CONF_ENTITY_ID],
            "last_wet": dt_util.utcnow().isoformat(),
            "last_alert": dt_util.utcnow().isoformat(),
        })
        await self._async_send_email(item, recovery=False)
        await self._async_show_alert(item)
        await self._async_save()
        self._signal_update(item["id"])

    async def _async_leak_cleared(self, item: dict[str, Any]) -> None:
        data = self.sensor_state(item["id"])
        if not data.get("active"):
            return
        data["active"] = False
        data["acknowledged"] = False
        await self._async_clear_notifications(item)
        await self._async_send_email(item, recovery=True)
        await self._async_save()
        self._signal_update(item["id"])

    async def async_acknowledge(self, sensor_id: str) -> None:
        """Acknowledge the current episode and stop email reminders."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        if data.get("active"):
            data["acknowledged"] = True
            await self._async_save()
            self._signal_update(sensor_id)

    async def async_reset_acknowledgment(self, sensor_id: str) -> None:
        """Re-enable reminders for an active episode."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        if data.get("active"):
            data["acknowledged"] = False
            await self._async_save()
            self._signal_update(sensor_id)

    async def async_test_notifications(self, sensor_id: str) -> None:
        """Send a test notification without changing leak state."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        title = f"Govee Water Leak Monitor: Test – {item['name']}"
        message = f"This is a test notification for {item['name']}. No leak state was changed."
        await self._async_send_email(item, title=title, message=message)
        await self._async_send_mobile(item, title, message)

    async def _async_reminder_tick(self, now: datetime) -> None:
        for item in self.sensors:
            data = self.sensor_state(item["id"])
            current = self.hass.states.get(item[CONF_ENTITY_ID])
            if data.get("active") and not data.get("acknowledged") and current and current.state == "on":
                await self._async_send_email(item, recovery=False)

    def _sensor_context(self, item: dict[str, Any]) -> tuple[str, str, str]:
        entity_id = item[CONF_ENTITY_ID]
        state = self.hass.states.get(entity_id)
        friendly = state.attributes.get("friendly_name", item["name"]) if state else item["name"]
        area = self._area_for_entity(entity_id) or friendly
        home = self.hass.states.get("zone.home")
        home_name = home.attributes.get("friendly_name", "Home") if home else "Home"
        return str(area), str(friendly), str(home_name)

    def _area_for_entity(self, entity_id: str) -> str | None:
        entity_reg = er.async_get(self.hass)
        entity = entity_reg.async_get(entity_id)
        area_id = entity.area_id if entity else None
        if not area_id and entity and entity.device_id:
            device = dr.async_get(self.hass).async_get(entity.device_id)
            area_id = device.area_id if device else None
        if area_id:
            area = ar.async_get(self.hass).async_get_area(area_id)
            return area.name if area else None
        return None

    def _notification_text(self, item: dict[str, Any]) -> tuple[str, str, str]:
        area, friendly, home = self._sensor_context(item)
        data = self.sensor_state(item["id"])
        last_wet = data.get("last_wet")
        if last_wet:
            try:
                parsed = dt_util.parse_datetime(last_wet)
                stamp = dt_util.as_local(parsed).strftime("%Y-%m-%d %H:%M:%S") if parsed else "Unknown"
            except (TypeError, ValueError):
                stamp = "Unknown"
        else:
            stamp = "Unknown"
        title = f"Water Leak: {home}: {area}"
        message = f"Water detected in {area} by {friendly} @ {stamp}"
        return title, message, area

    async def _async_show_alert(self, item: dict[str, Any], startup: bool = False) -> None:
        title, message, _ = self._notification_text(item)
        notification_id = self._notification_id(item)
        await self.hass.services.async_call("persistent_notification", "create", {
            "notification_id": notification_id, "title": title, "message": message,
        }, blocking=True)
        await self._async_send_mobile(item, title, message)

    async def _async_clear_notifications(self, item: dict[str, Any]) -> None:
        await self.hass.services.async_call("persistent_notification", "dismiss", {
            "notification_id": self._notification_id(item),
        }, blocking=True)
        for target in self._targets(CONF_MOBILE_TARGETS):
            service = target.removeprefix("notify.")
            try:
                await self.hass.services.async_call("notify", service, {
                    "message": "clear_notification", "data": {"tag": self._notification_id(item)},
                }, blocking=True)
            except HomeAssistantError:
                _LOGGER.exception("Unable to clear mobile notification using %s", target)

    async def _async_send_mobile(self, item: dict[str, Any], title: str, message: str) -> None:
        notification_id = self._notification_id(item)
        for target in self._targets(CONF_MOBILE_TARGETS):
            service = target.removeprefix("notify.")
            try:
                await self.hass.services.async_call("notify", service, {
                    "title": title,
                    "message": message,
                    "data": {
                        "tag": notification_id,
                        "alert_once": True,
                        "actions": [{
                            "action": f"ACK_{notification_id}",
                            "title": "Acknowledge",
                        }],
                    },
                }, blocking=True)
            except HomeAssistantError:
                _LOGGER.exception("Unable to send mobile notification using %s", target)

    async def _async_send_email(
        self, item: dict[str, Any], recovery: bool = False, title: str | None = None, message: str | None = None
    ) -> None:
        if title is None or message is None:
            alert_title, alert_message, area = self._notification_text(item)
            if recovery:
                data = self.sensor_state(item["id"])
                last_wet = data.get("last_wet")
                if last_wet:
                    try:
                        parsed = dt_util.parse_datetime(last_wet)
                        last_wet = dt_util.as_local(parsed).strftime("%Y-%m-%d %H:%M:%S") if parsed else "Unknown"
                    except (TypeError, ValueError):
                        last_wet = "Unknown"
                else:
                    last_wet = "Unknown"
                title = f"Water Leak Alert Cleared: {self._sensor_context(item)[2]}: {area}"
                message = f"Water leak alert cleared for {item['name']} in {area}. Water last detected @ {last_wet}"
            else:
                title, message = alert_title, alert_message
        for target in self._targets(CONF_EMAIL_TARGETS):
            try:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"title": title, "message": message},
                    target={"entity_id": target},
                    blocking=True,
                )
            except HomeAssistantError:
                _LOGGER.exception("Unable to send email using notify entity %s", target)

    def _targets(self, option: str) -> list[str]:
        raw = self.options.get(option, []) or []
        if isinstance(raw, str):
            return [value.strip() for value in raw.replace("\n", ",").split(",") if value.strip()]
        return [str(value).strip() for value in raw if str(value).strip()]

    @staticmethod
    def _notification_id(item: dict[str, Any]) -> str:
        return f"govee_water_leak_{item[CONF_ENTITY_ID].replace('.', '_')}"

    async def _async_save(self) -> None:
        await self.store.async_save({"sensors": self.state})

    @callback
    def _signal_update(self, sensor_id: str) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_send
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}_{sensor_id}")
