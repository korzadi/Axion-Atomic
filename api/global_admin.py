"""Autorización administrativa global separada de los roles de proyecto."""
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import text
from api.auth import COOKIE_NAME, current_user
from api.config import settings
from api.database import engine

ROLE_PERMISSIONS = {
 "platform_admin": ("admin.access.read", "billing.read", "billing.manage", "users.manage", "audit.read"),
 "billing_admin": ("admin.access.read", "billing.read", "billing.manage", "audit.read"),
 "billing_support": ("admin.access.read", "billing.read", "audit.read"),
 "billing_readonly": ("admin.access.read", "billing.read"),
}


def authenticated_admin_user(axion_session: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
 if not settings.auth_enabled:
  raise HTTPException(status_code=503, detail="La autenticación web aún no está habilitada")
 return current_user(axion_session)


def global_roles_for_user(user_id: str) -> tuple[str, ...]:
 with engine.connect() as conn:
  rows = conn.execute(text("""
   SELECT role FROM global_role_assignments
   WHERE user_id=:user_id AND revoked_at IS NULL ORDER BY role
  """), {"user_id": user_id}).scalars().all()
 # Fail closed: una asignación desconocida no debe aparentar acceso administrativo.
 return tuple(role for role in rows if role in ROLE_PERMISSIONS)


def require_global_permission(permission: str):
 if not isinstance(permission, str) or not permission or len(permission) > 100:
  raise ValueError("Permiso global no válido")
 def dependency(user=Depends(authenticated_admin_user)):
  roles = global_roles_for_user(user["id"])
  permissions = {p for role in roles for p in ROLE_PERMISSIONS.get(role, ())}
  if permission not in permissions:
   raise HTTPException(status_code=404, detail="Recurso no encontrado")
  return {**user, "global_roles": roles, "global_permissions": tuple(sorted(permissions))}
 return dependency
