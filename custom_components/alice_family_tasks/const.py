"""Constants for Alice Family Tasks."""

from __future__ import annotations

DOMAIN = "alice_family_tasks"
PLATFORMS = ["sensor"]

CONF_ALIASES = "aliases"
CONF_ALL_ALIASES = "all_aliases"
CONF_INTEGRATION_NAME = "integration_name"
CONF_RECIPIENTS = "recipients"
CONF_RECIPIENT_ID = "id"
CONF_RECIPIENT_NAME = "name"
CONF_TODO_ENTITY = "todo_entity"
CONF_WEBHOOK_ID = "webhook_id"

DEFAULT_ALL_ALIASES = ["всем", "для всех", "общее", "общая"]
DEFAULT_NAME = "Семейные задачи"
EVENT_REQUEST = "alice_family_tasks_request"
EVENT_RESPONSE = "alice_family_tasks_response"
LEGACY_EVENT_REQUEST = "yandex_intent"
LEGACY_EVENT_RESPONSE = "yandex_intent_response"

CARD_URL = "/alice_family_tasks/alice-family-tasks-card.js"
CARD_FILENAME = "alice-family-tasks-card.js"

SERVICE_ADD_TASK = "add_task"
SERVICE_PROCESS_COMMAND = "process_command"
