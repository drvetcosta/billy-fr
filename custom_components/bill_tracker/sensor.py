"""Sensor platform for Bill Tracker."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, EVENT_UPDATED
from .manager import BillTrackerManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Bill Tracker sensor."""
    manager: BillTrackerManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BillTrackerSensor(manager)])


class BillTrackerSensor(SensorEntity):
    """Expose the current month's bill total as a sensor."""

    _attr_name = "Totale bollette"
    _attr_unique_id = "bill_tracker_total"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:receipt-text"

    def __init__(self, manager: BillTrackerManager) -> None:
        self.manager = manager

    async def async_added_to_hass(self) -> None:
        """Subscribe to Bill Tracker updates."""
        self.async_on_remove(self.hass.bus.async_listen(EVENT_UPDATED, self._on_update))

    @callback
    def _on_update(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return the current month's total."""
        return self.manager.summary()["current_month"]

    @property
    def extra_state_attributes(self):
        """Expose compact summary data without duplicating the full database in Recorder."""
        return self.manager.summary()
