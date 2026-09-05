"""Thin Yandex Alice adapter for the Alice Family Tasks HA integration."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HELP_TEXT = (
    "Назовите получателя, задачу и при необходимости дату. "
    "Например: Паргеву взять форму завтра."
)


def _alice_response(text: str, *, end_session: bool, state: dict | None = None) -> dict:
    response = {
        "version": "1.0",
        "response": {"text": text, "end_session": end_session},
    }
    if state:
        response["session_state"] = state
    return response


def _send_to_home_assistant(command: str) -> dict:
    webhook_url = os.environ.get("HA_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise RuntimeError("HA_WEBHOOK_URL is not configured")

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"command": command[:512]}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=5.0)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def handler(event: dict, context) -> dict:
    del context
    request = event.get("request") or {}
    session = event.get("session") or {}
    session_state = (event.get("state") or {}).get("session") or {}
    command = str(
        request.get("command") or request.get("original_utterance") or ""
    ).strip()

    if session.get("new") and not command:
        return _alice_response(HELP_TEXT, end_session=False)

    normalized = command.casefold().replace("ё", "е")
    if normalized in {"помощь", "что ты умеешь", "что умеешь"}:
        return _alice_response(HELP_TEXT, end_session=False)
    if normalized in {"выход", "хватит", "отмена", "отмени"}:
        return _alice_response("Хорошо, ничего не добавляю.", end_session=True)

    pending = str(session_state.get("pending_command") or "").strip()
    full_command = " ".join(part for part in (command, pending) if part)
    if not full_command:
        return _alice_response(HELP_TEXT, end_session=False)

    try:
        result = _send_to_home_assistant(full_command)
    except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
        return _alice_response(
            "Не получилось связаться с Home Assistant. Попробуйте еще раз.",
            end_session=True,
        )

    if result.get("success"):
        return _alice_response(
            str(result.get("text") or "Задача добавлена."), end_session=True
        )

    error = result.get("error")
    can_retry = error in {"recipient_not_found", "empty_task"}
    return _alice_response(
        str(result.get("text") or "Не удалось добавить задачу."),
        end_session=not can_retry,
        state={"pending_command": full_command} if can_retry else None,
    )
