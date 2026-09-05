"""Alice Family Tasks integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components import webhook
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_ALIASES,
    CONF_ALL_ALIASES,
    CONF_RECIPIENT_ID,
    CONF_RECIPIENT_NAME,
    CONF_RECIPIENTS,
    CONF_TODO_ENTITY,
    CONF_WEBHOOK_ID,
    DEFAULT_ALL_ALIASES,
    DOMAIN,
    EVENT_REQUEST,
    EVENT_RESPONSE,
    LEGACY_EVENT_REQUEST,
    LEGACY_EVENT_RESPONSE,
    PLATFORMS,
    SERVICE_ADD_TASK,
    SERVICE_PROCESS_COMMAND,
)
from .coordinator import FamilyTasksCoordinator
from .parser import ParsedTask, normalize, parse_command, split_aliases

CONF_COMMAND = "command"
CONF_DUE = "due"
CONF_ENTRY_ID = "entry_id"
CONF_RECIPIENT = "recipient"
CONF_TEXT = "text"


@dataclass(slots=True)
class FamilyTasksRuntime:
    """Runtime data for one config entry."""

    coordinator: FamilyTasksCoordinator


def _entry_for_call(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Unknown Alice Family Tasks entry")
        return entry
    if len(entries) != 1:
        raise ServiceValidationError("entry_id is required when multiple entries exist")
    return entries[0]


def _recipient_by_value(entry: ConfigEntry, value: str) -> dict[str, Any] | None:
    wanted = normalize(value)
    for recipient in entry.options.get(CONF_RECIPIENTS, []):
        candidates = [
            recipient[CONF_RECIPIENT_ID],
            recipient[CONF_RECIPIENT_NAME],
            *recipient.get(CONF_ALIASES, []),
        ]
        if wanted in split_aliases([str(item) for item in candidates]):
            return recipient
    return None


async def _add_parsed_task(
    hass: HomeAssistant, entry: ConfigEntry, parsed: ParsedTask
) -> list[str]:
    recipients = entry.options.get(CONF_RECIPIENTS, [])
    selected = [
        item for item in recipients if item[CONF_RECIPIENT_ID] in parsed.recipient_ids
    ]
    data: dict[str, Any] = {"item": parsed.text}
    if parsed.due:
        data["due_date"] = parsed.due.isoformat()
    for recipient in selected:
        await hass.services.async_call(
            "todo",
            "add_item",
            data,
            target={"entity_id": recipient[CONF_TODO_ENTITY]},
            blocking=True,
        )
    runtime: FamilyTasksRuntime = entry.runtime_data
    await runtime.coordinator.async_request_refresh()
    return [item[CONF_RECIPIENT_NAME] for item in selected]


async def _process_command(
    hass: HomeAssistant, entry: ConfigEntry, command: str
) -> dict[str, Any]:
    recipients = list(entry.options.get(CONF_RECIPIENTS, []))
    parsed = parse_command(
        command,
        recipients,
        list(entry.options.get(CONF_ALL_ALIASES, DEFAULT_ALL_ALIASES)),
        today=dt_util.now().date(),
    )
    if not parsed.recipient_ids:
        names = ", ".join(item[CONF_RECIPIENT_NAME] for item in recipients)
        return {
            "success": False,
            "text": f"Не поняла, кому добавить задачу. Доступные получатели: {names}.",
            "error": "recipient_not_found",
        }
    if not parsed.text:
        return {
            "success": False,
            "text": "Не услышала текст задачи.",
            "error": "empty_task",
        }
    names = await _add_parsed_task(hass, entry, parsed)
    due_text = f" на {parsed.due.strftime('%d.%m')}" if parsed.due else ""
    target_text = ", ".join(names)
    return {
        "success": True,
        "text": f"Добавила для {target_text}: {parsed.text}{due_text}.",
        "recipients": names,
        "task": parsed.text,
        "due": parsed.due.isoformat() if parsed.due else None,
    }


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the card endpoint and integration services."""
    card_path = Path(__file__).parent / "www" / CARD_FILENAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), cache_headers=False)]
    )

    async def process_service(call: ServiceCall) -> dict[str, Any]:
        entry = _entry_for_call(hass, call.data.get(CONF_ENTRY_ID))
        return await _process_command(hass, entry, call.data[CONF_COMMAND])

    async def add_service(call: ServiceCall) -> dict[str, Any]:
        entry = _entry_for_call(hass, call.data.get(CONF_ENTRY_ID))
        recipient = _recipient_by_value(entry, call.data[CONF_RECIPIENT])
        if recipient is None:
            raise ServiceValidationError("Unknown recipient")
        due = call.data.get(CONF_DUE)
        parsed = ParsedTask(
            recipient_ids=(recipient[CONF_RECIPIENT_ID],),
            text=call.data[CONF_TEXT].strip(),
            due=due,
        )
        names = await _add_parsed_task(hass, entry, parsed)
        return {"success": True, "recipients": names}

    hass.services.async_register(
        DOMAIN,
        SERVICE_PROCESS_COMMAND,
        process_service,
        schema=vol.Schema(
            {
                vol.Required(CONF_COMMAND): cv.string,
                vol.Optional(CONF_ENTRY_ID): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TASK,
        add_service,
        schema=vol.Schema(
            {
                vol.Required(CONF_RECIPIENT): cv.string,
                vol.Required(CONF_TEXT): cv.string,
                vol.Optional(CONF_DUE): cv.date,
                vol.Optional(CONF_ENTRY_ID): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured family task board."""
    coordinator = FamilyTasksCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = FamilyTasksRuntime(coordinator)

    entities = [item[CONF_TODO_ENTITY] for item in coordinator.recipients]
    if entities:

        @callback
        def request_refresh(_event: Event) -> None:
            hass.async_create_task(coordinator.async_request_refresh())

        entry.async_on_unload(
            async_track_state_change_event(hass, entities, request_refresh)
        )

    async def handle_event(event: Event) -> None:
        command = str(
            event.data.get(CONF_COMMAND) or event.data.get(CONF_TEXT) or ""
        ).strip()
        result = await _process_command(hass, entry, command)
        response_type = (
            LEGACY_EVENT_RESPONSE
            if event.event_type == LEGACY_EVENT_REQUEST
            else EVENT_RESPONSE
        )
        hass.bus.async_fire(
            response_type,
            {"text": result["text"], "end_session": True, **result},
        )

    entry.async_on_unload(hass.bus.async_listen(EVENT_REQUEST, handle_event))
    entry.async_on_unload(hass.bus.async_listen(LEGACY_EVENT_REQUEST, handle_event))

    async def remove_completed(_now: Any) -> None:
        """Remove completed rows after the dashboard day changes."""
        entities = [item[CONF_TODO_ENTITY] for item in coordinator.recipients]
        if entities:
            await hass.services.async_call(
                "todo",
                "remove_completed_items",
                {},
                target={"entity_id": entities},
                blocking=True,
            )
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(hass, remove_completed, hour=0, minute=0, second=5)
    )

    async def handle_webhook(
        _hass: HomeAssistant, _webhook_id: str, request: web.Request
    ) -> web.Response:
        payload = await request.json()
        command = str(payload.get(CONF_COMMAND) or "").strip()
        if not command and payload.get(CONF_RECIPIENT) and payload.get(CONF_TEXT):
            command = f"{payload[CONF_RECIPIENT]} {payload[CONF_TEXT]} {payload.get('when', '')}"
        result = await _process_command(hass, entry, command)
        return web.json_response(result, status=200 if result["success"] else 400)

    webhook.async_register(
        hass,
        DOMAIN,
        entry.title,
        entry.data[CONF_WEBHOOK_ID],
        handle_webhook,
        allowed_methods=["POST"],
    )
    entry.async_on_unload(
        lambda: webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
