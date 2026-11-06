from collections import Counter
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from backend.datasets import entries
from procedures.compare import compare
from procedures.normalize import ARRAYS, normalize

MATERIALS = Path(os.getenv("ORGANIZER_DIR", ".organizer/ЗАДАНИЕ"))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=";"))


def csv_fields(rows, fields):
    return sorted(tuple("" if row[field] is None else str(row[field]) for field in fields) for row in rows)


class OrganizerTests(unittest.TestCase):
    def test_both_organizer_examples(self):
        for folder in ("example", "examples"):
            with self.subTest(folder=folder):
                path = MATERIALS / folder
                params = {
                    "ignore": ["company.decisionResult.calculatedAt"],
                    "arrays": {"company.scoreCardResult": ["name"], "company.rejectReasons": "value"},
                    "columns": {
                        **{
                            f"company.scoreCardResult.{field}": {
                                "SUFFIX": "scoreCard", "PATH": f"company.scoreCardResult.scoreCard.{field}"
                            } for field in ("name", "value", "version")
                        },
                        **{
                            f"company.limitResult.{field}": {
                                "SUFFIX": "Limit", "PATH": f"company.limitResult.Limit.{field}"
                            } for field in ("currency", "limit")
                        },
                        "company.rejectReasons": {
                            "SUFFIX": "reason", "KEY": "code" if folder == "example" else "",
                            "PATH": "company.rejectReasons.reason.code",
                        },
                    },
                    "buckets": {
                        "company.limitResult.limit": [(0, 100000, "(0 - 100K]"), (100000, 250000, "(100K - 250K]")],
                        "company.scoreCardResult.value": [(0, 0.3, "(0 - 0.3]"), (0.3, 0.6, "(0.3 - 0.6]")],
                    },
                }
                left = normalize("1001", "BEFORE", read_json(next(path.glob("01*.json"))), params)
                right = normalize("1001", "AFTER", read_json(next(path.glob("02*.json"))), params)
                diff = list(compare(left, right, {}))
                for number, rows in (("03", left), ("04", right), ("05", left + right), ("06", diff)):
                    expected = csv_rows(next(path.glob(f"{number}*.csv")))
                    fields = [field for field in expected[0] if field != "COMMENT"]
                    self.assertEqual(csv_fields(rows, fields), csv_fields(expected, fields))
                self.assertEqual(Counter(row["CHANGE_TYPE"] for row in diff),
                                 {"SAME": 8, "VALUE_CHANGED": 4, "ATTRIBUTE_NEW": 2})
                self.assertEqual(sum(row["CHANGE_TYPE"] == "ATTRIBUTE_LOST" for row in compare(right, left, {})), 2)

    def test_real_response_reordering_and_vector_positions(self):
        original = read_json(MATERIALS / "samples/BEFORE/I32554354.json")
        # Populate a documented case missing from this sample, including a composite key.
        offer = {"product_id": 5123, "type": "standard", "rank": 1}
        original["decisionResult"]["available_offers"] = [offer, {**offer, "type": "manual", "rank": 2}]
        after = deepcopy(original)
        visited = set()

        def reorder(node, path=""):
            if isinstance(node, dict):
                for name, child in node.items():
                    reorder(child, f"{path}.{name}" if path else name)
            elif isinstance(node, list):
                visited.add(path)
                if ARRAYS[path] != "index":
                    node.reverse()
                for child in node:
                    reorder(child, path)

        reorder(after)
        self.assertEqual(visited, ARRAYS.keys())
        after["appData"].update(request_id="another", createDateTime="another")
        left = normalize("I32554354", "BEFORE", original, {})
        right = normalize("I32554354", "AFTER", after, {})
        self.assertTrue(all(row["CHANGE_TYPE"] == "SAME" for row in compare(left, right, {})))
        vector = after["decisionResult"]["scoring"][0]["value"]
        vector[0], vector[1] = vector[1], vector[0]
        right = normalize("I32554354", "AFTER", after, {})
        changes = [row for row in compare(left, right, {}) if row["DIFF_FLAG"]]
        self.assertEqual([(row["PATH"], row["CHANGE_TYPE"]) for row in changes],
                         [("decisionResult.scoring.value", "VALUE_CHANGED")] * 2)

    def test_null_false_and_missing_are_distinct(self):
        inputs = ({"flag": None}, {"flag": False}, {})
        rows = [normalize("id", "BEFORE" if i == 0 else "AFTER", doc, {})
                for i, doc in enumerate(inputs)]
        self.assertEqual(next(compare(rows[0], rows[1], {}))["CHANGE_TYPE"], "VALUE_CHANGED")
        self.assertEqual(next(compare(rows[0], rows[2], {}))["CHANGE_TYPE"], "ATTRIBUTE_LOST")
        self.assertEqual(next(compare(rows[2], rows[0], {}))["VALUE_AFTER"], "NULL")

    def test_duplicate_key_rejected(self):
        offer = {"product_id": 1, "type": "manual"}
        with self.assertRaisesRegex(ValueError, "Duplicate array key"):
            normalize("id", "BEFORE", {"decisionResult": {"available_offers": [offer, offer]}}, {})

    def test_zip_pairs_by_filename_and_rejects_missing_slice(self):
        from io import BytesIO

        with ZipFile(BytesIO(), "w") as archive:
            archive.writestr("root/RESULTS/BEFORE_MASTER/A.json", "{}")
            archive.writestr("root/RESULTS/AFTER_BETA/B.json", "{}")
            with self.assertRaisesRegex(ValueError, "2 unpaired IDs"):
                entries(archive)
            archive.writestr("root/RESULTS/BEFORE_MASTER/B.json", "{}")
            archive.writestr("root/RESULTS/AFTER_BETA/A.json", "{}")
            self.assertEqual(list(entries(archive)), ["A", "B"])

