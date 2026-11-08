"""rtl_433 MQTT discovery, leak state, persistence, and notifications."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CONF_EMAIL_TARGETS,
    CONF_MOBILE_TARGETS,
    CONF_REMINDER_INTERVAL,
    DEFAULT_OPTIONS,
    DOMAIN,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)
_RTL433_TOPIC_RE = re.compile(
    r"^rtl_433/([^/]+)/devices/Govee-Water/([^/]+)/([^/]+)$"
)
_STATE_TOPIC_RE = re.compile(
    r"^rtl_433/([^/]+)/devices/Govee-Water/([^/]+)/detect_wet$"
)


class WaterLeakCoordinator:
    """Coordinate automatically discovered Govee Water sensors."""

    def __init__(self, hass: HomeAssistant, entry, options: dict[str, Any]) -> None:
        self.hass = hass
        self.entry = entry
        self.options = {**DEFAULT_OPTIONS, **options}
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self.state: dict[str, dict[str, Any]] = {}
        self.discovered: dict[str, dict[str, Any]] = {}
        self._by_source: dict[tuple[str, str], str] = {}
        self._entity_adders: dict[str, tuple[Callable, Callable]] = {}
        self._mqtt_unsubs: list[Callable] = []
        self._discovery_prefixes: set[str] = {"homeassistant"}
        self._unsub_timer = None
        self._unsub_ack = None
        self._unsub_device_registry = None

    @property
    def sensors(self) -> list[dict[str, Any]]:
        """All currently discovered rtl_433 sensors."""
        return list(self.discovered.values())

    def sensor_config(self, sensor_id: str) -> dict[str, Any] | None:
        return self.discovered.get(sensor_id)

    def sensor_state(self, sensor_id: str) -> dict[str, Any]:
        """Return persisted state, creating its default record if needed."""
        return self.state.setdefault(sensor_id, {
            "active": False,
            "acknowledged": False,
            "last_wet": None,
            "last_alert": None,
            "battery_mv": None,
            "battery_ok": None,
            "last_battery_report": None,
            "last_event": None,
            "last_event_time": None,
        })

    def register_entity_adder(self, platform: str, add_entities: Callable, factory: Callable) -> None:
        """Register a platform callback and add sensors already discovered."""
        self._entity_adders[platform] = (add_entities, factory)
        if self.discovered:
            add_entities(factory(self.sensors))

    async def async_setup(self) -> None:
        """Load persistent state and start reminder/mobile-action listeners."""
        stored = await self.store.async_load() or {}
        self.state = stored.get("sensors", {})
        interval = max(1, int(self.options.get(CONF_REMINDER_INTERVAL, DEFAULT_OPTIONS[CONF_REMINDER_INTERVAL])))
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_reminder_tick, timedelta(minutes=interval)
        )
        self._unsub_ack = self.hass.bus.async_listen(
            "mobile_app_notification_action", self._async_mobile_action
        )
        self._unsub_device_registry = self.hass.bus.async_listen(
            "device_registry_updated", self._async_device_registry_updated
        )

    async def async_start_discovery(self) -> None:
        """Subscribe to HA MQTT discovery and rtl_433 Govee telemetry."""
        if "mqtt" not in self.hass.config.components:
            raise HomeAssistantError("The MQTT integration must be configured and loaded")

        from homeassistant.components import mqtt

        mqtt_entries = self.hass.config_entries.async_entries("mqtt")
        prefixes = {
            config_entry.options.get("discovery_prefix")
            or config_entry.data.get("discovery_prefix")
            or "homeassistant"
            for config_entry in mqtt_entries
        } or {"homeassistant"}
        self._discovery_prefixes = prefixes
        for prefix in prefixes:
            for topic in (f"{prefix}/+/+/config", f"{prefix}/+/+/+/config"):
                unsub = await mqtt.async_subscribe(
                    self.hass, topic, self._async_discovery_message, qos=0
                )
                self._mqtt_unsubs.append(unsub)

        unsub = await mqtt.async_subscribe(
            self.hass,
            "rtl_433/+/devices/Govee-Water/+/+",
            self._async_rtl433_message,
            qos=0,
        )
        self._mqtt_unsubs.append(unsub)
        _LOGGER.info("Listening for rtl_433 Govee Water MQTT sensors")

    async def async_shutdown(self) -> None:
        """Remove timers and MQTT subscriptions."""
        if self._unsub_timer:
            self._unsub_timer()
        if self._unsub_ack:
            self._unsub_ack()
        if self._unsub_device_registry:
            self._unsub_device_registry()
        for unsubscribe in self._mqtt_unsubs:
            unsubscribe()
        self._mqtt_unsubs.clear()

    @callback
    def _async_discovery_message(self, message) -> None:
        """Queue processing of an MQTT discovery config message."""
        self.hass.async_create_task(self._async_process_discovery(message.topic, message.payload))

    async def _async_process_discovery(self, topic: str, payload: str) -> None:
        """Match rtl_433 discovery metadata to its existing MQTT device."""
        try:
            config = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return

        parts = topic.split("/")
        if len(parts) < 4 or parts[0] not in self._discovery_prefixes or parts[1] != "binary_sensor":
            return
        device_data = config.get("device") or {}
        if device_data.get("model") != "Govee-Water":
            return
        if device_data.get("manufacturer") != "rtl_433":
            return

        state_topic = config.get("state_topic", "")
        match = _STATE_TOPIC_RE.match(state_topic)
        if not match:
            return
        instance_id, sensor_number = match.groups()
        identifiers = device_data.get("identifiers", [])
        if isinstance(identifiers, str):
            identifiers = [identifiers]
        if not identifiers:
            _LOGGER.debug("Ignoring Govee discovery without device identifiers: %s", topic)
            return

        device_registry = dr.async_get(self.hass)
        mqtt_device = None
        device_identifier = None
        mqtt_entries = self.hass.config_entries.async_entries("mqtt")
        # MQTT's own discovery handler and our subscriber receive the retained
        # config around the same time. Allow its device registration task to
        # finish before deciding that the device is missing.
        for attempt in range(5):
            for identifier in identifiers:
                for mqtt_entry in mqtt_entries:
                    mqtt_device = device_registry.async_get_device_by_identifier(
                        ("mqtt", str(identifier)), mqtt_entry.entry_id
                    )
                    if mqtt_device:
                        device_identifier = str(identifier)
                        break
                if mqtt_device:
                    break
            if mqtt_device:
                break
            if attempt < 4:
                await asyncio.sleep(0.25)
        if mqtt_device is None:
            # The MQTT integration normally registers the device before our
            # discovery subscriber receives the retained config. Never create
            # a substitute device: wait for a subsequent config publication.
            _LOGGER.debug(
                "rtl_433 device not present in HA device registry yet: %s", identifiers
            )
            return

        unique_id = config.get("unique_id")
        source_entity_id = None
        if unique_id:
            entity_registry = er.async_get(self.hass)
            for entity in er.async_entries_for_device(entity_registry, mqtt_device.id):
                if (
                    entity.platform == "mqtt"
                    and entity.entity_id.startswith("binary_sensor.")
                    and entity.unique_id == unique_id
                ):
                    source_entity_id = entity.entity_id
                    break

        key = slugify(f"{instance_id}_{sensor_number}")
        name = (
            mqtt_device.name_by_user
            or mqtt_device.name
            or device_data.get("name")
            or f"Govee Water {sensor_number}"
        )
        sensor = {
            "key": key,
            "instance_id": instance_id,
            "sensor_number": sensor_number,
            "device_identifier": device_identifier,
            "device_identifiers": list(mqtt_device.identifiers),
            "device_id": mqtt_device.id,
            "device_name": name,
            "source_entity_id": source_entity_id,
            "state_topic": state_topic,
            "base_topic": state_topic.rsplit("/", 1)[0],
            "discovery_unique_id": unique_id,
        }
        previous = self.discovered.get(key)
        # Re-link existing monitor entities if the MQTT device was deleted
        # and later rediscovered (Home Assistant assigns a new registry ID).
        needs_entities = previous is None or previous.get("device_id") != mqtt_device.id
        if previous is not None:
            previous.update(sensor)
            sensor = previous
        self.discovered[key] = sensor
        linked_entities = 0
        if previous is not None and needs_entities:
            linked_entities = self._link_registered_entities(key, mqtt_device.id)
        self._by_source[(instance_id, sensor_number)] = key
        self.sensor_state(key)

        if needs_entities:
            _LOGGER.info(
                "Discovered rtl_433 Govee Water sensor %s on existing HA device %s",
                sensor_number,
                mqtt_device.name_by_user or mqtt_device.name or mqtt_device.id,
            )
            for add_entities, factory in self._entity_adders.values():
                add_entities(factory([sensor]))

        # Restore a wet state already held by the MQTT moisture entity. This
        # is a startup reconciliation only; no new email is sent for it.
        if source_entity_id:
            source_state = self.hass.states.get(source_entity_id)
            if source_state is not None and source_state.state == "on":
                await self._async_restore_wet(sensor)
            elif source_state is not None and source_state.state == "off":
                data = self.sensor_state(key)
                if data.get("active"):
                    data.update({"active": False, "acknowledged": False})
                    self._signal_update(key)
                    await self._async_clear_notifications(sensor)
                    await self._async_save()

    @callback
    def _async_rtl433_message(self, message) -> None:
        """Handle a single field published by rtl_433."""
        match = _RTL433_TOPIC_RE.match(message.topic)
        if not match:
            return
        instance_id, sensor_number, field = match.groups()
        key = self._by_source.get((instance_id, sensor_number))
        if key is None:
            return
        self.hass.async_create_task(self._async_process_sensor_field(key, field, message.payload))

    async def _async_process_sensor_field(self, sensor_id: str, field: str, payload: str) -> None:
        """Process detect_wet, battery, and event fields independently."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        value = str(payload).strip()

        if field == "detect_wet":
            if value in {"1", "true", "True"}:
                await self._async_leak_started(item)
            elif value in {"0", "false", "False"}:
                await self._async_leak_cleared(item)
            return

        changed = False
        if field == "battery_mV":
            try:
                number = float(value)
                data["battery_mv"] = int(number) if number.is_integer() else number
                data["last_battery_report"] = dt_util.utcnow().isoformat()
                changed = True
            except ValueError:
                _LOGGER.debug("Invalid battery_mV value from %s: %s", item["base_topic"], value)
        elif field == "battery_ok":
            try:
                number = float(value)
                data["battery_ok"] = int(number) if number.is_integer() else number
                data["last_battery_report"] = dt_util.utcnow().isoformat()
                changed = True
            except ValueError:
                _LOGGER.debug("Invalid battery_ok value from %s: %s", item["base_topic"], value)
        elif field == "event":
            data["last_event"] = value
            data["last_event_time"] = dt_util.utcnow().isoformat()
            changed = True

        if changed:
            self._signal_update(sensor_id)
            await self._async_save()

    async def async_acknowledge(self, sensor_id: str) -> None:
        """Acknowledge the current leak episode and stop reminders."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        if data.get("active") and not data.get("acknowledged"):
            data["acknowledged"] = True
            self._signal_update(sensor_id)
            await self._async_save()

    async def async_reset_acknowledgment(self, sensor_id: str) -> None:
        """Re-enable reminders for an active episode."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        if data.get("active") and data.get("acknowledged"):
            data["acknowledged"] = False
            self._signal_update(sensor_id)
            await self._async_save()

    async def async_reset_to_dry(self, sensor_id: str) -> None:
        """Publish dry to the actual MQTT state topic; state follows MQTT echo."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        from homeassistant.components import mqtt

        await mqtt.async_publish(
            self.hass,
            item["state_topic"],
            "0",
            qos=0,
            retain=False,
        )
        _LOGGER.info("Published detect_wet=0 for Govee Water sensor %s", item["sensor_number"])

    async def async_test_notifications(self, sensor_id: str) -> None:
        """Send a test notification without changing leak state."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        _, friendly, _ = self._sensor_context(item)
        title = f"Govee Water Leak Monitor: Test – {friendly}"
        message = f"This is a test notification for {friendly}. No leak state was changed."
        await self._async_send_email(item, title=title, message=message)
        await self._async_send_mobile(item, title, message)

    async def _async_restore_wet(self, item: dict[str, Any]) -> None:
        """Restore a sensor that is already wet when discovered or restarted."""
        data = self.sensor_state(item["key"])
        if data.get("active"):
            return
        now = dt_util.utcnow().isoformat()
        data.update({
            "active": True,
            "acknowledged": False,
            "last_wet": data.get("last_wet") or now,
            "last_alert": data.get("last_alert") or now,
        })
        self._signal_update(item["key"])
        await self._async_show_alert(item)
        await self._async_save()

    async def _async_leak_started(self, item: dict[str, Any]) -> None:
        """Start one leak episode; repeated wet packets do not duplicate alerts."""
        data = self.sensor_state(item["key"])
        if data.get("active"):
            return
        now = dt_util.utcnow().isoformat()
        data.update({
            "active": True,
            "acknowledged": False,
            "last_wet": now,
            "last_alert": now,
        })
        self._signal_update(item["key"])
        await self._async_send_email(item, recovery=False)
        await self._async_show_alert(item)
        await self._async_save()

    async def _async_leak_cleared(self, item: dict[str, Any]) -> None:
        """End the current leak episode only after detect_wet reports dry."""
        data = self.sensor_state(item["key"])
        if not data.get("active"):
            return
        data["active"] = False
        data["acknowledged"] = False
        self._signal_update(item["key"])
        await self._async_clear_notifications(item)
        await self._async_send_email(item, recovery=True)
        await self._async_save()

    async def _async_reminder_tick(self, now: datetime) -> None:
        """Send reminders only while an unacknowledged leak episode is active."""
        for item in self.sensors:
            data = self.sensor_state(item["key"])
            if data.get("active") and not data.get("acknowledged"):
                await self._async_send_email(item, recovery=False)

    @callback
    def _async_mobile_action(self, event) -> None:
        """Handle acknowledge actions from mobile notifications."""
        action = event.data.get("action", "")
        if not action.startswith("ACK_govee_water_leak_"):
            return
        notification_id = action.removeprefix("ACK_")
        item = next((cfg for cfg in self.sensors if self._notification_id(cfg) == notification_id), None)
        if item:
            self.hass.async_create_task(self.async_acknowledge(item["key"]))

    @callback
    def _async_device_registry_updated(self, event) -> None:
        """Refresh availability when a source MQTT device is removed or added."""
        for sensor_id in self.discovered:
            self._signal_update(sensor_id)

    def device_exists(self, device_id: str) -> bool:
        """Check whether the original MQTT device is still in the registry."""
        return dr.async_get(self.hass).async_get(device_id) is not None

    @callback
    def _link_registered_entities(self, sensor_id: str, device_id: str) -> int:
        """Move existing monitor entity-registry rows to a rediscovered device."""
        entity_registry = er.async_get(self.hass)
        prefix = f"{sensor_id}_"
        linked = 0
        for entity in list(entity_registry.entities.values()):
            if (
                entity.platform == DOMAIN
                and entity.unique_id.startswith(prefix)
            ):
                linked += 1
                if entity.device_id == device_id:
                    continue
                old_device_id = entity.device_id
                entity_registry.async_update_entity(
                    entity.entity_id, device_id=device_id
                )
                if old_device_id:
                    device_registry = dr.async_get(self.hass)
                    old_device = device_registry.async_get(old_device_id)
                    remaining = er.async_entries_for_device(
                        entity_registry, old_device_id, include_disabled_entities=True
                    )
                    if (
                        old_device
                        and not remaining
                        and old_device.config_entries == {self.entry.entry_id}
                    ):
                        device_registry.async_remove_device(old_device_id)
        return linked

    def _sensor_context(self, item: dict[str, Any]) -> tuple[str | None, str, str]:
        """Resolve the existing MQTT device's current name and optional area."""
        device = dr.async_get(self.hass).async_get(item["device_id"])
        source_state = (
            self.hass.states.get(item["source_entity_id"])
            if item.get("source_entity_id") else None
        )
        friendly = (
            (device.name_by_user if device else None)
            or (source_state.attributes.get("friendly_name") if source_state else None)
            or (device.name if device else None)
            or item["device_name"]
        )
        area_name = None
        area_id = device.area_id if device else None
        if not area_id and item.get("source_entity_id"):
            source_entry = er.async_get(self.hass).async_get(item["source_entity_id"])
            area_id = source_entry.area_id if source_entry else None
        if area_id:
            area = ar.async_get(self.hass).async_get_area(area_id)
            area_name = area.name if area else None
        home = self.hass.states.get("zone.home")
        home_name = home.attributes.get("friendly_name", "Home") if home else "Home"
        return (str(area_name) if area_name else None), str(friendly), str(home_name)

    def _notification_text(self, item: dict[str, Any]) -> tuple[str, str, str]:
        area, friendly, home = self._sensor_context(item)
        last_wet = self.sensor_state(item["key"]).get("last_wet")
        if last_wet:
            parsed = dt_util.parse_datetime(last_wet)
            stamp = dt_util.as_local(parsed).strftime("%Y-%m-%d %H:%M:%S") if parsed else "Unknown"
        else:
            stamp = "Unknown"
        title = f"Water Leak: {home}: {area}" if area else f"Water Leak: {home}"
        message = (
            f"Water detected in {area} by {friendly} @ {stamp}"
            if area else f"Water detected by {friendly} @ {stamp}"
        )
        return title, message, area

    async def _async_show_alert(self, item: dict[str, Any]) -> None:
        title, message, _ = self._notification_text(item)
        await self.hass.services.async_call("persistent_notification", "create", {
            "notification_id": self._notification_id(item),
            "title": title,
            "message": message,
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
                    "message": "clear_notification",
                    "data": {"tag": self._notification_id(item)},
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
        self,
        item: dict[str, Any],
        recovery: bool = False,
        title: str | None = None,
        message: str | None = None,
    ) -> None:
        if title is None or message is None:
            alert_title, alert_message, area = self._notification_text(item)
            if recovery:
                last_wet = self.sensor_state(item["key"]).get("last_wet")
                parsed = dt_util.parse_datetime(last_wet) if last_wet else None
                stamp = dt_util.as_local(parsed).strftime("%Y-%m-%d %H:%M:%S") if parsed else "Unknown"
                home = self._sensor_context(item)[2]
                title = (
                    f"Water Leak Alert Cleared: {home}: {area}"
                    if area else f"Water Leak Alert Cleared: {home}"
                )
                _, friendly, _ = self._sensor_context(item)
                message = (
                    f"Water leak alert cleared for {friendly} in {area}. Water last detected @ {stamp}"
                    if area else f"Water leak alert cleared for {friendly}. Water last detected @ {stamp}"
                )
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

    async def _async_save(self) -> None:
        await self.store.async_save({"sensors": self.state})

    def _targets(self, option: str) -> list[str]:
        raw = self.options.get(option, []) or []
        if isinstance(raw, str):
            return [value.strip() for value in raw.replace("\n", ",").split(",") if value.strip()]
        return [str(value).strip() for value in raw if str(value).strip()]

    @staticmethod
    def _notification_id(item: dict[str, Any]) -> str:
        return f"govee_water_leak_{item['key']}"

    @callback
    def _signal_update(self, sensor_id: str) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_send

        async_dispatcher_send(
            self.hass,
            f"{SIGNAL_UPDATE}_{self.entry.entry_id}_{sensor_id}",
        )
