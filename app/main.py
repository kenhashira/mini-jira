"""Mini-Jira: a small Jira-like issue tracker API built with FastAPI + SQLite."""
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .db import get_conn, init_db
from .schemas import (
    ALLOWED_TRANSITIONS,
    CommentCreate,
    IssueCreate,
    IssueUpdate,
    ProjectCreate,
    Transition,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Mini-Jira", version="1.0.0", lifespan=lifespan)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def issue_to_dict(row: sqlite3.Row, project_key: str) -> dict:
    return {
        "key": f"{project_key}-{row['number']}",
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "assignee": row["assignee"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def parse_key(issue_key: str) -> tuple[str, int]:
    """'PROJ-12' -> ('PROJ', 12). Bad format -> 404, like Jira."""
    try:
        project_key, number = issue_key.rsplit("-", 1)
        return project_key, int(number)
    except ValueError:
        raise HTTPException(status_code=404, detail="Issue not found")


def fetch_issue(conn: sqlite3.Connection, issue_key: str) -> sqlite3.Row:
    project_key, number = parse_key(issue_key)
    row = conn.execute(
        """SELECT i.* FROM issues i JOIN projects p ON p.id = i.project_id
           WHERE p.key = ? AND i.number = ?""",
        (project_key, number),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return row


# ---------- Projects ----------
@app.post("/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO projects (key, name) VALUES (?, ?)", (body.key, body.name)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Project key already exists")
    finally:
        conn.close()
    return {"key": body.key, "name": body.name}


@app.get("/projects")
def list_projects() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT key, name FROM projects ORDER BY key").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Issues ----------
@app.post("/projects/{project_key}/issues", status_code=201)
def create_issue(project_key: str, body: IssueCreate) -> dict:
    conn = get_conn()
    try:
        project = conn.execute(
            "SELECT * FROM projects WHERE key = ?", (project_key,)
        ).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        number = project["issue_counter"] + 1
        ts = now()
        conn.execute(
            "UPDATE projects SET issue_counter = ? WHERE id = ?",
            (number, project["id"]),
        )
        conn.execute(
            """INSERT INTO issues
               (project_id, number, title, description, priority, assignee,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project["id"], number, body.title, body.description,
             body.priority, body.assignee, ts, ts),
        )
        conn.commit()
        row = fetch_issue(conn, f"{project_key}-{number}")
        return issue_to_dict(row, project_key)
    finally:
        conn.close()


@app.get("/projects/{project_key}/issues")
def list_issues(
    project_key: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    conn = get_conn()
    try:
        project = conn.execute(
            "SELECT * FROM projects WHERE key = ?", (project_key,)
        ).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        where, params = ["project_id = ?"], [project["id"]]
        if status:
            where.append("status = ?")
            params.append(status)
        if assignee:
            where.append("assignee = ?")
            params.append(assignee)
        clause = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) FROM issues WHERE {clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM issues WHERE {clause} ORDER BY number LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "issues": [issue_to_dict(r, project_key) for r in rows],
        }
    finally:
        conn.close()


@app.get("/issues/{issue_key}")
def get_issue(issue_key: str) -> dict:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        return issue_to_dict(row, parse_key(issue_key)[0])
    finally:
        conn.close()


@app.patch("/issues/{issue_key}")
def update_issue(issue_key: str, body: IssueUpdate) -> dict:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        changes = body.model_dump(exclude_unset=True)
        if changes:
            sets = ", ".join(f"{col} = ?" for col in changes)
            conn.execute(
                f"UPDATE issues SET {sets}, updated_at = ? WHERE id = ?",
                [*changes.values(), now(), row["id"]],
            )
            conn.commit()
        return issue_to_dict(fetch_issue(conn, issue_key), parse_key(issue_key)[0])
    finally:
        conn.close()


@app.post("/issues/{issue_key}/transitions")
def transition_issue(issue_key: str, body: Transition) -> dict:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        if body.status not in ALLOWED_TRANSITIONS[row["status"]]:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot move from '{row['status']}' to '{body.status}'",
            )
        conn.execute(
            "UPDATE issues SET status = ?, updated_at = ? WHERE id = ?",
            (body.status, now(), row["id"]),
        )
        conn.commit()
        return issue_to_dict(fetch_issue(conn, issue_key), parse_key(issue_key)[0])
    finally:
        conn.close()


@app.delete("/issues/{issue_key}", status_code=204)
def delete_issue(issue_key: str) -> None:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        conn.execute("DELETE FROM issues WHERE id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()


# ---------- Comments ----------
@app.post("/issues/{issue_key}/comments", status_code=201)
def add_comment(issue_key: str, body: CommentCreate) -> dict:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        ts = now()
        cur = conn.execute(
            "INSERT INTO comments (issue_id, author, body, created_at) VALUES (?,?,?,?)",
            (row["id"], body.author, body.body, ts),
        )
        conn.commit()
        return {"id": cur.lastrowid, "author": body.author,
                "body": body.body, "created_at": ts}
    finally:
        conn.close()


@app.get("/issues/{issue_key}/comments")
def list_comments(issue_key: str) -> list[dict]:
    conn = get_conn()
    try:
        row = fetch_issue(conn, issue_key)
        rows = conn.execute(
            "SELECT id, author, body, created_at FROM comments "
            "WHERE issue_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
