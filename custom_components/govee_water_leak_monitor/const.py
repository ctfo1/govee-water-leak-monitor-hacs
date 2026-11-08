"""Constants for Govee Water Leak Monitor."""
DOMAIN = "govee_water_leak_monitor"
PLATFORMS = ["binary_sensor", "sensor", "button"]

CONF_REMINDER_INTERVAL = "reminder_interval"
CONF_EMAIL_TARGETS = "email_targets"
CONF_MOBILE_TARGETS = "mobile_targets"

DEFAULT_REMINDER_INTERVAL = 10
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_state"
SIGNAL_UPDATE = f"{DOMAIN}_update"

DEFAULT_OPTIONS = {
    CONF_REMINDER_INTERVAL: DEFAULT_REMINDER_INTERVAL,
    CONF_EMAIL_TARGETS: [],
    CONF_MOBILE_TARGETS: [],
}
