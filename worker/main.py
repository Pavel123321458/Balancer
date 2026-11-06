import json
import logging
import time

import pymysql

from backend.db import connection, dump, many, transaction
from backend.mart import COLUMNS, Mart
from backend.plugins import load

LOG = logging.getLogger("worker")
BATCH_SIZE = 40
NORMALIZED = ("APP_ID", "SOURCE", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY",
              "PATH", "VALUE", "ADJUSTED_VALUE")


def stage(cursor, run_id, name, message):
    cursor.execute("UPDATE runs SET stage = %s WHERE id = %s", (name, run_id))
    cursor.execute("INSERT INTO run_logs (run_id, stage, message) VALUES (%s, %s, %s)", (run_id, name, message))


def claim(conn):
    with transaction(conn) as cursor:
        cursor.execute("SELECT id FROM runs WHERE status = 'QUEUED' ORDER BY id LIMIT 1 FOR UPDATE")
        row = cursor.fetchone()
        if row is None:
            return None
        run_id = row["id"]
        cursor.execute("DELETE FROM run_apps WHERE run_id = %s", (run_id,))
        cursor.execute("UPDATE runs SET status = 'RUNNING', processed = 0 WHERE id = %s", (run_id,))
        stage(cursor, run_id, "processing", "Reading dataset and comparing responses")
        return run_id


def store_batch(conn, run_id, batch, normalizer, comparator, settings):
    norm_rows, comparison_rows, apps = [], [], []
    for item in batch:
        app_id = item["app_id"]
        try:
            before = json.loads(item["before_json"])
            after = json.loads(item["after_json"])
            params = settings["normalize_params"]
            left = list(normalizer.normalize(app_id, "BEFORE", before, params))
            right = list(normalizer.normalize(app_id, "AFTER", after, params))
            diffs = list(comparator.compare(left, right, settings["compare_params"]))
            segment = normalizer.segments(app_id, before, after, params)
            apps.append((run_id, app_id, any(row["DIFF_FLAG"] for row in diffs),
                         segment["DECISION_CHANGED"], dump(segment)))
            norm_rows.extend(left)
            norm_rows.extend(right)
            comparison_rows.extend(diffs)
        except Exception as exc:
            raise ValueError(f"{app_id}: {exc}") from exc
    with transaction(conn) as cursor:
        many(cursor, "run_apps", ("run_id", "APP_ID", "DIFF_FLAG", "DECISION_CHANGED", "segment"), apps)
        for table, columns, rows in (("normalized", NORMALIZED, norm_rows),
                                      ("comparisons", COLUMNS, comparison_rows)):
            many(cursor, table, ("run_id", *columns),
                 ((run_id, *(row[col] for col in columns)) for row in rows))
        cursor.execute("UPDATE runs SET processed = processed + %s WHERE id = %s", (len(batch), run_id))


def finish(conn, run_id, checks):
    with transaction(conn) as cursor:
        stage(cursor, run_id, "checks", f"Checks: {', '.join(checks) or 'none'}")

    with conn.cursor() as cursor:
        mart = Mart(cursor, run_id)
        report = []
        for name, overrides in checks.items():
            check = load(name, "check").CHECK
            params = {**check["params"], **overrides}
            report.extend((run_id, check["id"], dump(row)) for row in check["entrypoint"](mart, params))

    with transaction(conn) as cursor:
        stage(cursor, run_id, "aggregating", "Building counts and application summary")
    with transaction(conn) as cursor:
        many(cursor, "check_results", ("run_id", "check_id", "result"), report)
        cursor.execute(
            """INSERT INTO pivot_facts
                (run_id, PREFIX, CLASS, SUFFIX, ARRAY_KEY, `KEY`, VALUE_ADJUSTED, DIFF_FLAG, SOURCE, CNT)
               SELECT n.run_id, n.PREFIX, n.CLASS, n.SUFFIX, n.ARRAY_KEY, n.`KEY`,
                      n.ADJUSTED_VALUE, c.DIFF_FLAG, n.SOURCE, COUNT(DISTINCT n.APP_ID)
               FROM normalized n JOIN comparisons c USING (run_id, APP_ID, PATH, ARRAY_KEY)
               WHERE n.run_id = %s
               GROUP BY n.run_id, n.PREFIX, n.CLASS, n.SUFFIX, n.ARRAY_KEY, n.`KEY`,
                        n.ADJUSTED_VALUE, c.DIFF_FLAG, n.SOURCE""", (run_id,),
        )
        cursor.execute(
            """INSERT INTO run_summaries
               SELECT %s, COUNT(*), COALESCE(SUM(DIFF_FLAG), 0), COALESCE(SUM(DECISION_CHANGED), 0),
                      (SELECT COUNT(*) FROM comparisons WHERE run_id = %s)
               FROM run_apps WHERE run_id = %s""", (run_id, run_id, run_id),
        )
        cursor.execute("UPDATE runs SET status = 'SUCCEEDED' WHERE id = %s", (run_id,))
        stage(cursor, run_id, "done", "Run completed")


def process(conn, run_id):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT r.dataset_id, c.settings FROM runs r JOIN configurations c ON c.id = r.configuration_id "
            "WHERE r.id = %s", (run_id,),
        )
        run = cursor.fetchone()
    settings = json.loads(run["settings"])
    normalizer = load(settings["normalizer"], "normalize")
    comparator = load(settings["comparator"], "compare")
    with transaction(conn) as cursor:
        stage(cursor, run_id, "processing", f"Normalizer: {settings['normalizer']}; comparator: {settings['comparator']}")
    last_id = ""
    while True:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT app_id, before_json, after_json FROM responses WHERE dataset_id = %s AND app_id > %s "
                "ORDER BY app_id LIMIT %s", (run["dataset_id"], last_id, BATCH_SIZE),
            )
            batch = cursor.fetchall()
        if not batch:
            break
        store_batch(conn, run_id, batch, normalizer, comparator, settings)
        last_id = batch[-1]["app_id"]
    finish(conn, run_id, settings["checks"])


def consume(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK('balancer.worker', 0) AS acquired")
        if cursor.fetchone()["acquired"] != 1:
            return
    with transaction(conn) as cursor:
        cursor.execute("SELECT id FROM runs WHERE status = 'RUNNING'")
        for row in cursor.fetchall():
            run_id = row["id"]
            cursor.execute("UPDATE runs SET status = 'QUEUED' WHERE id = %s", (run_id,))
            stage(cursor, run_id, "queued", "Worker restarted; run queued again")

    while True:
        run_id = claim(conn)
        if run_id is None:
            time.sleep(1)
            continue
        try:
            process(conn, run_id)
        except Exception as exc:
            LOG.exception("Run %s failed", run_id)
            with transaction(conn) as cursor:
                cursor.execute("UPDATE runs SET status = 'FAILED', error = %s WHERE id = %s",
                               (str(exc)[:2000], run_id))
                stage(cursor, run_id, "failed", str(exc)[:2000])


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with connection() as conn:
                consume(conn)
        except pymysql.MySQLError:
            LOG.exception("Database connection or queue error")
        time.sleep(2)


if __name__ == "__main__":
    main()

