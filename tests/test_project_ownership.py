import unittest
from contextlib import contextmanager
from unittest.mock import patch

from api import projects


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return []


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

    @contextmanager
    def connect(self):
        yield self.connection


class ProjectOwnershipTests(unittest.TestCase):
    def test_project_and_owner_membership_are_created_in_one_transaction(self):
        fake = FakeEngine()
        with patch.object(projects, "engine", fake):
            created = projects.create_owned_project("user-1", "Project Alpha")
        self.assertEqual(created["role"], "owner")
        self.assertEqual(len(fake.connection.calls), 2)
        project_sql, project_params = fake.connection.calls[0]
        membership_sql, membership_params = fake.connection.calls[1]
        self.assertIn("INSERT INTO projects", project_sql)
        self.assertIn("INSERT INTO project_memberships", membership_sql)
        self.assertIn("'owner'", membership_sql)
        self.assertNotIn("role", membership_params)
        self.assertEqual(membership_params["user_id"], "user-1")
        self.assertEqual(membership_params["created_by"], "user-1")
        self.assertEqual(project_params["id"], created["id"])

    def test_project_listing_is_scoped_to_authenticated_user(self):
        fake = FakeEngine()
        with patch.object(projects, "engine", fake):
            projects.list_user_projects("user-2")
        sql, params = fake.connection.calls[0]
        self.assertIn("WHERE m.user_id=:user_id", sql)
        self.assertEqual(params["user_id"], "user-2")


if __name__ == "__main__":
    unittest.main()
