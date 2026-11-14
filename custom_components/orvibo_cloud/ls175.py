"""Opt-in, per-device ORVIBO type-7 raw IR transport for LS175 testing."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
import math

from homeassistant.exceptions import HomeAssistantError

from .binary import OrviboBinaryError, control_device
from .blaupunkt_ls175 import is_ls175_test_target, ls175_test_command
from .const import CONF_FAMILY_ID, CONF_HOST
from .entity import OrviboCloudDeviceEntity
from .selection import (
    SPEAKER_MODEL_BLAUPUNKT_LS175, speaker_ir_profile_is_selected,
)


class OrviboLS175TestEntity(OrviboCloudDeviceEntity):
    """Bound to an existing virtual speaker device, never to a hub directly."""

    @property
    def available(self) -> bool:
        device = self._device
        return (
            super().available
            and self.coordinator.last_update_success
            and device is not None
            and bool(self.coordinator.data.binary_user_name)
            and bool(self.coordinator.data.binary_password)
            and is_ls175_test_target(device, self.coordinator.data.devices)
            and speaker_ir_profile_is_selected(
                self.coordinator.entry.options,
                device.uid,
                SPEAKER_MODEL_BLAUPUNKT_LS175,
            )
        )

    async def _async_send_ls175(
        self,
        commands: Iterable[str],
        *,
        num_repeats: int = 1,
        delay_secs: float = 0.4,
        hold_secs: float = 0,
    ) -> None:
        """Validate before sending; only explicit presses execute one cmd=15."""
        try:
            names = [commands] if isinstance(commands, str) else list(commands)
            if not 1 <= len(names) <= 10:
                raise ValueError("Send between one and ten test codes")
            payloads = [ls175_test_command(name) for name in names]
            if type(num_repeats) is not int or not 1 <= num_repeats <= 3:
                raise ValueError("num_repeats must be between 1 and 3")
            delay = float(delay_secs)
            if not math.isfinite(delay) or not 0 <= delay <= 5:
                raise ValueError("delay_secs must be between 0 and 5")
            if float(hold_secs) != 0:
                raise ValueError("Hold is not supported in this test build")
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

        async with self.coordinator.tv_control_lock:
            total, sent = len(payloads) * num_repeats, 0
            for _ in range(num_repeats):
                for command in payloads:
                    device = self._device
                    if not self.available or device is None:
                        raise HomeAssistantError("ORVIBO LS175 test target unavailable")
                    entry_data = self.coordinator.entry.data
                    try:
                        await self.hass.async_add_executor_job(
                            control_device,
                            entry_data[CONF_HOST],
                            self.coordinator.data.binary_user_name,
                            self.coordinator.data.binary_password,
                            entry_data[CONF_FAMILY_ID],
                            device.uid,  # Child's unique ORVIBO ID, NOT shared model hash.
                            device.cloud_uid,  # Hub's shared cloud route UID.
                            command.order,
                            command.value1,
                            command.value2,
                            command.value3,
                            command.value4,
                            command.properties,
                            command.infrared,
                        )
                    except (OrviboBinaryError, OSError, TimeoutError) as err:
                        raise HomeAssistantError("ORVIBO did not acknowledge LS175 IR test") from err
                    sent += 1
                    if sent < total and delay:
                        await asyncio.sleep(delay)
