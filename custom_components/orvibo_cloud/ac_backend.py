"""Route AC infrared commands through the existing ORVIBO TLS client."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.exceptions import HomeAssistantError

from .ac_profiles import ACProfile
from .binary import OrviboBinaryError, control_device
from .const import CONF_FAMILY_ID, CONF_HOST
from .control import OrviboControlCommand
from .coordinator import OrviboCloudCoordinator
from .protocol import OrviboDevice


def has_available_route(
    device: OrviboDevice, devices: Iterable[OrviboDevice], hub_type: str
) -> bool:
    """Check the hub association without routing a command to a hub row."""
    if not device.uid or not device.cloud_uid or not device.model:
        return False
    matches = [
        hub for hub in devices
        if hub.device_type == hub_type and hub.cloud_uid == device.cloud_uid
        and hub.model == device.model
    ]
    if hub_type == "30":
        # The Magic Cube can appear as multiple rows sharing the same route.
        return device.online is True and any(hub.online is True for hub in matches)
    return len(matches) == 1 and matches[0].online is not False


class OrviboACBackend:
    """Resolve current routing and send one validated IR signal."""

    def __init__(self, coordinator: OrviboCloudCoordinator, profile: ACProfile) -> None:
        self.coordinator = coordinator
        self.profile = profile

    def available(self, device: OrviboDevice) -> bool:
        account = self.coordinator.data
        return (
            self.coordinator.last_update_success
            and device.online is not False
            and has_available_route(device, account.devices, self.profile.hub_type)
            and bool(account.binary_user_name and account.binary_password)
        )

    async def async_send(
        self, device: OrviboDevice, command: OrviboControlCommand
    ) -> None:
        """Send under the caller's control lock without retrying on failure."""
        if not self.available(device):
            raise HomeAssistantError("The ORVIBO AC remote is unavailable")
        account = self.coordinator.data
        entry_data = self.coordinator.entry.data
        try:
            await self.coordinator.hass.async_add_executor_job(
                control_device,
                entry_data[CONF_HOST],
                account.binary_user_name,
                account.binary_password,
                entry_data[CONF_FAMILY_ID],
                device.uid,
                device.cloud_uid,
                command.order, command.value1, command.value2, command.value3,
                command.value4, command.properties, command.infrared,
            )
        except (OrviboBinaryError, OSError):
            raise HomeAssistantError("ORVIBO did not acknowledge the AC command") from None
