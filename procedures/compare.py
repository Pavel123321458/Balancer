IDENTITY = ("APP_ID", "PATH", "ARRAY_KEY")
DIMENSIONS = ("APP_ID", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH")


def compare(before, after, params):
    def index(rows):
        result = {}
        for row in rows:
            key = tuple(row[field] for field in IDENTITY)
            if key in result:
                raise ValueError(f"Duplicate normalized attribute {key}")
            result[key] = row
        return result

    left, right = index(before), index(after)
    for key in sorted(left.keys() | right.keys()):
        b, a = left.get(key), right.get(key)
        if b is None:
            kind = "ATTRIBUTE_NEW"
        elif a is None:
            kind = "ATTRIBUTE_LOST"
        else:
            kind = "SAME" if b["VALUE"] == a["VALUE"] else "VALUE_CHANGED"
        yield {
            **{field: (a or b)[field] for field in DIMENSIONS},
            "VALUE_BEFORE": b["VALUE"] if b else None,
            "VALUE_AFTER": a["VALUE"] if a else None,
            "ADJUSTED_BEFORE": b["ADJUSTED_VALUE"] if b else None,
            "ADJUSTED_AFTER": a["ADJUSTED_VALUE"] if a else None,
            "DIFF_FLAG": int(kind != "SAME"), "CHANGE_TYPE": kind,
        }

