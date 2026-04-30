"""Test the BLE Battery Management System integration switch definition."""

from datetime import timedelta
from typing import Final
from unittest.mock import AsyncMock, patch

from aiobmsble import BMSSample
from habluetooth import BluetoothServiceInfoBleak
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bms_ble.const import (
    ATTR_CHRG_MOSFET,
    ATTR_DISCHRG_MOSFET,
    DOMAIN,
    UPDATE_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
import homeassistant.util.dt as dt_util

from .bluetooth import inject_bluetooth_service_info_bleak
from .conftest import mock_config, mock_devinfo_min, mock_update_full

SWITCH_PREFIX: Final[str] = "switch.config_test_dummy_bms"


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_switch_creation(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test that switches are created for MOSFETs."""

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", mock_update_full)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    assert config in hass.config_entries.async_entries()
    assert config.state is ConfigEntryState.LOADED

    # Check that both switches are created
    chrg_switch: State | None = hass.states.get(f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}")
    dischrg_switch: State | None = hass.states.get(
        f"{SWITCH_PREFIX}_{ATTR_DISCHRG_MOSFET}"
    )

    assert chrg_switch is not None
    assert dischrg_switch is not None
    assert chrg_switch.state == STATE_OFF  # Initially off per mock_update_full
    assert dischrg_switch.state == STATE_OFF


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_switch_state_updates(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test that switch states update from BMS data."""

    async def patch_async_update(_self) -> BMSSample:
        """Patch async_update to return MOSFETs on."""
        return await mock_update_full(_self) | {
            ATTR_CHRG_MOSFET: True,
            ATTR_DISCHRG_MOSFET: True,
        }

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", mock_update_full)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Verify initial state (off)
    chrg_switch = hass.states.get(f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}")
    assert chrg_switch.state == STATE_OFF

    # Update with MOSFETs on
    monkeypatch.setattr(f"{bms_class}.async_update", patch_async_update)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=UPDATE_INTERVAL))
    await hass.async_block_till_done()

    # Verify updated state (on)
    chrg_switch = hass.states.get(f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}")
    dischrg_switch = hass.states.get(f"{SWITCH_PREFIX}_{ATTR_DISCHRG_MOSFET}")
    assert chrg_switch.state == STATE_ON
    assert dischrg_switch.state == STATE_ON


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_turn_on_charge_mosfet(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test turning on the charge MOSFET."""

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", mock_update_full)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Mock the send_command method
    with patch(
        "custom_components.bms_ble.coordinator.BTBmsCoordinator.async_control_mosfet",
        new_callable=AsyncMock,
    ) as mock_control:
        # Turn on charge MOSFET
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}"},
            blocking=True,
        )

        # Verify control_mosfet was called with correct byte (0x00 = both enabled)
        mock_control.assert_called_once_with(0x00)


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_turn_off_charge_mosfet(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test turning off the charge MOSFET."""

    async def patch_async_update_on(_self) -> BMSSample:
        """Return MOSFETs on."""
        return await mock_update_full(_self) | {
            ATTR_CHRG_MOSFET: True,
            ATTR_DISCHRG_MOSFET: True,
        }

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", patch_async_update_on)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Mock the send_command method
    with patch(
        "custom_components.bms_ble.coordinator.BTBmsCoordinator.async_control_mosfet",
        new_callable=AsyncMock,
    ) as mock_control:
        # Turn off charge MOSFET (discharge still on)
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}"},
            blocking=True,
        )

        # Verify control_mosfet was called with correct byte (0x02 = discharge enabled only)
        mock_control.assert_called_once_with(0x02)


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_turn_off_discharge_mosfet(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test turning off the discharge MOSFET."""

    async def patch_async_update_on(_self) -> BMSSample:
        """Return MOSFETs on."""
        return await mock_update_full(_self) | {
            ATTR_CHRG_MOSFET: True,
            ATTR_DISCHRG_MOSFET: True,
        }

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", patch_async_update_on)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Mock the send_command method
    with patch(
        "custom_components.bms_ble.coordinator.BTBmsCoordinator.async_control_mosfet",
        new_callable=AsyncMock,
    ) as mock_control:
        # Turn off discharge MOSFET (charge still on)
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": f"{SWITCH_PREFIX}_{ATTR_DISCHRG_MOSFET}"},
            blocking=True,
        )

        # Verify control_mosfet was called with correct byte (0x01 = charging enabled only)
        mock_control.assert_called_once_with(0x01)


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_control_both_mosfets_off(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test turning off both MOSFETs."""

    async def patch_async_update_on(_self) -> BMSSample:
        """Return MOSFETs on."""
        return await mock_update_full(_self) | {
            ATTR_CHRG_MOSFET: True,
            ATTR_DISCHRG_MOSFET: True,
        }

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", patch_async_update_on)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Mock the send_command method
    with patch(
        "custom_components.bms_ble.coordinator.BTBmsCoordinator.async_control_mosfet",
        new_callable=AsyncMock,
    ) as mock_control:
        # Turn off discharge MOSFET first
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": f"{SWITCH_PREFIX}_{ATTR_DISCHRG_MOSFET}"},
            blocking=True,
        )
        # Then turn off charge MOSFET
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": f"{SWITCH_PREFIX}_{ATTR_CHRG_MOSFET}"},
            blocking=True,
        )

        # Verify last call was with 0x03 (both disabled)
        assert mock_control.call_count == 2
        assert mock_control.call_args_list[1][0][0] == 0x03


@pytest.mark.usefixtures(
    "enable_bluetooth", "patch_default_bleak_client", "patch_entity_enabled_default"
)
async def test_control_mosfet_checksum(
    monkeypatch: pytest.MonkeyPatch,
    bt_discovery: BluetoothServiceInfoBleak,
    hass: HomeAssistant,
) -> None:
    """Test MOSFET control command checksum calculation."""

    bms_class: Final[str] = "aiobmsble.bms.dummy_bms.BMS"
    monkeypatch.setattr(f"{bms_class}.device_info", mock_devinfo_min)
    monkeypatch.setattr(f"{bms_class}.async_update", mock_update_full)

    config: MockConfigEntry = mock_config()
    config.add_to_hass(hass)

    inject_bluetooth_service_info_bleak(hass, bt_discovery)

    assert await hass.config_entries.async_setup(config.entry_id)
    await hass.async_block_till_done()

    # Test checksum calculation
    # Frame: DD 5A E1 02 00 01 (for control_byte=0x01)
    # Sum: 0xDD + 0x5A + 0xE1 + 0x02 + 0x00 + 0x01 = 0x21B
    # Checksum: (~0x21B + 1) & 0xFFFF = 0xFDE5
    # So CHECKSUM_H = 0xFD, CHECKSUM_L = 0xE5

    mock_device = AsyncMock()
    captured_frames = []

    async def capture_send_command(frame):
        captured_frames.append(frame)

    mock_device.send_command = capture_send_command

    coordinator = hass.data[DOMAIN]["cc:cc:cc:cc:cc:cc"][0]
    coordinator._device = mock_device

    await coordinator.async_control_mosfet(0x01)

    assert len(captured_frames) == 1
    frame = captured_frames[0]

    # Verify frame structure
    assert frame[0] == 0xDD  # Start bit
    assert frame[1] == 0x5A  # Write command
    assert frame[2] == 0xE1  # MOSFET control command
    assert frame[3] == 0x02  # Data length
    assert frame[4] == 0x00  # Reserved
    assert frame[5] == 0x01  # Control byte
    assert frame[8] == 0x77  # Stop bit

    # Verify checksum
    checksum_h = frame[6]
    checksum_l = frame[7]
    checksum = (checksum_h << 8) | checksum_l

    # Calculate expected checksum
    payload_sum = sum(frame[:6]) & 0xFFFF
    expected_checksum = ((~payload_sum) + 1) & 0xFFFF

    assert checksum == expected_checksum
