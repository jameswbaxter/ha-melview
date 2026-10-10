"""Climate entity for a MelView unit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_WHOLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MelViewConfigEntry, MelViewCoordinator
from .entity import MelViewEntity
from .melview import MelViewDevice, MelViewError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MelViewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a climate entity per unit."""
    coordinator = entry.runtime_data
    async_add_entities(MelViewClimate(coordinator, device) for device in coordinator.devices)


class MelViewClimate(MelViewEntity, ClimateEntity):
    """A MelView unit as a climate entity."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: MelViewCoordinator, device: MelViewDevice) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = device.get_id()
        self._attr_hvac_modes = [HVACMode.OFF, *device.get_supported_modes()]
        self._attr_fan_modes = list(device.fan.values())
        halves = device.get_precision_halves()
        self._attr_precision = PRECISION_HALVES if halves else PRECISION_WHOLE
        self._attr_target_temperature_step = 0.5 if halves else 1.0

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._device.is_power_on():
            return HVACMode.OFF
        return self._device.get_mode()

    @property
    def current_temperature(self) -> float | None:
        return self._device.get_room_temperature()

    @property
    def target_temperature(self) -> float | None:
        return self._device.get_temperature()

    @property
    def min_temp(self) -> float:
        return self._device.get_temperature_range(self._device.get_mode())[0]

    @property
    def max_temp(self) -> float:
        return self._device.get_temperature_range(self._device.get_mode())[1]

    @property
    def fan_mode(self) -> str | None:
        return self._device.get_speed()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        outside = self._device.get_outside_temperature()
        return {"outside_temperature": outside} if outside is not None else None

    async def _command(self, action) -> None:
        try:
            await action
        except MelViewError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._command(self._device.async_set_temperature(float(temperature)))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._command(self._device.async_set_speed(fan_mode))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._command(self._device.async_power_off())
        else:
            await self._command(self._device.async_set_mode(hvac_mode))

    async def async_turn_on(self) -> None:
        await self._command(self._device.async_power_on())

    async def async_turn_off(self) -> None:
        await self._command(self._device.async_power_off())
