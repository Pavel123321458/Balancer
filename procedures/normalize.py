"""SPR JSON procedure. Array rules use paths without array indices."""
from urllib.parse import quote

ARRAYS = {
    "decisionResult.available_offers": ["product_id", "type"],
    "decisionResult.product_trials": ["product_id"],
    "decisionResult.product_trials.rules": ["name"],
    "decisionResult.product_trials.scoring.scoreModels": ["modelName"],
    "decisionResult.scoring": ["modelName"],
    "decisionResult.scoring.value": "index",
    "ext_data": ["body.action"],
    "product_catalog": ["mfo_id", "product_id"],
    "tariff_matrix": ["mfo_id", "product_id"],
}
IGNORE = ["appData.request_id", "appData.createDateTime"]


def value_text(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def lookup(obj, path):
    for part in path.split("."):
        obj = obj[part]
    if isinstance(obj, (dict, list)) or obj is None:
        raise ValueError(f"Invalid array key at {path}")
    return value_text(obj)


def normalize(app_id, source, document, params):
    arrays = {**ARRAYS, **params.get("arrays", {})}
    ignored = set(params.get("ignore", IGNORE))
    columns = params.get("columns", {})
    buckets = params.get("buckets", {})
    rows = {}

    def walk(node, parts, keys=(), scalar_element=False):
        path = ".".join(parts)
        if path in ignored:
            return
        if isinstance(node, dict):
            for name, child in node.items():
                walk(child, (*parts, name), keys)
            return
        if isinstance(node, list):
            rule = arrays.get(path)
            if rule is None:
                raise ValueError(f"No array rule for {path}")
            seen = set()
            for index, child in enumerate(node):
                if rule == "index":
                    key = str(index)
                elif rule == "value" and not isinstance(child, (dict, list)):
                    key = quote(value_text(child), safe="@")
                    if key in seen:
                        continue
                elif isinstance(rule, list) and rule and isinstance(child, dict):
                    key = ":".join(quote(lookup(child, field), safe="@") for field in rule)
                else:
                    raise ValueError(f"Invalid array rule or element at {path}")
                if key in seen:
                    raise ValueError(f"Duplicate array key {key!r} at {path}")
                seen.add(key)
                walk(child, parts, (*keys, key), scalar_element=True)
            return

        key = "|".join(keys)
        identity = (path, key)
        if identity in rows:
            raise ValueError(f"Duplicate attribute {identity}")
        value = value_text(node)
        adjusted = value
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            for lower, upper, label in buckets.get(path, []):
                if lower < node <= upper:
                    adjusted = label
                    break
        row = {
            "APP_ID": app_id, "SOURCE": source, "PATH": path,
            "PREFIX": parts[0], "CLASS": parts[1] if len(parts) > 1 else "",
            "SUFFIX": ".".join(parts[2:] if scalar_element else parts[2:-1]),
            "KEY": "" if scalar_element else parts[-1],
            "ARRAY_KEY": key, "VALUE": value, "ADJUSTED_VALUE": adjusted,
        }
        row.update(columns.get(path, {}))
        rows[identity] = row

    actual_id = document.get("appData", {}).get("application_id")
    if actual_id is not None and str(actual_id) != app_id:
        raise ValueError(f"Application ID {actual_id!r} differs from filename {app_id!r}")
    walk(document, ())
    return list(rows.values())


def segments(app_id, before, after, params):
    result = {"APP_ID": app_id}
    products = set()
    for source, document in (("BEFORE", before), ("AFTER", after)):
        decision = document.get("decisionResult", {})
        offers = decision.get("available_offers", [])
        trials = decision.get("product_trials", [])
        top = min(offers, key=lambda o: (o["rank"], str(o["product_id"]), o["type"]), default={})
        trial = min(trials, key=lambda t: (
            t["product_id"] != top.get("product_id"), str(t["product_id"])
        ), default={})
        products.update(str(t["product_id"]) for t in trials)
        result.update({
            f"DECISION_{source}": decision.get("decision"),
            f"TOP_OFFER_{source}": top.get("product_id"),
            f"PD_MODEL_{source}": trial.get("scoring", {}).get("pd", {}).get("modelName"),
            f"CUTOFF_{source}": trial.get("cutOff", {}).get("name"),
            f"REJECT_REASON_{source}": trial.get("rejectReason"),
            f"SCORE_OKB_{source}": document.get("characteristics", {}).get("score_okb"),
        })
        if source == "AFTER":
            result["PARTNER_TYPE"] = trial.get("partner_type")
            result["ROUTING_METHOD"] = trial.get("routing_method")
    result["PRODUCTS"] = ";".join(sorted(products))
    result["DECISION_CHANGED"] = int(result["DECISION_BEFORE"] != result["DECISION_AFTER"])
    return result

