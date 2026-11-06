"""Endpoint administrativo propio de solo lectura."""
from fastapi import APIRouter, Depends
from api.global_admin import ROLE_PERMISSIONS, authenticated_admin_user, global_roles_for_user

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get("/access/me")
async def my_admin_access(user=Depends(authenticated_admin_user)):
 roles = global_roles_for_user(user["id"])
 permissions = sorted({p for role in roles for p in ROLE_PERMISSIONS.get(role, ())})
 return {
  "user_id": user["id"],
  "roles": list(roles),
  "permissions": permissions,
  "administration_enabled": bool(roles),
  "mutations_enabled": False,
 }
