"""Validate the anonymized recorder artifact without inferring burner cycles."""

import hashlib
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
assert hashlib.sha256((root / "observations.jsonl").read_bytes()).hexdigest() == manifest["sha256"]
records = [json.loads(line) for line in (root / "observations.jsonl").read_text().splitlines()]
assert len(records) == manifest["row_count"]
assert records == sorted(records, key=lambda row: (row["t_us"], row["entity"]))
counts = Counter(row["entity"] for row in records)
assert counts == {entity["entity"]: entity["source_count"] for entity in manifest["entities"]}
for row in records:
    assert set(row) <= {"entity", "t_us", "updated_us", "state", "boundary_state"}
    assert 0 <= row["t_us"] < manifest["duration_us"]
    assert 0 <= row["updated_us"] < manifest["duration_us"]
    assert isinstance(row["state"], str)
    assert "gateway_mqtt_" in row["entity"] or "gateway_native_" in row["entity"]
for entity in counts:
    series = [row for row in records if row["entity"] == entity]
    assert series[0].get("boundary_state") is True
    assert sum(bool(row.get("boundary_state")) for row in series) == 1
status = [row for row in records if row["entity"] == "sensor.gateway_mqtt_ketelstatus_am012"]
assert any(row["state"] == "4" for row in status)
assert any(
    left["state"] == "3" and 0 < right["t_us"] - left["t_us"] < 180_000_000
    for left, right in zip(status, status[1:])
)
assert not any("flame" in entity for entity in counts)
print(f"Verified {len(records)} records across {len(counts)} entities; no flame inference.")
