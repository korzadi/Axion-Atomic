import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from api.global_admin import ROLE_PERMISSIONS, global_roles_for_user, require_global_permission
from api.main import app


class GlobalAdminRbacTests(unittest.TestCase):
 def test_global_admin_authentication_fails_closed_when_auth_disabled(self):
  from api.global_admin import authenticated_admin_user
  with patch("api.global_admin.settings.auth_enabled", False), patch("api.global_admin.current_user") as current:
   with self.assertRaises(HTTPException) as caught:
    authenticated_admin_user("session-token")
  self.assertEqual(caught.exception.status_code, 503)
  current.assert_not_called()

 def test_unknown_global_role_grants_no_permissions(self):
  unknown_permissions = {p for role in ("unexpected_role",) for p in ROLE_PERMISSIONS.get(role, ())}
  self.assertEqual(unknown_permissions, set())

 def test_project_roles_do_not_grant_global_permissions(self):
  self.assertNotIn("billing.manage", ROLE_PERMISSIONS.get("owner", ()))
  self.assertNotIn("billing.manage", ROLE_PERMISSIONS.get("admin", ()))

 def test_billing_support_cannot_manage_billing(self):
  self.assertIn("billing.read", ROLE_PERMISSIONS["billing_support"])
  self.assertNotIn("billing.manage", ROLE_PERMISSIONS["billing_support"])

 def test_readonly_role_has_no_mutations(self):
  self.assertTrue(all(p.endswith(".read") or p == "admin.access.read"
                      for p in ROLE_PERMISSIONS["billing_readonly"]))

 def test_loads_only_active_global_assignments(self):
  conn=MagicMock()
  conn.execute.return_value.scalars.return_value.all.return_value=["billing_readonly"]
  ctx=MagicMock(); ctx.__enter__.return_value=conn
  with patch("api.global_admin.engine.connect", return_value=ctx):
   self.assertEqual(global_roles_for_user("user-1"), ("billing_readonly",))
  self.assertIn("revoked_at IS NULL", str(conn.execute.call_args.args[0]))

 def test_unknown_database_roles_are_ignored(self):
  conn=MagicMock()
  conn.execute.return_value.scalars.return_value.all.return_value=["unexpected_role", "billing_readonly"]
  ctx=MagicMock(); ctx.__enter__.return_value=conn
  with patch("api.global_admin.engine.connect", return_value=ctx):
   self.assertEqual(global_roles_for_user("user-1"), ("billing_readonly",))

 def test_denies_unassigned_user(self):
  dep=require_global_permission("billing.manage")
  with patch("api.global_admin.global_roles_for_user", return_value=()):
   with self.assertRaises(HTTPException) as caught: dep({"id":"ordinary"})
  self.assertEqual(caught.exception.status_code,404)

 def test_allows_explicit_billing_admin(self):
  dep=require_global_permission("billing.manage")
  with patch("api.global_admin.global_roles_for_user", return_value=("billing_admin",)):
   result=dep({"id":"operator"})
  self.assertIn("billing.manage",result["global_permissions"])

 def test_read_only_access_endpoint(self):
  from api.global_admin import authenticated_admin_user
  client=TestClient(app)
  app.dependency_overrides[authenticated_admin_user]=lambda:{"id":"ordinary"}
  try:
   with patch("api.admin_routes.global_roles_for_user",return_value=()):
    response=client.get("/admin/access/me")
   self.assertEqual(response.status_code,200)
   self.assertFalse(response.json()["administration_enabled"])
   self.assertFalse(response.json()["mutations_enabled"])
  finally: app.dependency_overrides.clear()


if __name__ == "__main__": unittest.main()
