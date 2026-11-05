import json
from sqlalchemy import create_engine, text
from api.config import settings

engine = create_engine(settings.database_url, future=True)

def create_approval(project_id, goal, plan):
    with engine.begin() as conn:
        row = conn.execute(text("INSERT INTO approvals(project_id,goal,plan_json,status) "
            "VALUES (:p,:g,:j,'pending') RETURNING id"),
            {"p":project_id,"g":goal,"j":json.dumps(plan)}).first()
        return int(row[0])

def list_pending():
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id,project_id,goal,plan_json,created_at FROM approvals "
                                 "WHERE status='pending' ORDER BY created_at")).mappings().all()
        return [dict(x) for x in rows]

def decide_approval(approval_id, approved, reviewer, note):
    status = "approved" if approved else "rejected"
    with engine.begin() as conn:
        row = conn.execute(text("UPDATE approvals SET status=:s,reviewer=:r,reviewer_note=:n,"
            "decided_at=now() WHERE id=:i AND status='pending' RETURNING id"),
            {"s":status,"r":reviewer,"n":note,"i":approval_id}).first()
        if not row:
            raise ValueError("Approval not found or already decided")
    # Approval records intent only. It does not execute code or commands.
    return {"id":approval_id,"status":status,"execution":"not_implemented"}
