"""Shared transmission and availability for Allone Pro TV controls."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import math
from homeassistant.exceptions import HomeAssistantError

from .binary import OrviboBinaryError, control_device
from .const import CONF_FAMILY_ID, CONF_HOST
from .control import is_allone_tv, lg_tv_button_command, tv_button_command
from .entity import OrviboCloudDeviceEntity


class OrviboTVEntity(OrviboCloudDeviceEntity):
    """One command endpoint on an Allone Pro's type-6 TV remote."""

    @property
    def available(self) -> bool:
        device = self._device
        return (
            super().available
            and device is not None
            and bool(self.coordinator.data.binary_password)
            and is_allone_tv(device, self.coordinator.data.devices)
            and any(
                hub.device_type == "67"
                and hub.cloud_uid == device.cloud_uid
                and hub.online is not False
                for hub in self.coordinator.data.devices
            )
        )

    async def _async_send_tv_commands(
        self,
        commands: Iterable[str],
        *,
        num_repeats: int = 1,
        delay_secs: float = 0.4,
        hold_secs: float = 0,
    ) -> None:
        """Validate the complete sequence, then send it once per requested key."""

        try:
            names = [commands] if isinstance(commands, str) else list(commands)
            if not names:
                raise ValueError("At least one TV command is required")
            profile = self.coordinator.entry.options.get("tv_profile", "lg")
            if profile not in {"lg", "stored"}:
                raise ValueError("Select a supported TV infrared profile in Configure")
            build = lg_tv_button_command if profile == "lg" else tv_button_command
            payloads = [build(name) for name in names]
            if isinstance(num_repeats, bool) or not isinstance(num_repeats, int):
                raise ValueError("num_repeats must be an integer")
            if not 1 <= num_repeats <= 20:
                raise ValueError("num_repeats must be between 1 and 20")
            delay = float(delay_secs)
            if not math.isfinite(delay) or not 0 <= delay <= 60:
                raise ValueError("delay_secs must be between 0 and 60")
            if float(hold_secs) != 0:
                raise ValueError("Holding a TV button is not supported")
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

        async with self.coordinator.tv_control_lock:
            total = len(payloads) * num_repeats
            sent = 0
            for _ in range(num_repeats):
                for command in payloads:
                    # Resolve identifiers after acquiring the lock, including
                    # after a coordinator refresh or a queued key sequence.
                    device = self._device
                    if device is None or not self.available:
                        raise HomeAssistantError("The ORVIBO TV remote is unavailable")
                    entry_data = self.coordinator.entry.data
                    try:
                        await self.hass.async_add_executor_job(
                            control_device,
                            entry_data[CONF_HOST],
                            self.coordinator.data.binary_user_name,
                            self.coordinator.data.binary_password,
                            entry_data[CONF_FAMILY_ID],
                            self._device_id,
                            device.cloud_uid,
                            command.order,
                            command.value1,
                            command.value2,
                            command.value3,
                            command.value4,
                            command.properties,
                            command.infrared,
                        )
                    except (OrviboBinaryError, OSError, TimeoutError) as err:
                        raise HomeAssistantError(str(err)) from err
                    sent += 1
                    if sent < total and delay:
                        await asyncio.sleep(delay)
