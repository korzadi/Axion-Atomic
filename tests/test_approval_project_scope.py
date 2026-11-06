import unittest
from contextlib import contextmanager
from unittest.mock import patch

from agent import approvals
from api.schemas import ApprovalRequest


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return []

    def first(self):
        return (7,)


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return FakeResult()


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class ProjectApprovalScopeTests(unittest.TestCase):
    def test_pending_list_is_filtered_by_project(self):
        fake = FakeEngine()
        with patch.object(approvals, "engine", fake):
            approvals.list_pending("project-A")
        sql, params = fake.connection.calls[0]
        self.assertIn("project_id=:p", sql)
        self.assertEqual(params["p"], "project-A")

    def test_decision_is_bound_to_approval_and_project(self):
        fake = FakeEngine()
        with patch.object(approvals, "engine", fake):
            approvals.decide_approval(7, "project-A", True, "service-api", "")
        sql, params = fake.connection.calls[0]
        self.assertIn("id=:i AND project_id=:p", sql)
        self.assertEqual(params["i"], 7)
        self.assertEqual(params["p"], "project-A")

    def test_client_cannot_supply_reviewer_identity(self):
        self.assertNotIn("reviewer", ApprovalRequest.model_fields)


if __name__ == "__main__":
    unittest.main()
