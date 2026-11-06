from contextlib import contextmanager
import json
import os

import pymysql


def connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "balancer"),
        password=os.environ["MYSQL_PASSWORD"],
        database=os.getenv("MYSQL_DATABASE", "balancer"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@contextmanager
def session():
    with connection() as conn, conn.cursor() as cursor:
        yield cursor


@contextmanager
def transaction(conn):
    conn.begin()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def many(cursor, table, columns, values):
    names = ", ".join(f"`{name}`" for name in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    cursor.executemany(f"INSERT INTO {table} ({names}) VALUES ({placeholders})", values)

