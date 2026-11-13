"""Constants for the Orvibo Cloud integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

from .protocol import ORVIBO_HOSTS as ORVIBO_HOSTS

DOMAIN: Final = "orvibo_cloud"
ORVIBO_LOCK_EVENT: Final = "orvibo_cloud_lock_event"

CONF_FAMILY_ID: Final = "family_id"
CONF_HOST: Final = "host"
CONF_PASSWORD_HASH: Final = "password_hash"
CONF_USER_ID: Final = "user_id"
CONF_RAW_EVENT_CAPTURE: Final = "raw_event_capture"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=1)

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.REMOTE,
    Platform.SENSOR,
)
