"""Support for BMS_BLE switches for controlling charge/discharge MOSFETs."""

from collections.abc import Callable

from aiobmsble import BMSSample

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BTBmsConfigEntry
from .const import (
    ATTR_CHRG_MOSFET,
    ATTR_DISCHRG_MOSFET,
    DOMAIN,
    LOGGER,
)
from .coordinator import BTBmsCoordinator

PARALLEL_UPDATES = 0


class BmsSwitchEntityDescription(SwitchEntityDescription, frozen_or_thawed=True):
    """Describes BMS switch entity."""

    attr_fn: Callable[[BMSSample], dict[str, int | str]] | None = None


SWITCH_TYPES: list[BmsSwitchEntityDescription] = [
    BmsSwitchEntityDescription(
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        key=ATTR_CHRG_MOSFET,
        name="Charge MOSFET",
        translation_key=ATTR_CHRG_MOSFET,
    ),
    BmsSwitchEntityDescription(
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        key=ATTR_DISCHRG_MOSFET,
        name="Discharge MOSFET",
        translation_key=ATTR_DISCHRG_MOSFET,
    ),
]


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: BTBmsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add switches for passed config_entry in Home Assistant."""

    bms: BTBmsCoordinator = config_entry.runtime_data
    for descr in SWITCH_TYPES:
        if descr.key not in bms.data:
            continue
        async_add_entities(
            [BMSSwitch(bms, descr, format_mac(config_entry.unique_id))]
        )


class BMSSwitch(CoordinatorEntity[BTBmsCoordinator], SwitchEntity):
    """The generic BMS switch implementation for MOSFET control."""

    entity_description: BmsSwitchEntityDescription

    def __init__(
        self,
        bms: BTBmsCoordinator,
        descr: BmsSwitchEntityDescription,
        unique_id: str,
    ) -> None:
        """Initialize BMS switch."""
        self._attr_unique_id = f"{DOMAIN}-{unique_id}-{descr.key}"
        self._attr_device_info = bms.device_info
        self._attr_has_entity_name = True
        self.entity_description: BmsSwitchEntityDescription = descr
        super().__init__(bms)

    @property
    def is_on(self) -> bool | None:
        """Return True if the MOSFET is on (conducting)."""
        return bool(self.coordinator.data.get(self.entity_description.key))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the MOSFET (enable conduction)."""
        await self._set_mosfet_state(enable=True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the MOSFET (disable conduction)."""
        await self._set_mosfet_state(enable=False)

    async def _set_mosfet_state(self, enable: bool) -> None:
        """Set the MOSFET state.

        Args:
            enable: True to enable (turn on), False to disable (turn off)

        Raises:
            HomeAssistantError: If the control command fails
        """
        # Get the current state of both MOSFETs from coordinator data
        chrg_mosfet_on = bool(
            self.coordinator.data.get(ATTR_CHRG_MOSFET, False)
        )
        dischrg_mosfet_on = bool(
            self.coordinator.data.get(ATTR_DISCHRG_MOSFET, False)
        )

        # Determine the new state based on which switch is being controlled
        if self.entity_description.key == ATTR_CHRG_MOSFET:
            chrg_mosfet_on = enable
        else:  # ATTR_DISCHRG_MOSFET
            dischrg_mosfet_on = enable

        # Calculate the control byte (XX value) per BMS protocol
        # 0x00 = both enabled (release software close)
        # 0x01 = charging disabled
        # 0x02 = discharging disabled
        # 0x03 = both disabled
        if chrg_mosfet_on and dischrg_mosfet_on:
            control_byte = 0x00
        elif not chrg_mosfet_on and dischrg_mosfet_on:
            control_byte = 0x01
        elif chrg_mosfet_on and not dischrg_mosfet_on:
            control_byte = 0x02
        else:  # both disabled
            control_byte = 0x03

        LOGGER.debug(
            "%s: Setting MOSFET state - Charge: %s, Discharge: %s (control byte: 0x%02X)",
            self.coordinator.name,
            chrg_mosfet_on,
            dischrg_mosfet_on,
            control_byte,
        )

        try:
            # Send the control command to the BMS
            await self.coordinator.async_control_mosfet(control_byte)
        except Exception as err:
            LOGGER.error(
                "%s: Failed to control MOSFET: %s",
                self.coordinator.name,
                err,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="mosfet_control_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        # Refresh the coordinator data to get the updated state
        await self.coordinator.async_request_refresh()
