"""Options and command history for RF blinds without position feedback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

CONF_RF_BLIND_OPTIONS = "rf_blind_options"
CONF_REMEMBER_STATE = "remember_assumed_state"
CONF_RESTORE_STATE = "restore_assumed_state"
CONF_STATE_EXPIRY = "assumed_state_expiry_minutes"
MAX_STATE_EXPIRY_MINUTES = 525600
STATE_SOURCE = "last_successful_command"
_ACTIONS = {"open", "close", "stop"}


@dataclass(frozen=True, slots=True)
class RFBlindOptions:
    """Independent, opt-in settings for one RF blind."""

    remember: bool = False
    restore: bool = False
    expiry_minutes: int = 0

    @classmethod
    def from_mapping(cls, value: Any) -> RFBlindOptions:
        """Read saved options defensively; malformed options stay disabled."""

        if not isinstance(value, Mapping):
            return cls()
        expiry = value.get(CONF_STATE_EXPIRY, 0)
        if type(expiry) is not int or not 0 <= expiry <= MAX_STATE_EXPIRY_MINUTES:
            expiry = 0
        remember = value.get(CONF_REMEMBER_STATE) is True
        return cls(
            remember=remember,
            restore=remember and value.get(CONF_RESTORE_STATE) is True,
            expiry_minutes=expiry,
        )

    def as_dict(self) -> dict[str, bool | int]:
        """Serialize options for a config entry."""

        return {
            CONF_REMEMBER_STATE: self.remember,
            CONF_RESTORE_STATE: self.restore,
            CONF_STATE_EXPIRY: self.expiry_minutes,
        }


def configured_rf_blind_options(
    options: Mapping[str, Any],
) -> dict[str, RFBlindOptions]:
    """Return settings by cloud device ID, without enabling legacy entries."""

    configured = options.get(CONF_RF_BLIND_OPTIONS)
    if not isinstance(configured, Mapping):
        return {}
    return {
        device_id: RFBlindOptions.from_mapping(value)
        for device_id, value in configured.items()
        if isinstance(device_id, str)
    }


@dataclass(slots=True)
class AssumedBlindState:
    """The last successful command, never a measured percentage."""

    last_action: str | None = None
    last_action_time: datetime | None = None

    @classmethod
    def from_attributes(
        cls, attributes: Mapping[str, Any], now: datetime
    ) -> AssumedBlindState:
        """Restore only our own valid history with an explicit UTC timestamp."""

        action = attributes.get("last_action")
        timestamp = attributes.get("last_action_time")
        if (
            attributes.get("state_source") != STATE_SOURCE
            or not isinstance(action, str)
            or action not in _ACTIONS
            or not isinstance(timestamp, str)
        ):
            return cls()
        try:
            when = datetime.fromisoformat(timestamp)
        except ValueError:
            return cls()
        if when.tzinfo is None or when.utcoffset() is None or when > now:
            return cls()
        return cls(action, when.astimezone(UTC))

    def record(self, action: str, now: datetime) -> None:
        """Record a command after its successful acknowledgement."""

        if action not in _ACTIONS:
            raise ValueError("Unsupported RF blind action")
        self.last_action = action
        self.last_action_time = now

    def expires_at(self, options: RFBlindOptions) -> datetime | None:
        """Return an absolute deadline so reloads do not reset the lifetime."""

        if not options.expiry_minutes or self.last_action_time is None:
            return None
        return self.last_action_time + timedelta(minutes=options.expiry_minutes)

    def expired(self, options: RFBlindOptions, now: datetime) -> bool:
        """Return whether the optional lifetime has elapsed."""

        deadline = self.expires_at(options)
        return deadline is not None and now >= deadline

    def is_closed(self, options: RFBlindOptions, now: datetime) -> bool | None:
        """Return an assumed binary state; Stop and expired history are unknown."""

        if not options.remember or self.expired(options, now):
            return None
        if self.last_action == "close":
            return True
        if self.last_action == "open":
            return False
        return None

    def attributes(self, options: RFBlindOptions, now: datetime) -> dict[str, Any]:
        """Expose the origin and age of the assumption without inventing position."""

        return {
            "last_action": self.last_action,
            "last_action_time": (
                self.last_action_time.isoformat() if self.last_action_time else None
            ),
            "state_source": STATE_SOURCE if self.last_action is not None else None,
            "assumption_expired": self.expired(options, now),
        }
