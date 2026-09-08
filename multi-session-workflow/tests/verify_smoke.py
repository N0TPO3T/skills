"""Verify smoke-run artifacts; actual task and scheduler behavior needs separate evidence."""

import csv
import hashlib
import json
import math
from pathlib import Path
import sys


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify(directory):
    source = directory / "input.csv"
    normalized_path = directory / "normalized.json"
    with source.open(newline="", encoding="utf-8") as stream:
        rows = [{"id": row["id"], "value": int(row["value"])} for row in csv.DictReader(stream)]
    check(bool(rows), "Fixture must contain at least one row")
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    check(normalized["schema_version"] == 1, "Unexpected normalized schema")
    check(normalized["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest(), "Source hash mismatch")
    check(normalized["rows"] == rows, "Normalized rows differ from source")
    check(all(type(row["value"]) is int for row in normalized["rows"]), "Values must be integers")
    check(summary["schema_version"] == 1, "Unexpected summary schema")
    check(summary["normalized_sha256"] == hashlib.sha256(normalized_path.read_bytes()).hexdigest(), "Normalized hash mismatch")
    total = sum(row["value"] for row in rows)
    check(summary["count"] == len(rows), "Count mismatch")
    check(summary["sum"] == total, "Sum mismatch")
    check(math.isclose(summary["mean"], total / len(rows), rel_tol=1e-12, abs_tol=1e-12), "Mean mismatch")
    print(f"PASS: {len(rows)} rows, sum={total}, mean={total / len(rows)}; both source hashes match")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 tests/verify_smoke.py /path/to/test-run")
    try:
        verify(Path(sys.argv[1]))
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise SystemExit(f"FAIL: {error}") from error
