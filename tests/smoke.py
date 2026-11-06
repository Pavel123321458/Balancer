"""Run upload -> queue -> worker -> reports against the Compose stack."""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from backend.datasets import entries, read_response


def verify(archive, base_url):
    def api(path, body=None, content_type="application/json"):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        with urlopen(Request(base_url + path, body, {"Content-Type": content_type}), timeout=90) as result:
            return json.load(result)

    boundary = "balancer-verification-multipart"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            'filename="dataset.zip"\r\nContent-Type: application/zip\r\n\r\n').encode()
    body += archive.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    dataset = api("/datasets", body, f"multipart/form-data; boundary={boundary}")
    run = api("/runs", {"dataset_id": dataset["id"]})
    path = f"/runs/{run['id']}"
    started = time.monotonic()
    assert api(path + "/start", {})["status"] == "QUEUED"
    previous = None
    while time.monotonic() - started < 300:
        state = api(path)
        progress = (state["status"], state["stage"], state["processed"])
        if progress != previous:
            print(*progress, flush=True)
            previous = progress
        if state["status"] == "FAILED":
            raise RuntimeError(state["error"])
        if state["status"] == "SUCCEEDED":
            break
        time.sleep(1)
    else:
        raise TimeoutError(f"Run {run['id']} did not finish")
    elapsed = time.monotonic() - started
    with ZipFile(archive) as source:
        pairs = entries(source)
        decision_changes = sum(
            read_response(source, before)["decisionResult"]["decision"] !=
            read_response(source, after)["decisionResult"]["decision"]
            for before, after in pairs.values()
        )
    summary = state["summary"]
    assert summary["applications"] == dataset["applications"] == len(pairs)
    assert summary["apps_with_decision_change"] == decision_changes
    detail = api(path + "/results?only_differences=true&limit=1")["rows"]
    assert bool(detail) == bool(summary["apps_with_differences"])
    checks = api(path + "/checks?limit=1000")
    assert api(path + "/facts?limit=1")
    assert api(path + "/logs")[-1]["stage"] == "done"
    for scope, total in (("differences", summary["apps_with_differences"]),
                         ("decisions", summary["apps_with_decision_change"])):
        assert api(path + f"/applications?scope={scope}")["total"] == total
    pivot = api(path + "/pivot?group=CLASS&group=KEY&split=SOURCE&limit=1")["rows"][0]
    source = "AFTER" if pivot["AFTER"] else "BEFORE"
    filters = json.dumps({"CLASS": pivot["CLASS"], "KEY": pivot["KEY"], "SOURCE": source})
    apps = api(path + "/applications?" + urlencode({"filters": filters, "limit": 1}))
    assert 0 < apps["total"] <= pivot[source]
    app_id = apps["rows"][0]["APP_ID"]
    assert api(path + "/results?" + urlencode({"app_id": app_id, "facts": filters, "limit": 1}))["rows"]
    print(json.dumps({
        **summary, "elapsed_seconds": round(elapsed, 2), "check_rows": len(checks),
        "checks": sorted({row["check_id"] for row in checks}),
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    verify(args.archive, args.url)

