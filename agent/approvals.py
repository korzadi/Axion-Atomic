import json
from sqlalchemy import text
from api.database import engine


def create_approval(project_id, goal, plan):
    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO approvals(project_id,goal,plan_json,status) "
                 "VALUES (:p,:g,:j,'pending') RETURNING id"),
            {"p": project_id, "g": goal, "j": json.dumps(plan)},
        ).first()
        return int(row[0])


def list_pending(project_id):
    if not project_id:
        raise ValueError("project_id is required")
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id,project_id,goal,plan_json,created_at FROM approvals "
                 "WHERE project_id=:p AND status='pending' ORDER BY created_at"),
            {"p": project_id},
        ).mappings().all()
        return [dict(x) for x in rows]


def decide_approval(approval_id, project_id, approved, reviewer, note):
    if not project_id:
        raise ValueError("project_id is required")
    status = "approved" if approved else "rejected"
    with engine.begin() as conn:
        row = conn.execute(
            text("UPDATE approvals SET status=:s,reviewer=:r,reviewer_note=:n,"
                 "decided_at=now() WHERE id=:i AND project_id=:p AND status='pending' RETURNING id"),
            {"s": status, "r": reviewer, "n": note, "i": approval_id, "p": project_id},
        ).first()
        if not row:
            raise ValueError("Approval not found or already decided")
    # Approval records intent only. It does not execute code or commands.
    return {"id": approval_id, "project_id": project_id, "status": status, "execution": "not_implemented"}
