# Water Leak Alerts

A Home Assistant custom integration that monitors existing water-leak `binary_sensor` entities. It replaces the helper-heavy automation pattern with config-entry configuration and integration-owned persistent state.

## Current implementation (0.1.0)

- Empty initial setup; add sensors through **Settings → Devices & services → Water Leak Alerts → Configure**.
- One HA device per monitored sensor.
- Binary sensor state transitions (`off` → `on`, `on` → `off`) drive leak start and recovery.
- Optional MQTT topic per sensor refreshes the last-wet timestamp and updates an active alert without sending another initial email.
- Initial email on a new leak episode; configurable periodic email reminders while wet and unacknowledged.
- Mobile notifications use a stable tag and include an Acknowledge action.
- Acknowledgment suppresses email reminders only. It does not dismiss persistent/mobile notifications.
- Recovery clears persistent/mobile notifications and sends a recovery email.
- Active alerts are restored after restart without sending another initial email.
- Last-wet time and acknowledgment are stored by the integration; no `input_boolean` or `input_datetime` helpers are created.

## Install manually

Copy `custom_components/water_leak_alerts` into `/config/custom_components/`, then restart Home Assistant. Add **Water Leak Alerts** under **Settings → Devices & services → Add integration**.

For HACS, publish this as a public GitHub repository and add it as a custom integration repository. Before publishing, replace the `OWNER` placeholders in `manifest.json` (`documentation`, `issue_tracker`, and `codeowners`) with your actual GitHub username/repository. HACS requires those manifest fields; this ZIP is not yet tied to a GitHub repository.

## Configure

Open the integration's **Configure** button:

1. **Notification settings**: set reminder interval in minutes. Enter email targets as comma/newline-separated SMTP notify entity IDs (the same entity IDs previously passed to `smtp.send_message`). Enter mobile targets as comma/newline-separated `notify` service names, e.g. `notify.mobile_app_phone`.
2. **Add water sensor**: choose a `binary_sensor` entity, give it a display name, and optionally enter an MQTT topic and wet payload (default `1`).
3. **Edit or remove a sensor**: select an existing sensor and modify its settings or enable Delete sensor.

The MQTT integration must be configured in Home Assistant if any sensor uses an MQTT topic. Sensors without an MQTT topic still support leak start, reminder, acknowledgment, recovery, and startup restoration. Their last-wet timestamp is set when the HA binary sensor transitions to wet.

## Entities

Each configured sensor gets:

- `Leak Alert Active` binary sensor.
- `Acknowledged` diagnostic binary sensor.
- `Last Wet Event` timestamp sensor.
- `Last Alert` timestamp sensor.
- `Acknowledge Leak` button.
- `Reset Acknowledgment` button.
- `Test Notification` button.

The integration references the original water-sensor entity; it does not create a duplicate wet/dry entity.

## Notification targets

- Email targets use the Home Assistant `smtp.send_message` service and the configured target entity ID.
- Mobile targets use `notify.<service>` services. Enter the service name including the `notify.` prefix.
- Multiple targets can be separated by commas or new lines.

## Important behavior notes

- The reminder timer starts when the integration loads and repeats at the configured interval; it is not aligned to wall-clock multiples of ten minutes.
- MQTT wet events update the timestamp only while the configured HA binary sensor currently reports `on`. An MQTT message arriving before the HA entity changes to `on` is ignored.
- The first implementation assumes water sensors use `off` for dry and `on` for wet.
- Notification service failures are logged and do not stop monitoring.

## Development status

This is an initial implementation. It has been syntax-checked, but it has not yet been run against a live Home Assistant instance or validated with your exact SMTP/MQTT/mobile service setup. Test on a backup or staging instance before relying on it for leak protection.
