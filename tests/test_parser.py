import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = "custom_components.alice_family_tasks"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "custom_components" / "alice_family_tasks")]
sys.modules.setdefault(PACKAGE, package)


def load_module(name: str):
    path = ROOT / "custom_components" / "alice_family_tasks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load_module("const")
parser = load_module("parser")

RECIPIENTS = [
    {
        "id": "anna",
        "name": "Анна",
        "aliases": ["маме", "мне"],
        "todo_entity": "todo.anna",
    },
    {
        "id": "pargev",
        "name": "Паргев",
        "aliases": ["Паргеву", "сыну"],
        "todo_entity": "todo.pargev",
    },
]


class CommandParserTest(unittest.TestCase):
    def test_matches_arbitrary_recipient_alias(self):
        result = parser.parse_command(
            "Добавь задачу Паргеву взять форму завтра",
            RECIPIENTS,
            ["всем"],
            today=date(2026, 9, 5),
        )
        self.assertEqual(result.recipient_ids, ("pargev",))
        self.assertEqual(result.text, "взять форму")
        self.assertEqual(result.due, date(2026, 9, 6))

    def test_matches_all_recipients(self):
        result = parser.parse_command(
            "всем закрыть окна сегодня", RECIPIENTS, ["всем"], today=date(2026, 9, 5)
        )
        self.assertEqual(result.recipient_ids, ("anna", "pargev"))
        self.assertEqual(result.text, "закрыть окна")

    def test_parses_weekday(self):
        result = parser.parse_command(
            "маме позвонить врачу в понедельник",
            RECIPIENTS,
            ["всем"],
            today=date(2026, 9, 5),
        )
        self.assertEqual(result.recipient_ids, ("anna",))
        self.assertEqual(result.due, date(2026, 9, 7))

    def test_parses_vo_vtornik(self):
        result = parser.parse_command(
            "Паргеву тренировка во вторник",
            RECIPIENTS,
            ["всем"],
            today=date(2026, 9, 5),
        )
        self.assertEqual(result.text, "тренировка")
        self.assertEqual(result.due, date(2026, 9, 8))

    def test_preserves_time_in_task_text(self):
        result = parser.parse_command(
            "маме позвонить врачу в 18:00 завтра",
            RECIPIENTS,
            ["всем"],
            today=date(2026, 9, 5),
        )
        self.assertEqual(result.text, "позвонить врачу в 18:00")
        self.assertEqual(result.due, date(2026, 9, 6))

    def test_parses_calendar_date(self):
        result = parser.parse_command(
            "сыну соревнования 12 сентября",
            RECIPIENTS,
            ["всем"],
            today=date(2026, 9, 5),
        )
        self.assertEqual(result.text, "соревнования")
        self.assertEqual(result.due, date(2026, 9, 12))

    def test_rejects_conflicting_aliases(self):
        recipients = [
            *RECIPIENTS,
            {"id": "third", "name": "Бабушка", "aliases": ["маме"]},
        ]
        self.assertIn("маме", parser.validate_aliases(recipients, ["всем"]))


if __name__ == "__main__":
    unittest.main()
