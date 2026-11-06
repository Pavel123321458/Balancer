import json

from backend.analytics import matching_attributes

COLUMNS = (
    "APP_ID", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH",
    "VALUE_BEFORE", "VALUE_AFTER", "ADJUSTED_BEFORE", "ADJUSTED_AFTER",
    "DIFF_FLAG", "CHANGE_TYPE",
)
SELECT_COLUMNS = ", ".join(f"`{field}`" for field in COLUMNS)
FILTERS = {
    "path": "PATH", "key": "KEY", "array_key": "ARRAY_KEY", "diff_flag": "DIFF_FLAG",
    "change_type": "CHANGE_TYPE", "value_before": "VALUE_BEFORE",
    "value_after": "VALUE_AFTER", "app_ids": "APP_ID",
}


class Mart:
    def __init__(self, cursor, run_id):
        self.cursor = cursor
        self.run_id = run_id

    def _query(self, select, filters, tail="", extra=()):
        conditions, params = ["run_id = %s"], [self.run_id]
        for name, value in filters.items():
            if name == "fact_filters":
                conditions.append(matching_attributes(value, "comparisons") +
                                  " AND n.PATH = comparisons.PATH AND n.ARRAY_KEY = comparisons.ARRAY_KEY)")
                params.extend(value.values())
                continue
            if name == "path_prefix":
                escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                conditions.append("PATH LIKE %s ESCAPE '!'")
                params.append(escaped + "%")
                continue
            column = f"`{FILTERS[name]}`"
            if isinstance(value, (list, tuple, set)):
                if not value:
                    conditions.append("FALSE")
                    continue
                placeholders = ", ".join(["%s"] * len(value))
                conditions.append(f"{column} IN ({placeholders})")
                params.extend(value)
            elif value is None:
                conditions.append(f"{column} IS NULL")
            else:
                conditions.append(f"{column} = %s")
                params.append(value)
        where = " AND ".join(conditions)
        self.cursor.execute(f"SELECT {select} FROM comparisons WHERE {where} {tail}", (*params, *extra))
        return self.cursor.fetchall()

    def rows(self, **filters):
        return self._query(SELECT_COLUMNS, filters, "ORDER BY APP_ID, PATH, ARRAY_KEY")

    def page(self, limit, offset, **filters):
        return self._query(SELECT_COLUMNS, filters, "ORDER BY APP_ID, PATH, ARRAY_KEY LIMIT %s OFFSET %s",
                           (limit, offset))

    def count(self, **filters):
        return self._query("COUNT(*) AS n", filters)[0]["n"]

    def app_ids(self, **filters):
        return [r["APP_ID"] for r in self._query("DISTINCT APP_ID", filters, "ORDER BY APP_ID")]

    def segments(self):
        self.cursor.execute("SELECT segment FROM run_apps WHERE run_id = %s ORDER BY APP_ID", (self.run_id,))
        return [json.loads(row["segment"]) for row in self.cursor.fetchall()]

    def total_apps(self):
        self.cursor.execute("SELECT COUNT(*) AS n FROM run_apps WHERE run_id = %s", (self.run_id,))
        return self.cursor.fetchone()["n"]

