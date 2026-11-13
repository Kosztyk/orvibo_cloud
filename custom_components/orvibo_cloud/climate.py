"""Home Assistant climate entities for explicitly recognized IR profiles."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ac_backend import OrviboACBackend
from .ac_profiles import ACProfile, ac_profile
from .const import DOMAIN
from .coordinator import OrviboCloudCoordinator
from .entity import OrviboCloudDeviceEntity
from .selection import device_is_selected


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboClimate(coordinator, device.uid, profile)
        for device in coordinator.data.devices
        if device_is_selected(entry.options, device.uid)
        and (profile := ac_profile(device)) is not None
    )


class OrviboClimate(OrviboCloudDeviceEntity, ClimateEntity):
    """Expose only the capabilities listed by the matched profile."""

    _attr_name = None
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self, coordinator: OrviboCloudCoordinator, device_id: str, profile: ACProfile
    ) -> None:
        super().__init__(coordinator, device_id)
        self._profile = profile
        self._state = profile.default
        self._backend = OrviboACBackend(coordinator, profile)
        self._attr_unique_id = f"{device_id}_ir_climate"
        self._attr_hvac_modes = [HVACMode(mode) for mode in profile.modes]
        self._attr_supported_features = ClimateEntityFeature(0)
        if HVACMode.OFF in self._attr_hvac_modes:
            self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
        if profile.turn_on_mode is not None:
            self._attr_supported_features |= ClimateEntityFeature.TURN_ON
        if profile.temperatures:
            self._attr_min_temp = min(profile.temperatures)
            self._attr_max_temp = max(profile.temperatures)
            self._attr_target_temperature_step = profile.temperatures.step
            self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if profile.fans:
            self._attr_fan_modes = list(profile.fans)
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        if profile.swings:
            self._attr_swing_modes = list(profile.swings)
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
        if profile.presets:
            self._attr_preset_modes = list(profile.presets)
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

    @property
    def available(self) -> bool:
        device = self._device
        return (
            super().available
            and device is not None
            and ac_profile(device) is self._profile
            and self._backend.available(device)
        )

    @property
    def hvac_mode(self) -> HVACMode | None:
        return HVACMode(self._state.mode) if self._state.mode else None

    @property
    def target_temperature(self) -> int | None:
        return self._state.temperature

    @property
    def fan_mode(self) -> str | None:
        return self._state.fan

    @property
    def swing_mode(self) -> str | None:
        return self._state.swing

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self._async_change(swing=swing_mode)

    @property
    def preset_mode(self) -> str | None:
        return self._state.preset

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._async_change(preset=preset_mode)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._async_change(mode=str(hvac_mode))

    async def async_turn_on(self) -> None:
        mode = self._profile.turn_on_mode
        if mode is None:
            raise HomeAssistantError("This AC profile does not support turning on")
        await self._async_change(turn_on=True)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if type(temperature) not in (int, float) or not float(temperature).is_integer():
            raise HomeAssistantError("This AC profile requires a whole Celsius temperature")
        changes = {"temperature": int(temperature)}
        if (mode := kwargs.get("hvac_mode")) is not None:
            changes["mode"] = str(mode)
        await self._async_change(**changes)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._async_change(fan=fan_mode)

    async def _async_change(self, *, turn_on: bool = False, **changes: Any) -> None:
        # Share the transport lock with TV and derive the state after acquiring it.
        async with self.coordinator.tv_control_lock:
            device = self._device
            if device is None or not self.available:
                raise HomeAssistantError("The ORVIBO AC remote is unavailable")
            base = self._state
            if turn_on:
                mode = self._profile.turn_on_mode
                if self._profile.remember_settings:
                    mode = base.previous_mode or mode
                changes["mode"] = mode
            if base.mode in (None, "off"):
                base = self._profile.mode_defaults.get(changes.get("mode"), base)
            candidate = replace(base, **changes)
            local_settings = "mode" not in changes and candidate.mode in (None, "off")
            if local_settings and not self._profile.remember_settings:
                raise HomeAssistantError("Select an active AC mode before changing settings")
            if self._profile.remember_settings and candidate.mode not in (None, "off"):
                candidate = replace(candidate, previous_mode=candidate.mode)
            try:
                command = self._profile.command(
                    replace(candidate, mode="off") if local_settings else candidate
                )
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
            if not local_settings:
                await self._backend.async_send(device, command)
            if candidate.preset in self._profile.momentary_presets:
                candidate = replace(candidate, preset="none")
            self._state = candidate
            self.async_write_ha_state()
