"""Endpoints administrativos globales; las mutaciones son explícitas y auditadas."""
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from api.auth import CSRF_COOKIE, require_csrf
from api.billing_recovery import recover_completed_billing_executions
from api.billing_reservations import (
    IdempotencyConflict,
    ReservationNotFound,
    ReservationStateError,
    reconcile_confirmed_no_execution,
)
from api.billing_result_crypto import (
    AesGcmResultCipher,
    EnvironmentResultKeyProvider,
    ResultEncryptionError,
)
from api.database import engine
from api.global_admin import (
    ROLE_PERMISSIONS,
    authenticated_admin_user,
    global_roles_for_user,
    require_global_permission,
)

router = APIRouter(prefix="/admin", tags=["administration"])


async def _admin_csrf(
    user=Depends(authenticated_admin_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    require_csrf(user, csrf_cookie, csrf_header)
    return user


@router.get("/access/me")
async def my_admin_access(user=Depends(authenticated_admin_user)):
    roles = global_roles_for_user(user["id"])
    permissions = sorted({p for role in roles for p in ROLE_PERMISSIONS.get(role, ())})
    return {
        "user_id": user["id"],
        "roles": list(roles),
        "permissions": permissions,
        "administration_enabled": bool(roles),
        "mutations_enabled": "billing.manage" in permissions,
        "available_mutations": (
            [
                "billing.executions.recover",
                "billing.reservations.reconcile_no_execution",
            ]
            if "billing.manage" in permissions
            else []
        ),
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


@router.get("/billing/overview")
async def admin_billing_overview(
    _user=Depends(require_global_permission("billing.read")),
):
    """Resumen agregado de reservas, ledger y ejecuciones persistidos."""
    with engine.connect() as conn:
        reservations = conn.execute(text("""
            SELECT state, count(*) AS count, coalesce(sum(requested_credits), 0) AS credits
            FROM billing_usage_reservations
            GROUP BY state ORDER BY state
        """)).mappings().all()
        ledger = conn.execute(text("""
            SELECT event_type, count(*) AS count,
                   coalesce(sum(available_delta), 0) AS available_delta,
                   coalesce(sum(reserved_delta), 0) AS reserved_delta,
                   coalesce(sum(consumed_delta), 0) AS consumed_delta
            FROM billing_credit_ledger
            GROUP BY event_type ORDER BY event_type
        """)).mappings().all()
        executions = conn.execute(text("""
            SELECT state, count(*) AS count,
                   count(*) FILTER (WHERE recovery_requires_review) AS requires_review,
                   count(*) FILTER (WHERE recovery_next_attempt_at IS NOT NULL
                                     AND recovery_next_attempt_at <= now()) AS recovery_due
            FROM billing_inference_executions
            GROUP BY state ORDER BY state
        """)).mappings().all()
    return {
        "reservations": [dict(row) for row in reservations],
        "ledger": [dict(row) for row in ledger],
        "executions": [dict(row) for row in executions],
    }

@router.get("/billing/executions")
async def admin_billing_executions(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    _user=Depends(require_global_permission("billing.read")),
):
    """Detalle paginado de ejecuciones persistidas; omite ciphertext y secretos."""
    with engine.connect() as conn:
        total = conn.execute(text("""
            SELECT count(*) FROM billing_inference_executions
        """)).scalar_one()
        rows = conn.execute(text("""
            SELECT e.id, e.user_id, e.reservation_id, e.state,
                   e.recovery_attempts, e.recovery_next_attempt_at,
                   e.recovery_last_attempt_at, e.recovery_last_error_code,
                   e.recovery_requires_review, e.recovery_settled_at,
                   e.created_at, e.updated_at, e.completed_at,
                   r.state AS reservation_state, r.requested_credits
            FROM billing_inference_executions e
            JOIN billing_usage_reservations r ON r.id = e.reservation_id
            ORDER BY e.updated_at DESC, e.id DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset}).mappings().all()
    return {
        "executions": [
            {
                "id": str(row["id"]),
                "user_id": row["user_id"],
                "reservation_id": str(row["reservation_id"]),
                "state": row["state"],
                "reservation_state": row["reservation_state"],
                "requested_credits": row["requested_credits"],
                "recovery_attempts": row["recovery_attempts"],
                "recovery_next_attempt_at": row["recovery_next_attempt_at"],
                "recovery_last_attempt_at": row["recovery_last_attempt_at"],
                "recovery_last_error_code": row["recovery_last_error_code"],
                "recovery_requires_review": row["recovery_requires_review"],
                "recovery_settled_at": row["recovery_settled_at"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row["completed_at"],
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


@router.post("/billing/executions/recover")
async def admin_recover_billing_executions(
    limit: int = Query(default=25, ge=1, le=100),
    reservation_id: str | None = Query(default=None),
    reason: str = Query(
        default="Recuperación manual de liquidaciones completadas",
        min_length=8,
        max_length=500,
    ),
    user=Depends(require_global_permission("billing.manage")),
    _csrf_user=Depends(_admin_csrf),
):
    """Reintenta liquidar resultados cifrados ya completados; nunca repite inferencia."""
    normalized = None
    if reservation_id is not None:
        try:
            normalized = str(uuid.UUID(reservation_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="reservation_id inválido") from exc
    try:
        provider = EnvironmentResultKeyProvider()
        provider.active_key()
        cipher = AesGcmResultCipher(provider)
    except ResultEncryptionError as exc:
        raise HTTPException(
            status_code=503,
            detail="La clave de cifrado de resultados no está disponible",
        ) from exc

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO global_admin_audit_events
                        (id, actor_user_id, target_user_id, action, role, reason)
                    VALUES
                        (CAST(:id AS UUID), :actor_user_id, NULL,
                         'billing.executions.recover', NULL, :reason)
                """),
                {"id": str(uuid.uuid4()), "actor_user_id": user["id"], "reason": reason},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo registrar la recuperación en auditoría",
        ) from exc

    try:
        batch = await run_in_threadpool(
            recover_completed_billing_executions,
            engine=engine,
            cipher=cipher,
            limit=limit,
            reservation_id=normalized,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="La recuperación no pudo completarse",
        ) from exc
    return {
        "examined": batch.examined,
        "settled": batch.settled,
        "review": batch.review,
        "failed": batch.failed,
        "skipped": batch.skipped,
        "items": [
            {
                "reservation_id": item.reservation_id,
                "state": item.state,
                "charged_credits": item.charged_credits,
                "detail": item.detail,
            }
            for item in batch.items
        ],
    }


class ReconcileNoExecutionRequest(BaseModel):
    reservation_id: str = Field(min_length=36, max_length=36)
    reason: str = Field(min_length=10, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=200)


def _load_reservation_owner(reservation_id: str) -> tuple[str, str] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, state FROM billing_usage_reservations
                WHERE id=CAST(:id AS UUID)
            """),
            {"id": reservation_id},
        ).mappings().first()
    return (row["user_id"], row["state"]) if row is not None else None


@router.post("/billing/reservations/reconcile-no-execution")
async def admin_reconcile_no_execution(
    payload: ReconcileNoExecutionRequest,
    user=Depends(require_global_permission("billing.manage")),
    _csrf_user=Depends(_admin_csrf),
):
    """Libera una reserva unknown/review solo con confirmación humana auditada."""
    try:
        normalized = str(uuid.UUID(payload.reservation_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="reservation_id inválido") from exc
    owner = await run_in_threadpool(_load_reservation_owner, normalized)
    if owner is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    target_user_id, state = owner
    if state not in ("unknown", "review"):
        raise HTTPException(
            status_code=409,
            detail="Solo se concilian reservas en estado unknown o review",
        )
    reason = payload.reason.strip()
    idempotency_key = payload.idempotency_key.strip()
    if not idempotency_key or any(
        ord(char) < 0x21 or ord(char) > 0x7E for char in idempotency_key
    ):
        raise HTTPException(
            status_code=400,
            detail="La clave idempotente debe usar ASCII imprimible sin espacios",
        )
    try:
        result = await run_in_threadpool(
            reconcile_confirmed_no_execution,
            engine=engine,
            user_id=target_user_id,
            reservation_id=normalized,
            actor_user_id=user["id"],
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ReservationNotFound as exc:
        raise HTTPException(status_code=404, detail="Reserva no encontrada") from exc
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="La clave de conciliación ya pertenece a otra decisión",
        ) from exc
    except ReservationStateError as exc:
        raise HTTPException(
            status_code=409,
            detail="La reserva no está en un estado conciliable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datos de conciliación inválidos") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="La conciliación no pudo completarse",
        ) from exc

    audit_id = str(uuid.uuid5(
        uuid.UUID("6f0a1f9e-8f6a-4f0e-9c63-6a7f4a0d2b51"),
        f"reconcile-no-execution:{idempotency_key}",
    ))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO global_admin_audit_events
                        (id, actor_user_id, target_user_id, action, role, reason)
                    VALUES
                        (CAST(:id AS UUID), :actor_user_id, :target_user_id,
                         'billing.reservation.reconcile_no_execution', NULL, :reason)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": audit_id, "actor_user_id": user["id"],
                    "target_user_id": target_user_id, "reason": reason,
                },
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "La conciliación se aplicó, pero no se pudo registrar en auditoría global; "
                "reintente con la misma clave idempotente"
            ),
        ) from exc
    return {
        "reservation_id": result.reservation_id,
        "state": result.state,
        "idempotent": result.idempotent,
        "audited": True,
    }
