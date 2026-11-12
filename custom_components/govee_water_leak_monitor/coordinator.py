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
        # MQTT callbacks enqueue fields synchronously; one worker per sensor
        # applies them in arrival order so slow side effects cannot reorder state.
        self._message_queues: dict[str, asyncio.Queue] = {}
        self._message_workers: dict[str, asyncio.Task] = {}
        # Notification work is serialized separately from state processing.
        self._notification_queues: dict[str, asyncio.Queue] = {}
        self._notification_workers: dict[str, asyncio.Task] = {}
        self._episode_generation: dict[str, int] = {}
        self._shutting_down = False
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
        defaults = {
            "active": False,
            "acknowledged": False,
            "last_wet": None,
            "leak_started": None,
            "last_notification": None,
            "last_battery_report": None,
            "last_event": None,
            "last_event_time": None,
        }
        data = self.state.setdefault(sensor_id, {})
        for key, value in defaults.items():
            data.setdefault(key, value)
        # Migrate the prior timestamp key without losing existing history.
        if data.get("last_notification") is None and data.get("last_alert"):
            data["last_notification"] = data["last_alert"]
        # Before v0.3.2, last_wet held the start of the episode. Preserve it
        # as the best available start time when upgrading an active leak.
        if data.get("active") and not data.get("leak_started"):
            data["leak_started"] = data.get("last_wet")
        return data

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
        self._shutting_down = True
        workers = list(self._message_workers.values()) + list(self._notification_workers.values())
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._message_workers.clear()
        self._notification_workers.clear()

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
                await self._async_restore_dry(sensor)

    @callback
    def _async_rtl433_message(self, message) -> None:
        """Queue MQTT fields in callback-arrival order for their sensor."""
        match = _RTL433_TOPIC_RE.match(message.topic)
        if not match:
            return
        instance_id, sensor_number, field = match.groups()
        key = self._by_source.get((instance_id, sensor_number))
        if key is None:
            return

        queue = self._message_queues.setdefault(key, asyncio.Queue())
        queue.put_nowait((
            field,
            message.payload,
            bool(getattr(message, "retain", False)),
            dt_util.utcnow().isoformat(),
        ))
        worker = self._message_workers.get(key)
        if worker is None or worker.done():
            self._message_workers[key] = self.hass.async_create_task(
                self._async_process_sensor_queue(key)
            )

    async def _async_process_sensor_queue(self, sensor_id: str) -> None:
        """Apply a sensor's MQTT fields sequentially in arrival order."""
        queue = self._message_queues[sensor_id]
        try:
            while not queue.empty():
                field, payload, retained, received_at = queue.get_nowait()
                try:
                    await self._async_process_sensor_field(
                        sensor_id, field, payload, retained, received_at
                    )
                except Exception:
                    _LOGGER.exception(
                        "Error processing rtl_433 field %s for sensor %s", field, sensor_id
                    )
                finally:
                    queue.task_done()
        finally:
            self._message_workers.pop(sensor_id, None)
            if not self._shutting_down and not queue.empty():
                self._message_workers[sensor_id] = self.hass.async_create_task(
                    self._async_process_sensor_queue(sensor_id)
                )

    @callback
    def _next_episode_generation(self, sensor_id: str) -> int:
        generation = self._episode_generation.get(sensor_id, 0) + 1
        self._episode_generation[sensor_id] = generation
        return generation

    @callback
    def _queue_notification_operation(
        self, item: dict[str, Any], operation: str, generation: int
    ) -> None:
        """Queue notification side effects independently of MQTT state work."""
        sensor_id = item["key"]
        queue = self._notification_queues.setdefault(sensor_id, asyncio.Queue())
        queue.put_nowait((operation, generation))
        worker = self._notification_workers.get(sensor_id)
        if worker is None or worker.done():
            self._notification_workers[sensor_id] = self.hass.async_create_task(
                self._async_process_notification_queue(sensor_id)
            )

    async def _async_process_notification_queue(self, sensor_id: str) -> None:
        """Run notification operations serially and discard stale operations."""
        queue = self._notification_queues[sensor_id]
        try:
            while not queue.empty():
                operation, generation = queue.get_nowait()
                try:
                    item = self.sensor_config(sensor_id)
                    if item is None or generation != self._episode_generation.get(sensor_id, 0):
                        continue
                    data = self.sensor_state(sensor_id)

                    if operation in {"start", "restore", "reminder"}:
                        if not data.get("active") or data.get("acknowledged"):
                            continue
                        if operation == "start":
                            await self._async_send_email(item, recovery=False)
                        if (
                            generation != self._episode_generation.get(sensor_id, 0)
                            or not data.get("active") or data.get("acknowledged")
                        ):
                            continue
                        await self._async_show_alert(item, generation)
                        if operation == "reminder" and (
                            generation == self._episode_generation.get(sensor_id, 0)
                            and data.get("active") and not data.get("acknowledged")
                        ):
                            await self._async_send_email(item, recovery=False)

                    elif operation == "clear":
                        if data.get("active"):
                            continue
                        await self._async_clear_notifications(item)
                        if (
                            generation == self._episode_generation.get(sensor_id, 0)
                            and not data.get("active")
                        ):
                            await self._async_send_email(item, recovery=True)

                    elif operation == "restore_clear":
                        if not data.get("active"):
                            await self._async_clear_notifications(item)

                    elif operation == "ack_clear":
                        if data.get("acknowledged"):
                            await self._async_clear_notifications(item)

                except Exception:
                    _LOGGER.exception(
                        "Error processing %s notification operation for sensor %s",
                        operation, sensor_id,
                    )
                finally:
                    queue.task_done()
        finally:
            self._notification_workers.pop(sensor_id, None)
            if not self._shutting_down and not queue.empty():
                self._notification_workers[sensor_id] = self.hass.async_create_task(
                    self._async_process_notification_queue(sensor_id)
                )

    async def _async_process_sensor_field(
        self,
        sensor_id: str,
        field: str,
        payload: str,
        retained: bool = False,
        received_at: str | None = None,
    ) -> None:
        """Process MQTT telemetry; only detect_wet is accepted when retained.

        All timestamps use HA's receipt time. The MQTT time field is ignored.
        """
        if retained and field != "detect_wet":
            return

        item = self.sensor_config(sensor_id)
        if item is None:
            return
        data = self.sensor_state(sensor_id)
        value = str(payload).strip()
        now = received_at or dt_util.utcnow().isoformat()

        if field == "detect_wet":
            if value in {"1", "true", "True"}:
                if retained:
                    await self._async_restore_wet(item)
                else:
                    await self._async_leak_started(item, now)
            elif value in {"0", "false", "False"}:
                if retained:
                    await self._async_restore_dry(item)
                else:
                    await self._async_leak_cleared(item)
            return

        if field == "event":
            # Reset-to-Dry records its own event time before publishing.
            if (
                value.casefold() == "ha button press"
                and data.get("last_event") == value
                and data.get("last_event_time")
            ):
                return
            data["last_event"] = value
            data["last_event_time"] = now
            if value.casefold() == "battery report":
                data["last_battery_report"] = now
            self._signal_update(sensor_id)
            await self._async_save()

    async def async_set_acknowledged(self, sensor_id: str, acknowledged: bool) -> None:
        """Set acknowledgment for the current leak episode."""
        if self.sensor_config(sensor_id) is None:
            return
        data = self.sensor_state(sensor_id)
        desired = bool(acknowledged) and bool(data.get("active"))
        if data.get("acknowledged") != desired:
            data["acknowledged"] = desired
            self._signal_update(sensor_id)
            await self._async_save()
            # Keep the mobile and persistent alerts in sync with the shared
            # acknowledgment switch. Dismissing a notification without using
            # its Acknowledge action does not change this state.
            if desired:
                self._queue_notification_operation(
                    self.sensor_config(sensor_id),
                    "ack_clear",
                    self._episode_generation.get(sensor_id, 0),
                )

    async def async_acknowledge(self, sensor_id: str) -> None:
        """Acknowledge the current leak episode (mobile notification action)."""
        await self.async_set_acknowledged(sensor_id, True)

    async def async_reset_to_dry(self, sensor_id: str) -> None:
        """Publish a retained dry state and HA-originated reset event."""
        item = self.sensor_config(sensor_id)
        if item is None:
            return
        from homeassistant.components import mqtt

        # Persist the event timestamp before publishing. That preserves the
        # original HA reset time when the retained event is replayed later.
        now = dt_util.utcnow().isoformat()
        data = self.sensor_state(sensor_id)
        data["last_event"] = "HA Button Press"
        data["last_event_time"] = now
        self._signal_update(sensor_id)
        await self._async_save()

        await mqtt.async_publish(
            self.hass,
            item["state_topic"],
            "0",
            qos=0,
            # Replace any retained wet state so HA does not restore stale
            # detect_wet=1 after a restart. Real rtl_433 reports still win.
            retain=True,
        )
        await mqtt.async_publish(
            self.hass,
            f"{item['base_topic']}/event",
            "HA Button Press",
            qos=0,
            retain=True,
        )
        _LOGGER.info(
            "Published detect_wet=0 and event=HA Button Press for Govee Water sensor %s",
            item["sensor_number"],
        )

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
        """Restore retained/current wet state without treating it as a new event."""
        sensor_id = item["key"]
        data = self.sensor_state(sensor_id)
        if data.get("active"):
            return
        generation = self._next_episode_generation(sensor_id)
        data.update({
            "active": True,
            "acknowledged": False,
        })
        self._signal_update(sensor_id)
        await self._async_save()
        self._queue_notification_operation(item, "restore", generation)

    async def _async_restore_dry(self, item: dict[str, Any]) -> None:
        """Restore retained dry state without generating a recovery email."""
        sensor_id = item["key"]
        data = self.sensor_state(sensor_id)
        if not data.get("active"):
            return
        generation = self._next_episode_generation(sensor_id)
        data["active"] = False
        data["acknowledged"] = False
        self._signal_update(sensor_id)
        await self._async_save()
        self._queue_notification_operation(item, "restore_clear", generation)

    async def _async_leak_started(self, item: dict[str, Any], event_time: str | None = None) -> None:
        """Record every live wet report; alert only on a dry-to-wet transition."""
        sensor_id = item["key"]
        data = self.sensor_state(sensor_id)
        now = event_time or dt_util.utcnow().isoformat()
        data["last_wet"] = now
        if data.get("active"):
            self._signal_update(sensor_id)
            await self._async_save()
            return
        generation = self._next_episode_generation(sensor_id)
        data.update({"active": True, "acknowledged": False, "leak_started": now})
        self._signal_update(sensor_id)
        await self._async_save()
        self._queue_notification_operation(item, "start", generation)

    async def _async_leak_cleared(self, item: dict[str, Any]) -> None:
        """End the leak episode promptly and queue clear/recovery side effects."""
        sensor_id = item["key"]
        data = self.sensor_state(sensor_id)
        if not data.get("active"):
            return
        generation = self._next_episode_generation(sensor_id)
        data["active"] = False
        data["acknowledged"] = False
        self._signal_update(sensor_id)
        await self._async_save()
        self._queue_notification_operation(item, "clear", generation)

    async def _async_reminder_tick(self, now: datetime) -> None:
        """Queue reminders only for currently active, unacknowledged leaks."""
        for item in self.sensors:
            data = self.sensor_state(item["key"])
            if data.get("active") and not data.get("acknowledged"):
                self._queue_notification_operation(
                    item, "reminder", self._episode_generation.get(item["key"], 0)
                )

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

    async def _async_show_alert(
        self, item: dict[str, Any], generation: int | None = None
    ) -> None:
        """Show an alert only while its originating leak episode is current."""
        sensor_id = item["key"]
        data = self.sensor_state(sensor_id)

        def still_current() -> bool:
            return (
                generation is None
                or (
                    generation == self._episode_generation.get(sensor_id, 0)
                    and data.get("active")
                    and not data.get("acknowledged")
                )
            )

        if not still_current():
            return
        title, message, _ = self._notification_text(item)
        await self.hass.services.async_call("persistent_notification", "create", {
            "notification_id": self._notification_id(item),
            "title": title,
            "message": message,
        }, blocking=True)
        if not still_current():
            return
        await self._async_record_notification(item)
        if still_current():
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
                await self._async_record_notification(item)
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
                await self._async_record_notification(item)
            except HomeAssistantError:
                _LOGGER.exception("Unable to send email using notify entity %s", target)

    async def _async_record_notification(self, item: dict[str, Any]) -> None:
        """Persist the time of the most recent successfully sent notification."""
        data = self.sensor_state(item["key"])
        data["last_notification"] = dt_util.utcnow().isoformat()
        self._signal_update(item["key"])
        await self._async_save()

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
