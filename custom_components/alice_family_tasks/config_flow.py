"""Config flow for Alice Family Tasks."""

from __future__ import annotations

import secrets
import uuid
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.helpers import selector

from .const import (
    CONF_ALIASES,
    CONF_ALL_ALIASES,
    CONF_INTEGRATION_NAME,
    CONF_RECIPIENT_ID,
    CONF_RECIPIENT_NAME,
    CONF_RECIPIENTS,
    CONF_TODO_ENTITY,
    CONF_WEBHOOK_ID,
    DEFAULT_ALL_ALIASES,
    DEFAULT_NAME,
    DOMAIN,
)
from .parser import split_aliases, validate_aliases


def _recipient_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_RECIPIENT_NAME, default=defaults.get(CONF_RECIPIENT_NAME, "")
            ): selector.TextSelector(),
            vol.Required(
                CONF_ALIASES,
                default=", ".join(defaults.get(CONF_ALIASES, [])),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_TODO_ENTITY, default=defaults.get(CONF_TODO_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="todo")),
        }
    )


def _recipient_from_input(
    user_input: dict[str, Any], recipient_id: str | None = None
) -> dict[str, Any]:
    return {
        CONF_RECIPIENT_ID: recipient_id or uuid.uuid4().hex[:12],
        CONF_RECIPIENT_NAME: user_input[CONF_RECIPIENT_NAME].strip(),
        CONF_ALIASES: split_aliases(user_input[CONF_ALIASES]),
        CONF_TODO_ENTITY: user_input[CONF_TODO_ENTITY],
    }


class AliceFamilyTasksConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create an Alice Family Tasks entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the integration and its first recipient."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            recipient = _recipient_from_input(user_input)
            if not recipient[CONF_RECIPIENT_NAME]:
                errors[CONF_RECIPIENT_NAME] = "name_required"
            elif validate_aliases([recipient], DEFAULT_ALL_ALIASES):
                errors[CONF_ALIASES] = "alias_conflict"
            else:
                title = user_input[CONF_INTEGRATION_NAME].strip() or DEFAULT_NAME
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_INTEGRATION_NAME: title,
                        CONF_WEBHOOK_ID: f"alice_family_tasks_{secrets.token_urlsafe(18)}",
                    },
                    options={
                        CONF_RECIPIENTS: [recipient],
                        CONF_ALL_ALIASES: DEFAULT_ALL_ALIASES,
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INTEGRATION_NAME, default=DEFAULT_NAME
                ): selector.TextSelector(),
                **_recipient_schema().schema,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the recipient manager."""
        return AliceFamilyTasksOptionsFlow()


class AliceFamilyTasksOptionsFlow(OptionsFlowWithReload):
    """Manage recipients and aliases."""

    def __init__(self) -> None:
        self._options: dict[str, Any] | None = None
        self._selected_id: str | None = None

    @property
    def options(self) -> dict[str, Any]:
        if self._options is None:
            self._options = deepcopy(dict(self.config_entry.options))
        return self._options

    @property
    def recipients(self) -> list[dict[str, Any]]:
        return self.options.setdefault(CONF_RECIPIENTS, [])

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show recipient management actions."""
        menu = ["add_recipient", "general"]
        if self.recipients:
            menu[1:1] = ["edit_recipient", "remove_recipient"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a recipient."""
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = _recipient_from_input(user_input)
            proposed = [*self.recipients, candidate]
            if not candidate[CONF_RECIPIENT_NAME]:
                errors[CONF_RECIPIENT_NAME] = "name_required"
            elif candidate[CONF_TODO_ENTITY] in {
                item[CONF_TODO_ENTITY] for item in self.recipients
            }:
                errors[CONF_TODO_ENTITY] = "todo_in_use"
            elif validate_aliases(proposed, self.options.get(CONF_ALL_ALIASES, [])):
                errors[CONF_ALIASES] = "alias_conflict"
            else:
                self.recipients.append(candidate)
                return self._save()
        return self.async_show_form(
            step_id="add_recipient",
            data_schema=_recipient_schema(user_input),
            errors=errors,
        )

    async def async_step_edit_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a recipient to edit."""
        if user_input is not None:
            self._selected_id = user_input[CONF_RECIPIENT_ID]
            return await self.async_step_edit_recipient_details()
        options = [
            {"value": item[CONF_RECIPIENT_ID], "label": item[CONF_RECIPIENT_NAME]}
            for item in self.recipients
        ]
        return self.async_show_form(
            step_id="edit_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RECIPIENT_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_edit_recipient_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one recipient."""
        current = next(
            item
            for item in self.recipients
            if item[CONF_RECIPIENT_ID] == self._selected_id
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = _recipient_from_input(user_input, self._selected_id)
            proposed = [
                candidate if item[CONF_RECIPIENT_ID] == self._selected_id else item
                for item in self.recipients
            ]
            other_entities = {
                item[CONF_TODO_ENTITY]
                for item in self.recipients
                if item[CONF_RECIPIENT_ID] != self._selected_id
            }
            if not candidate[CONF_RECIPIENT_NAME]:
                errors[CONF_RECIPIENT_NAME] = "name_required"
            elif candidate[CONF_TODO_ENTITY] in other_entities:
                errors[CONF_TODO_ENTITY] = "todo_in_use"
            elif validate_aliases(proposed, self.options.get(CONF_ALL_ALIASES, [])):
                errors[CONF_ALIASES] = "alias_conflict"
            else:
                self.options[CONF_RECIPIENTS] = proposed
                return self._save()
        return self.async_show_form(
            step_id="edit_recipient_details",
            data_schema=_recipient_schema(user_input or current),
            errors=errors,
        )

    async def async_step_remove_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a recipient configuration without deleting its todo list."""
        if user_input is not None:
            selected = user_input[CONF_RECIPIENT_ID]
            self.options[CONF_RECIPIENTS] = [
                item for item in self.recipients if item[CONF_RECIPIENT_ID] != selected
            ]
            return self._save()
        options = [
            {"value": item[CONF_RECIPIENT_ID], "label": item[CONF_RECIPIENT_NAME]}
            for item in self.recipients
        ]
        return self.async_show_form(
            step_id="remove_recipient",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RECIPIENT_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure aliases that add a task to every list."""
        errors: dict[str, str] = {}
        if user_input is not None:
            aliases = split_aliases(user_input[CONF_ALL_ALIASES])
            if validate_aliases(self.recipients, aliases):
                errors[CONF_ALL_ALIASES] = "alias_conflict"
            else:
                self.options[CONF_ALL_ALIASES] = aliases
                return self._save()
        current = ", ".join(self.options.get(CONF_ALL_ALIASES, DEFAULT_ALL_ALIASES))
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALL_ALIASES, default=current
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
        )
