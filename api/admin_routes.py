"""Endpoints administrativos globales de solo lectura."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from api.database import engine
from api.global_admin import (
    ROLE_PERMISSIONS,
    authenticated_admin_user,
    global_roles_for_user,
    require_global_permission,
)

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


@router.get("/audit")
async def list_global_admin_audit(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    _user=Depends(require_global_permission("audit.read")),
):
    """Lista el registro administrativo append-only; nunca devuelve secretos."""
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM global_admin_audit_events")
        ).scalar_one()
        rows = conn.execute(
            text("""
                SELECT id, actor_user_id, target_user_id, action, role, reason, created_at
                FROM global_admin_audit_events
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        ).mappings().all()
    events = [
        {
            "id": str(row["id"]),
            "actor_user_id": row["actor_user_id"],
            "target_user_id": row["target_user_id"],
            "action": row["action"],
            "role": row["role"],
            "reason": row["reason"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {
        "events": events,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(events) < total,
        },
    }


@router.get("/users")
async def list_admin_users(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    _user=Depends(require_global_permission("users.read")),
):
    """Consulta cuentas reales sin exponer hashes, sesiones ni tokens."""
    search = q.strip() if q else None
    where = "WHERE (email ILIKE :pattern OR display_name ILIKE :pattern)" if search else ""
    params = {"limit": limit, "offset": offset}
    if search:
        params["pattern"] = f"%{search}%"
    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT count(*) FROM users {where}"), params
        ).scalar_one()
        rows = conn.execute(
            text(f"""
                SELECT id, email, display_name, status, email_verified_at,
                       created_at, last_login_at
                FROM users {where}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()
    return {
        "users": [
            {
                "id": row["id"],
                "email": row["email"],
                "display_name": row["display_name"],
                "status": row["status"],
                "email_verified_at": row["email_verified_at"],
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
            }
            for row in rows
        ],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(rows) < total,
        },
    }
