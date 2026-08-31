"""Run history for backend/app/jobs.py's job registry."""

from __future__ import annotations

from typing import Any

from app.storage.db.connection import _connect


def create_job_run(id: str, job_id: str, started_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO job_runs (id, job_id, status, started_at) VALUES (?, ?, 'running', ?)",
            (id, job_id, started_at),
        )


def finish_job_run(id: str, status: str, finished_at: str, error: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE job_runs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
            (status, finished_at, error, id),
        )


def list_job_runs(job_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        if job_id is None:
            rows = conn.execute(
                "SELECT id, job_id, status, started_at, finished_at, error FROM job_runs "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, job_id, status, started_at, finished_at, error FROM job_runs "
                "WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
    return [dict(row) for row in rows]
