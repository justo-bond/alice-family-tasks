import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import index


class AliceAdapterTest(unittest.TestCase):
    def test_forwards_the_complete_utterance(self):
        event = {
            "version": "1.0",
            "session": {"new": False},
            "request": {"command": "Паргеву собрать рюкзак завтра"},
        }
        with patch(
            "index._send_to_home_assistant",
            return_value={
                "success": True,
                "text": "Добавила для Паргев: собрать рюкзак.",
            },
        ) as send:
            result = index.handler(event, None)

        send.assert_called_once_with("Паргеву собрать рюкзак завтра")
        self.assertTrue(result["response"]["end_session"])

    def test_keeps_command_when_home_assistant_needs_recipient(self):
        event = {
            "version": "1.0",
            "session": {"new": False},
            "request": {"command": "купить хлеб"},
        }
        with patch(
            "index._send_to_home_assistant",
            return_value={
                "success": False,
                "error": "recipient_not_found",
                "text": "Кому добавить?",
            },
        ):
            result = index.handler(event, None)

        self.assertFalse(result["response"]["end_session"])
        self.assertEqual(result["session_state"]["pending_command"], "купить хлеб")

    def test_combines_the_follow_up_with_pending_command(self):
        event = {
            "version": "1.0",
            "session": {"new": False},
            "state": {"session": {"pending_command": "купить хлеб"}},
            "request": {"command": "маме"},
        }
        with patch(
            "index._send_to_home_assistant",
            return_value={"success": True, "text": "Добавила."},
        ) as send:
            index.handler(event, None)

        send.assert_called_once_with("маме купить хлеб")

    @patch("index.urllib.request.urlopen")
    def test_posts_raw_command(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"success": True, "text": "Готово"}
        ).encode()
        urlopen.return_value = response

        with patch.dict(os.environ, {"HA_WEBHOOK_URL": "https://example.test/hook"}):
            result = index._send_to_home_assistant("маме позвонить врачу")

        self.assertTrue(result["success"])
        request = urlopen.call_args.args[0]
        self.assertEqual(
            json.loads(request.data.decode()), {"command": "маме позвонить врачу"}
        )

    @patch("index.urllib.request.urlopen")
    def test_reads_structured_http_error(self, urlopen):
        body = io.BytesIO(
            json.dumps(
                {"success": False, "error": "empty_task", "text": "Что добавить?"}
            ).encode()
        )
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test/hook", 400, "Bad Request", {}, body
        )

        with patch.dict(os.environ, {"HA_WEBHOOK_URL": "https://example.test/hook"}):
            result = index._send_to_home_assistant("маме")

        self.assertEqual(result["error"], "empty_task")


if __name__ == "__main__":
    unittest.main()
