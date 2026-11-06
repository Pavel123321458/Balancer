import json
from typing import Annotated, Any, Literal
from zipfile import BadZipFile, ZipFile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.datasets import MAX_UPLOAD, entries, read_response
from backend.db import connection, dump, many, session, transaction
from backend.mart import Mart
from backend.plugins import available_checks, plugin_file

app = FastAPI(title="Balancer")
Limit = Annotated[int, Query(ge=1, le=1000)]
Offset = Annotated[int, Query(ge=0)]
Change = Literal["SAME", "VALUE_CHANGED", "ATTRIBUTE_NEW", "ATTRIBUTE_LOST"]


class RunRequest(BaseModel):
    dataset_id: int = Field(gt=0)
    normalizer: str = "builtin"
    comparator: str = "builtin"
    normalize_params: dict[str, Any] = Field(default_factory=dict)
    compare_params: dict[str, Any] = Field(default_factory=dict)
    checks: dict[str, dict[str, Any]] | None = None


@app.post("/datasets", status_code=201)
def upload_dataset(file: Annotated[UploadFile, File()]):
    if file.size is not None and file.size > MAX_UPLOAD:
        raise HTTPException(413, "ZIP exceeds 64 MiB")
    try:
        with ZipFile(file.file) as archive:
            pairs = entries(archive)
            with connection() as conn, transaction(conn) as cursor:
                cursor.execute("INSERT INTO datasets (name, application_count) VALUES (%s, %s)",
                               ((file.filename or "dataset.zip")[:255], len(pairs)))
                dataset_id = cursor.lastrowid
                many(cursor, "responses", ("dataset_id", "app_id", "before_json", "after_json"), (
                    (dataset_id, app_id, dump(read_response(archive, before)), dump(read_response(archive, after)))
                    for app_id, (before, after) in pairs.items()
                ))
    except (BadZipFile, ValueError, RuntimeError, NotImplementedError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": dataset_id, "applications": len(pairs)}


@app.post("/runs", status_code=201)
def create_run(request: RunRequest):
    settings = request.model_dump(exclude={"dataset_id"})
    if settings["checks"] is None:
        settings["checks"] = {name: {} for name in available_checks()}
    try:
        for name in (request.normalizer, request.comparator):
            if name != "builtin":
                plugin_file(name)
        for name in settings["checks"]:
            plugin_file(name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    with connection() as conn, transaction(conn) as cursor:
        cursor.execute("SELECT id FROM datasets WHERE id = %s", (request.dataset_id,))
        if cursor.fetchone() is None:
            raise HTTPException(404, "Dataset not found")
        cursor.execute("INSERT INTO configurations (settings) VALUES (%s)", (dump(settings),))
        config_id = cursor.lastrowid
        cursor.execute("INSERT INTO runs (dataset_id, configuration_id) VALUES (%s, %s)",
                       (request.dataset_id, config_id))
        run_id = cursor.lastrowid
    return {"id": run_id, "status": "CREATED"}


def run_row(cursor, run_id):
    cursor.execute(
        "SELECT r.*, d.application_count AS total FROM runs r JOIN datasets d ON d.id = r.dataset_id "
        "WHERE r.id = %s", (run_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Run not found")
    return row


def require_completed(cursor, run_id):
    row = run_row(cursor, run_id)
    if row["status"] != "SUCCEEDED":
        raise HTTPException(409, f"Run status: {row['status']}")


@app.post("/runs/{run_id}/start", status_code=202)
def start_run(run_id: int):
    with connection() as conn, transaction(conn) as cursor:
        cursor.execute(
            "UPDATE runs SET status = 'QUEUED', stage = 'queued' WHERE id = %s AND status = 'CREATED'",
            (run_id,),
        )
        if not cursor.rowcount:
            row = run_row(cursor, run_id)
            if row["status"] == "FAILED":
                raise HTTPException(409, "Create a new run to retry a failed run")
            return {"id": run_id, "status": row["status"]}
        cursor.execute("INSERT INTO run_logs (run_id, stage, message) VALUES (%s, 'queued', 'Run queued')", (run_id,))
    return {"id": run_id, "status": "QUEUED"}


@app.get("/runs/{run_id}")
def progress(run_id: int):
    with session() as cursor:
        row = run_row(cursor, run_id)
        cursor.execute("SELECT * FROM run_summaries WHERE run_id = %s", (run_id,))
        row["summary"] = cursor.fetchone() if row["status"] == "SUCCEEDED" else None
        return row


@app.get("/runs/{run_id}/results")
def results(run_id: int, app_id: str | None = None, path: str | None = None,
            array_key: str | None = None, change_type: Change | None = None,
            only_differences: bool = False, limit: Limit = 100, offset: Offset = 0):
    with session() as cursor:
        require_completed(cursor, run_id)
        filters = {name: value for name, value in (
            ("app_ids", app_id), ("path", path), ("array_key", array_key), ("change_type", change_type),
        ) if value is not None}
        if only_differences:
            filters["diff_flag"] = 1
        rows = Mart(cursor, run_id).page(limit, offset, **filters)
        return {"offset": offset, "rows": rows}


@app.get("/runs/{run_id}/checks")
def checks(run_id: int, limit: Limit = 100, offset: Offset = 0):
    with session() as cursor:
        require_completed(cursor, run_id)
        cursor.execute(
            "SELECT check_id, result FROM check_results WHERE run_id = %s ORDER BY id LIMIT %s OFFSET %s",
            (run_id, limit, offset),
        )
        return [{"check_id": row["check_id"], **json.loads(row["result"])} for row in cursor.fetchall()]


@app.get("/runs/{run_id}/facts")
def facts(run_id: int, limit: Limit = 100, offset: Offset = 0):
    with session() as cursor:
        require_completed(cursor, run_id)
        cursor.execute(
            "SELECT PREFIX, CLASS, SUFFIX, ARRAY_KEY, `KEY`, VALUE_ADJUSTED, DIFF_FLAG, SOURCE, CNT "
            "FROM pivot_facts WHERE run_id = %s ORDER BY id LIMIT %s OFFSET %s",
            (run_id, limit, offset),
        )
        return cursor.fetchall()


@app.get("/runs/{run_id}/logs")
def logs(run_id: int):
    with session() as cursor:
        run_row(cursor, run_id)
        cursor.execute(
            "SELECT stage, message, created_at FROM run_logs WHERE run_id = %s ORDER BY id", (run_id,)
        )
        return cursor.fetchall()

