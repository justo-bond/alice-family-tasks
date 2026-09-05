"""Task list coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_RECIPIENT_ID,
    CONF_RECIPIENT_NAME,
    CONF_RECIPIENTS,
    CONF_TODO_ENTITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class FamilyTasksCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep current task counts available as native sensor state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
            always_update=False,
        )
        self.entry = entry

    @property
    def recipients(self) -> list[dict[str, Any]]:
        """Return configured recipients."""
        return list(self.entry.options.get(CONF_RECIPIENTS, []))

    async def _async_update_data(self) -> dict[str, Any]:
        recipients = self.recipients
        entities = [item[CONF_TODO_ENTITY] for item in recipients]
        today = dt_util.now().date().isoformat()
        if not entities:
            return {"total": 0, "recipients": [], "day": today}

        response = await self.hass.services.async_call(
            "todo",
            "get_items",
            {},
            target={"entity_id": entities},
            blocking=True,
            return_response=True,
        )
        result: list[dict[str, Any]] = []
        total = 0
        for recipient in recipients:
            entity_id = recipient[CONF_TODO_ENTITY]
            items = (response or {}).get(entity_id, {}).get("items", [])
            visible = [
                item
                for item in items
                if item.get("status") == "needs_action"
                and (not item.get("due") or str(item["due"])[:10] <= today)
            ]
            total += len(visible)
            result.append(
                {
                    "id": recipient[CONF_RECIPIENT_ID],
                    "name": recipient[CONF_RECIPIENT_NAME],
                    "todo_entity": entity_id,
                    "count": len(visible),
                }
            )
        return {"total": total, "recipients": result, "day": today}
