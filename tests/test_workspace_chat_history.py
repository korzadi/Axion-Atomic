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

    def test_save_trims_oldest_messages_to_100_before_database_write(self):
        conn = MagicMock()
        conn.execute.return_value.first.return_value.updated_at = "now"
        context = MagicMock()
        context.__enter__.return_value = conn
        messages = [{"role": "user", "content": str(index)} for index in range(101)]
        with patch("api.workspace_routes.engine.begin", return_value=context):
            _save_chat_history("user-a", "project-a", messages)
        import json
        saved = json.loads(conn.execute.call_args.args[1]["messages"])
        self.assertEqual(len(saved), 100)
        self.assertEqual(saved[0]["content"], "1")

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


    def test_get_history_query_requires_both_user_and_project_scope(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": [{"role": "user", "content": "private"}],
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            result = _get_chat_history("user-a", "project-a")
        statement = " ".join(str(conn.execute.call_args.args[0]).split())
        self.assertIn("WHERE user_id=:user_id AND project_id=:project_id", statement)
        self.assertEqual(conn.execute.call_args.args[1], {"user_id": "user-a", "project_id": "project-a"})
        self.assertEqual(result["messages"][0]["content"], "private")

    def test_get_history_rejects_more_than_100_stored_messages(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": [{"role": "user", "content": "x"} for _ in range(101)],
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            with self.assertRaises(ValueError):
                _get_chat_history("user-a", "project-a")

    def test_get_history_rejects_malformed_json(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": "{not-json",
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            with self.assertRaises(ValueError):
                _get_chat_history("user-a", "project-a")


    def test_get_history_rejects_untrusted_roles_in_stored_records(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": [{"role": "system", "content": "instrucción no autorizada"}],
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            with self.assertRaises(ValueError):
                _get_chat_history("user-a", "project-a")

    def test_get_history_rejects_non_string_content(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": [{"role": "assistant", "content": {"unexpected": "object"}}],
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            with self.assertRaises(ValueError):
                _get_chat_history("user-a", "project-a")

    def test_get_history_rejects_total_content_over_40000_characters(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            "messages": [
                {"role": "user", "content": "a" * 20000},
                {"role": "assistant", "content": "b" * 20001},
            ],
            "updated_at": "now",
        }
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch("api.workspace_routes.engine.connect", return_value=context):
            with self.assertRaises(ValueError):
                _get_chat_history("user-a", "project-a")


    async def test_history_route_returns_503_when_storage_is_unavailable(self):
        with (
            patch("api.workspace_routes.run_in_threadpool", side_effect=_run_history_callback),
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes._get_chat_history", side_effect=RuntimeError("database unavailable")),
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_chat_history(project_id="project-a", user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(
            caught.exception.detail,
            "No se pudo recuperar el historial de la conversación",
        )

    async def test_history_route_returns_500_for_corrupt_stored_history(self):
        with (
            patch("api.workspace_routes.run_in_threadpool", side_effect=_run_history_callback),
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes._get_chat_history", side_effect=ValueError("invalid stored data")),
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_chat_history(project_id="project-a", user={"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(
            caught.exception.detail,
            "El historial de chat almacenado no es válido",
        )


def _run_history_callback(func, *args, **kwargs):
    return func(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
