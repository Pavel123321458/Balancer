"""Read a single organizer RESULTS tree without extracting uploaded files."""
import json
import re
from pathlib import PurePosixPath

SOURCES = {"BEFORE_MASTER": "BEFORE", "AFTER_BETA": "AFTER"}
MAX_UPLOAD = 64 * 1024 * 1024


def entries(archive):
    roots = set()
    files = {source: {} for source in SOURCES.values()}
    total_bytes = 0
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        parts = PurePosixPath(entry.filename).parts
        if len(parts) < 3 or parts[-3] != "RESULTS" or parts[-2] not in SOURCES:
            continue
        if not parts[-1].endswith(".json"):
            continue
        roots.add(parts[:-3])
        app_id = parts[-1][:-5]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", app_id):
            raise ValueError(f"Invalid application filename: {parts[-1]}")
        source = SOURCES[parts[-2]]
        if app_id in files[source]:
            raise ValueError(f"Duplicate {source} application {app_id}")
        files[source][app_id] = entry
        total_bytes += entry.file_size
        if entry.file_size > 8 * 1024 * 1024 or total_bytes > 512 * 1024 * 1024:
            raise ValueError("Uncompressed responses exceed size limit")
    before, after = files["BEFORE"], files["AFTER"]
    if len(roots) != 1 or not before or before.keys() != after.keys():
        raise ValueError(
            f"Expected one RESULTS tree with matching slices, found "
            f"{len(roots)} trees and {len(before.keys() ^ after.keys())} unpaired IDs"
        )
    return {app_id: (before[app_id], after[app_id]) for app_id in sorted(before)}


def read_response(archive, entry):
    with archive.open(entry) as file:
        document = json.loads(file.read().decode("utf-8-sig"))
    if not isinstance(document, dict):
        raise ValueError(f"Expected a JSON object in {entry.filename}")
    return document

