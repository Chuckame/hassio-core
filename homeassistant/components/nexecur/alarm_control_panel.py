"""Support for Verisure alarm control panels."""

from __future__ import annotations

import asyncio

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NexecurConfigEntry
from .api import NexecurAlarmStateEnum
from .const import CONF_PHONE_ID, CONF_SITE_ID, DOMAIN, LOGGER
from .coordinator import NexecurCoordinator

ALARM_STATE_TO_HA = {
    NexecurAlarmStateEnum.INACTIVE: AlarmControlPanelState.DISARMED,
    NexecurAlarmStateEnum.NIGHT: AlarmControlPanelState.ARMED_NIGHT,
    NexecurAlarmStateEnum.ACTIVE: AlarmControlPanelState.ARMED_AWAY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NexecurConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nexecur alarm control panel from a config entry."""
    async_add_entities(
        [NexecurAlarmPanelEntity(coordinator=entry.runtime_data.coordinator)]
    )


class NexecurAlarmPanelEntity(
    CoordinatorEntity[NexecurCoordinator], AlarmControlPanelEntity
):
    """Representation of a Nexecur alarm status."""

    _attr_code_arm_required = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_NIGHT
        | AlarmControlPanelEntityFeature.ARM_AWAY
    )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        assert self.coordinator.config_entry
        return DeviceInfo(
            name="Nexecur Alarm",
            manufacturer="Nexecur",
            identifiers={(DOMAIN, self.coordinator.config_entry.data[CONF_SITE_ID])},
            configuration_url="https://maprotectionmaison.fr",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this entity."""
        assert self.coordinator.config_entry
        return self.coordinator.config_entry.data[CONF_SITE_ID]

    async def _change_alarm_state(self, state: NexecurAlarmStateEnum) -> None:
        """Send set arm state command."""
        await self.coordinator.async_refresh()
        if not self.coordinator.last_update_success:
            LOGGER.error("Unable to change alarm state, coordinator is not ready")
            return
        previous_state = self.coordinator.data
        if previous_state == state:
            LOGGER.debug("Alarm is already in the desired state %s", state)
            return
        LOGGER.debug("Changing state from %s to %s", previous_state, state)
        assert self.coordinator.config_entry
        await self.coordinator.api.set_alarm_state(
            phone_id=self.coordinator.config_entry.data[CONF_PHONE_ID],
            site_id=self.coordinator.config_entry.data[CONF_SITE_ID],
            state=state,
        )
        # Accelerate refreshes to overcome the original sync delay
        for _ in range(30):
            if self.coordinator.data == state:
                break
            await asyncio.sleep(1)
            await self.coordinator.async_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        self._attr_alarm_state = AlarmControlPanelState.DISARMING
        self.async_write_ha_state()
        await self._change_alarm_state(NexecurAlarmStateEnum.INACTIVE)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send arm night command."""
        self._attr_alarm_state = AlarmControlPanelState.ARMING
        self.async_write_ha_state()
        await self._change_alarm_state(NexecurAlarmStateEnum.NIGHT)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        self._attr_alarm_state = AlarmControlPanelState.ARMING
        self.async_write_ha_state()
        await self._change_alarm_state(NexecurAlarmStateEnum.ACTIVE)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_alarm_state = ALARM_STATE_TO_HA.get(self.coordinator.data)
        self._attr_changed_by = "App"
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
