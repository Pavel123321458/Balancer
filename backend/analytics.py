"""Report queries over precomputed facts and their supporting attributes."""
import json
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from backend.db import session

router = APIRouter()
Dimension = Literal["PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "VALUE_ADJUSTED", "DIFF_FLAG", "SOURCE"]
Split = Literal["none", "SOURCE", "DIFF_FLAG"]
Scope = Literal["all", "differences", "decisions"]
DIMENSIONS = {
    "PREFIX": "n.PREFIX", "CLASS": "n.CLASS", "SUFFIX": "n.SUFFIX",
    "ARRAY_KEY": "n.ARRAY_KEY", "KEY": "n.`KEY`", "VALUE_ADJUSTED": "n.ADJUSTED_VALUE",
    "DIFF_FLAG": "c.DIFF_FLAG", "SOURCE": "n.SOURCE",
}
Page = Annotated[int, Query(ge=0)]
FactLimit = Annotated[int, Query(ge=1, le=100)]


def completed(cursor, run_id):
    cursor.execute("SELECT status FROM runs WHERE id = %s", (run_id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Анализ не найден")
    if row["status"] != "SUCCEEDED":
        raise HTTPException(409, "Анализ ещё не завершён")


def fact_filters(raw):
    try:
        filters = json.loads(raw)
        if not isinstance(filters, dict):
            raise ValueError
        for name, value in filters.items():
            if name not in DIMENSIONS:
                raise ValueError
            if name == "DIFF_FLAG":
                if type(value) is not int or value not in (0, 1):
                    raise ValueError
            elif not isinstance(value, str):
                raise ValueError
            elif name == "SOURCE" and value not in ("BEFORE", "AFTER"):
                raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "Некорректные фильтры сводной") from exc
    return filters


def matching_attributes(filters, alias):
    conditions = "".join(f" AND {DIMENSIONS[name]} = %s" for name in filters)
    return (
        "EXISTS (SELECT 1 FROM normalized n JOIN comparisons c USING (run_id, APP_ID, PATH, ARRAY_KEY)"
        f" WHERE n.run_id = {alias}.run_id AND n.APP_ID = {alias}.APP_ID{conditions}"
    )


@router.get("/runs/{run_id}/top-attributes")
def top_attributes(run_id: int, limit: FactLimit = 10):
    with session() as cursor:
        completed(cursor, run_id)
        cursor.execute(
            """SELECT PATH AS path, COUNT(DISTINCT APP_ID) AS applications
               FROM comparisons WHERE run_id = %s AND DIFF_FLAG = 1
               GROUP BY PATH ORDER BY applications DESC, PATH LIMIT %s""", (run_id, limit),
        )
        return cursor.fetchall()


@router.get("/runs/{run_id}/pivot")
def pivot(run_id: int, group: Annotated[list[Dimension] | None, Query()] = None, split: Split = "SOURCE",
          filters: str = "{}", offset: Page = 0, limit: FactLimit = 30):
    groups = group or ["CLASS", "KEY"]
    if len(groups) > 2 or len(set(groups)) != len(groups) or split in groups:
        raise HTTPException(422, "Выберите до двух разных группировок, отличных от колонок")
    selected = fact_filters(filters)
    group_sql = ", ".join(f"`{name}`" for name in groups)
    conditions = "".join(f" AND `{name}` = %s" for name in selected)
    cells = {
        "none": "",
        "SOURCE": ", SUM(IF(SOURCE = 'BEFORE', CNT, 0)) AS `BEFORE`, SUM(IF(SOURCE = 'AFTER', CNT, 0)) AS `AFTER`",
        "DIFF_FLAG": ", SUM(IF(DIFF_FLAG = 0, CNT, 0)) AS same_count, SUM(IF(DIFF_FLAG = 1, CNT, 0)) AS diff_count",
    }
    with session() as cursor:
        completed(cursor, run_id)
        cursor.execute(
            f"""SELECT {group_sql}, SUM(CNT) AS total{cells[split]}
                FROM pivot_facts WHERE run_id = %s{conditions}
                GROUP BY {group_sql} ORDER BY total DESC, {group_sql} LIMIT %s OFFSET %s""",
            (run_id, *selected.values(), limit + 1, offset),
        )
        rows = cursor.fetchall()
    return {"rows": rows[:limit], "has_more": len(rows) > limit}


@router.get("/runs/{run_id}/applications")
def applications(run_id: int, scope: Scope = "all", path: str | None = None,
                 app_id: Annotated[list[str] | None, Query()] = None, filters: str = "{}",
                 offset: Page = 0, limit: FactLimit = 30):
    selected = fact_filters(filters)
    where, params = ["a.run_id = %s"], [run_id]
    if scope == "differences":
        where.append("a.DIFF_FLAG = 1")
    if scope == "decisions":
        where.append("a.DECISION_CHANGED = 1")
    if app_id:
        if len(app_id) > 500:
            raise HTTPException(422, "Слишком много идентификаторов заявок")
        where.append("a.APP_ID IN (" + ", ".join(["%s"] * len(app_id)) + ")")
        params.extend(app_id)
    if path is not None:
        where.append("""EXISTS (SELECT 1 FROM comparisons p
                     WHERE p.run_id = a.run_id AND p.APP_ID = a.APP_ID AND p.PATH = %s AND p.DIFF_FLAG = 1)""")
        params.append(path)
    if selected:
        conditions = "".join(f" AND {DIMENSIONS[name]} = %s" for name in selected)
        join = "USING (run_id, APP_ID, PATH, ARRAY_KEY) WHERE c.run_id = %s" + conditions
        if selected.get("DIFF_FLAG") == 1:
            # Start with the small changed-row index and materialize IDs once.
            matches = ("SELECT APP_ID FROM (SELECT DISTINCT c.APP_ID FROM comparisons c "
                       "STRAIGHT_JOIN normalized n " + join + ") matched")
        else:
            matches = "SELECT n.APP_ID FROM comparisons c JOIN normalized n " + join
        where.append(f"a.APP_ID IN ({matches})")
        params.extend((run_id, *selected.values()))
    with session() as cursor:
        completed(cursor, run_id)
        predicate = " AND ".join(where)
        cursor.execute(
            f"""SELECT a.DIFF_FLAG, a.segment, COUNT(*) OVER () AS total FROM run_apps a WHERE {predicate}
                ORDER BY a.APP_ID LIMIT %s OFFSET %s""",
            (*params, limit, offset),
        )
        page = cursor.fetchall()
        total = page[0]["total"] if page else 0
        if not page and offset:
            cursor.execute(f"SELECT COUNT(*) AS total FROM run_apps a WHERE {predicate}", params)
            total = cursor.fetchone()["total"]
        rows = [{**json.loads(row["segment"]), "DIFF_FLAG": row["DIFF_FLAG"]} for row in page]
    return {"rows": rows, "total": total}


@router.get("/runs/{run_id}/applications/{app_id}")
def application(run_id: int, app_id: str):
    with session() as cursor:
        completed(cursor, run_id)
        cursor.execute("SELECT DIFF_FLAG, segment FROM run_apps WHERE run_id = %s AND APP_ID = %s", (run_id, app_id))
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Заявка не найдена")
    return {**json.loads(row["segment"]), "DIFF_FLAG": row["DIFF_FLAG"]}

