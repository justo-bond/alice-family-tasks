"""Russian command parser for family tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .const import CONF_ALIASES, CONF_RECIPIENT_ID, CONF_RECIPIENT_NAME

COMMAND_PREFIX = re.compile(
    r"^\s*(?:(?:добавь|добавить|создай|запиши|поставь)\s+"
    r"(?:(?:задачу|напоминание)\s+)?|напомни\s+)?",
    re.IGNORECASE,
)

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
WEEKDAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среду": 2,
    "четверг": 3,
    "пятницу": 4,
    "субботу": 5,
    "воскресенье": 6,
}

RELATIVE_RE = re.compile(r"(?<!\w)(?:(?:на|в)\s+)?(послезавтра|завтра|сегодня)(?!\w)")
MONTH_RE = re.compile(
    r"(?<!\w)(?:(?:на|в)\s+)?(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?!\w)"
)
NUMERIC_RE = re.compile(
    r"(?<!\w)(?:(?:на|в)\s+)?(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?(?!\w)"
)
WEEKDAY_RE = re.compile(r"(?<!\w)(?:(?:на|в)\s+)?(" + "|".join(WEEKDAYS) + r")(?!\w)")


@dataclass(frozen=True, slots=True)
class ParsedTask:
    """A parsed task command."""

    recipient_ids: tuple[str, ...]
    text: str
    due: date | None = None


def normalize(value: str) -> str:
    """Normalize text for matching while preserving date punctuation."""
    value = value.casefold().replace("ё", "е")
    value = re.sub(r"[,!?;:]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def split_aliases(value: str | list[str]) -> list[str]:
    """Convert a form value to a normalized alias list."""
    values = value if isinstance(value, list) else re.split(r"[,;\n]+", value)
    return list(
        dict.fromkeys(alias for item in values if (alias := normalize(str(item))))
    )


def _alias_pattern(alias: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in normalize(alias).split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)")


def validate_aliases(
    recipients: list[dict[str, Any]], all_aliases: list[str]
) -> dict[str, str]:
    """Return aliases that point to more than one target."""
    owners: dict[str, str] = {}
    conflicts: dict[str, str] = {}
    for recipient in recipients:
        aliases = [recipient[CONF_RECIPIENT_NAME], *recipient.get(CONF_ALIASES, [])]
        for alias in split_aliases(aliases):
            owner = owners.setdefault(alias, recipient[CONF_RECIPIENT_ID])
            if owner != recipient[CONF_RECIPIENT_ID]:
                conflicts[alias] = owner
    for alias in split_aliases(all_aliases):
        if alias in owners:
            conflicts[alias] = "all"
    return conflicts


def _find_recipients(
    command: str, recipients: list[dict[str, Any]], all_aliases: list[str]
) -> tuple[tuple[str, ...], tuple[int, int] | None]:
    matches: list[tuple[int, int, int, str]] = []
    for alias in split_aliases(all_aliases):
        if match := _alias_pattern(alias).search(command):
            matches.append((match.start(), -len(alias), match.end(), "__all__"))
    for recipient in recipients:
        aliases = [recipient[CONF_RECIPIENT_NAME], *recipient.get(CONF_ALIASES, [])]
        for alias in split_aliases(aliases):
            if match := _alias_pattern(alias).search(command):
                matches.append(
                    (
                        match.start(),
                        -len(alias),
                        match.end(),
                        recipient[CONF_RECIPIENT_ID],
                    )
                )
    if not matches:
        return (), None
    start, _length, end, recipient_id = min(matches)
    if recipient_id == "__all__":
        return tuple(item[CONF_RECIPIENT_ID] for item in recipients), (start, end)
    return (recipient_id,), (start, end)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_due(command: str, today: date) -> tuple[date | None, tuple[int, int] | None]:
    if match := RELATIVE_RE.search(command):
        days = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[match.group(1)]
        return today + timedelta(days=days), match.span()
    if match := NUMERIC_RE.search(command):
        day, month = int(match.group(1)), int(match.group(2))
        raw_year = match.group(3)
        year = int(raw_year) if raw_year else today.year
        if raw_year and year < 100:
            year += 2000
        candidate = _safe_date(year, month, day)
        if candidate and not raw_year and candidate < today:
            candidate = _safe_date(year + 1, month, day)
        return candidate, match.span() if candidate else None
    if match := MONTH_RE.search(command):
        day, month = int(match.group(1)), MONTHS[match.group(2)]
        year = today.year
        candidate = _safe_date(year, month, day)
        if candidate and candidate < today:
            candidate = _safe_date(year + 1, month, day)
        return candidate, match.span() if candidate else None
    if match := WEEKDAY_RE.search(command):
        weekday = WEEKDAYS[match.group(1)]
        delta = (weekday - today.weekday()) % 7 or 7
        return today + timedelta(days=delta), match.span()
    return None, None


def parse_command(
    raw_command: str,
    recipients: list[dict[str, Any]],
    all_aliases: list[str],
    *,
    today: date | None = None,
) -> ParsedTask:
    """Parse recipient aliases, task text, and an optional Russian date."""
    command = COMMAND_PREFIX.sub("", normalize(raw_command))
    recipient_ids, recipient_span = _find_recipients(command, recipients, all_aliases)
    due, due_span = _parse_due(command, today or datetime.now().astimezone().date())

    spans = sorted((span for span in (recipient_span, due_span) if span), reverse=True)
    for start, end in spans:
        command = command[:start] + " " + command[end:]
    text = re.sub(r"\s+", " ", command).strip(" ,:.-")
    return ParsedTask(recipient_ids=recipient_ids, text=text, due=due)
