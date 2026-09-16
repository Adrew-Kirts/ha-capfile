"""Sensor platform for the Capfile integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_CADRANS, CONF_PRM, CONF_SITE_NAME, DOMAIN, SIGNAL_UPDATE

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapfileSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with Capfile-specific metadata."""
    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[CapfileSensorDescription, ...] = (
    CapfileSensorDescription(
        key="month_kwh",
        data_key="month_kwh",
        name="Consommation ce mois",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
    ),
    CapfileSensorDescription(
        key="month_cost_variable",
        data_key="month_cost_variable",
        name="Coût consommation ce mois",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-eur",
    ),
    CapfileSensorDescription(
        key="month_subscription",
        data_key="month_subscription",
        name="Coût abonnement ce mois",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:calendar-month",
    ),
    CapfileSensorDescription(
        key="month_cost_total",
        data_key="month_cost_total",
        name="Coût total ce mois",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-multiple",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Capfile sensor entities."""
    has_soutirage = bool(entry.data.get(CONF_CADRANS, ""))
    if has_soutirage:
        async_add_entities(
            CapfileSensor(entry, description)
            for description in SENSOR_DESCRIPTIONS
        )


class CapfileSensor(RestoreEntity, SensorEntity):
    """A sensor that shows current-month aggregates from Capfile data."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        description: CapfileSensorDescription,
    ) -> None:
        self.entity_description: CapfileSensorDescription = description
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{description.key}"
        self._attr_native_value: float | None = None

        prm = entry.data.get(CONF_PRM, entry.entry_id)
        site = entry.data.get(CONF_SITE_NAME, prm)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prm)},
            name=f"Capfile – {site}",
            manufacturer="Capfile",
            model="Linky via Capfile",
            configuration_url="https://capfile.com",
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state and subscribe to sync updates."""
        await super().async_added_to_hass()

        # Restore last known value after HA restart
        if (last := await self.async_get_last_state()) and last.state not in (
            None, "unknown", "unavailable"
        ):
            try:
                self._attr_native_value = float(last.state)
            except ValueError:
                pass

        # Subscribe to updates fired after each sync
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self._entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Receive new sensor data from the sync and refresh state."""
        sensor_data: dict[str, Any] = (
            self.hass.data.get(DOMAIN, {})
            .get(self._entry.entry_id, {})
            .get("sensor_data", {})
        )
        value = sensor_data.get(self.entity_description.data_key)
        if value is not None:
            self._attr_native_value = float(value)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra attributes: per-cadran breakdown and last sync timestamp."""
        sensor_data: dict[str, Any] = (
            self.hass.data.get(DOMAIN, {})
            .get(self._entry.entry_id, {})
            .get("sensor_data", {})
        )
        attrs: dict[str, Any] = {}

        if self.entity_description.key == "month_kwh":
            attrs["par_cadran_kWh"] = sensor_data.get("month_kwh_by_cadran", {})
        elif self.entity_description.key in ("month_cost_variable", "month_cost_total"):
            attrs["par_cadran_EUR"] = sensor_data.get("month_cost_by_cadran", {})

        if last_sync := sensor_data.get("last_sync"):
            attrs["dernière_synchro"] = last_sync

        return attrs
