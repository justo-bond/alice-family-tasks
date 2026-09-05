"""Summary sensor for Alice Family Tasks."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FamilyTasksRuntime
from .const import CARD_URL, CONF_WEBHOOK_ID, DOMAIN
from .coordinator import FamilyTasksCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the summary sensor."""
    runtime: FamilyTasksRuntime = entry.runtime_data
    async_add_entities([FamilyTasksSummarySensor(runtime.coordinator, entry)])


class FamilyTasksSummarySensor(CoordinatorEntity[FamilyTasksCoordinator], SensorEntity):
    """Expose visible task counts and card metadata."""

    _attr_icon = "mdi:clipboard-check-outline"
    _attr_has_entity_name = True
    _attr_name = "Актуальные задачи"

    def __init__(self, coordinator: FamilyTasksCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_current_tasks"

    @property
    def native_value(self) -> int:
        return int(self.coordinator.data.get("total", 0))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "recipients": self.coordinator.data.get("recipients", []),
            "day": self.coordinator.data.get("day"),
            "card_url": CARD_URL,
            "webhook_path": f"/api/webhook/{self._entry.data[CONF_WEBHOOK_ID]}",
            "integration": DOMAIN,
        }
