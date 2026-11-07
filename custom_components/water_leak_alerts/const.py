"""Constants for Water Leak Alerts."""
from datetime import timedelta

DOMAIN = "water_leak_alerts"
PLATFORMS = ["binary_sensor", "sensor", "button"]
CONF_SENSORS = "sensors"
CONF_SENSOR_NAME = "name"
CONF_ENTITY_ID = "entity_id"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_MQTT_PAYLOAD = "mqtt_payload"
CONF_ENABLED = "enabled"
CONF_REMINDER_INTERVAL = "reminder_interval"
CONF_EMAIL_TARGETS = "email_targets"
CONF_MOBILE_TARGETS = "mobile_targets"
DEFAULT_REMINDER_INTERVAL = 10
DEFAULT_MQTT_PAYLOAD = "1"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"
SIGNAL_UPDATE = f"{DOMAIN}_update"
DEFAULT_OPTIONS = {
    CONF_SENSORS: [],
    CONF_REMINDER_INTERVAL: DEFAULT_REMINDER_INTERVAL,
    CONF_EMAIL_TARGETS: "",
    CONF_MOBILE_TARGETS: "",
}
