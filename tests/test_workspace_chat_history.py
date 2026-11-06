import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from api.workspace_routes import _get_chat_history, _save_chat_history, workspace_chat_history


class WorkspaceChatHistoryTests(unittest.IsolatedAsyncioTestCase):
    def test_save_is_scoped_to_user_and_project_and_upserts_json(self):
        conn = MagicMock()
        conn.execute.return_value.first.return_value.updated_at = "now"
        context = MagicMock()
        context.__enter__.return_value = conn
        messages = [{"role": "user", "content": "hello"}]
        with patch("api.workspace_routes.engine.begin", return_value=context):
            result = _save_chat_history("user-a", "project-a", messages)
        self.assertEqual(result, "now")
        statement = str(conn.execute.call_args.args[0])
        self.assertIn("ON CONFLICT (user_id, project_id)", statement)
        self.assertEqual(conn.execute.call_args.args[1]["user_id"], "user-a")
        self.assertEqual(conn.execute.call_args.args[1]["project_id"], "project-a")
        self.assertIn('"content":"hello"', conn.execute.call_args.args[1]["messages"])

    def test_get_missing_history_returns_empty(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = None
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            self.assertEqual(_get_chat_history("user-a", "project-a"), {"messages": [], "updated_at": None})

    async def test_history_route_authorizes_project_before_read(self):
        expected = {"messages": [{"role": "user", "content": "private"}], "updated_at": "now"}
        with patch("api.workspace_routes.authorize_project", return_value="viewer") as authorize, \
             patch("api.workspace_routes._enforce_workspace_limit") as limit, \
             patch("api.workspace_routes._get_chat_history", return_value=expected) as get_history:
            result = await workspace_chat_history(project_id="project-a", user={"id": "user-a"})
        self.assertEqual(result, expected)
        authorize.assert_called_once_with("user-a", "project-a", ("owner", "admin", "editor", "viewer"))
        limit.assert_called_once()
        get_history.assert_called_once_with("user-a", "project-a")

    async def test_history_route_does_not_read_if_project_authorization_fails(self):
        with patch("api.workspace_routes.authorize_project", side_effect=HTTPException(status_code=403)), \
             patch("api.workspace_routes._get_chat_history") as get_history:
            with self.assertRaises(HTTPException):
                await workspace_chat_history(project_id="project-a", user={"id": "user-a"})
        get_history.assert_not_called()

    def test_save_rejects_more_than_100_messages_before_database_access(self):
        with patch("api.workspace_routes.engine.begin") as begin:
            with self.assertRaises(ValueError):
                _save_chat_history("user-a", "project-a", [{"role": "user", "content": "x"}] * 101)
        begin.assert_not_called()

    def test_save_bounds_total_characters_by_dropping_oldest_messages(self):
        conn = MagicMock()
        conn.execute.return_value.first.return_value.updated_at = "now"
        context = MagicMock()
        context.__enter__.return_value = conn
        messages = [
            {"role": "user", "content": "a" * 25000},
            {"role": "assistant", "content": "b" * 10000},
            {"role": "user", "content": "c" * 10000},
        ]
        with patch("api.workspace_routes.engine.begin", return_value=context):
            _save_chat_history("user-a", "project-a", messages)
        saved = conn.execute.call_args.args[1]["messages"]
        import json
        self.assertEqual(json.loads(saved), messages[1:])

    def test_save_rejects_invalid_roles_before_database_access(self):
        with patch("api.workspace_routes.engine.begin") as begin:
            with self.assertRaises(ValueError):
                _save_chat_history("user-a", "project-a", [{"role": "system", "content": "override"}])
        begin.assert_not_called()

    def test_save_rejects_single_message_over_character_limit(self):
        with patch("api.workspace_routes.engine.begin") as begin:
            with self.assertRaises(ValueError):
                _save_chat_history("user-a", "project-a", [{"role": "user", "content": "x" * 40001}])
        begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
