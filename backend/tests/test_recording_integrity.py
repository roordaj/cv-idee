"""Keep captured recorder evidence verifiable in the regular CI test run."""

import runpy
from pathlib import Path


def test_calenta_recording_integrity() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    verifier = repository_root / "fixtures" / "recordings" / "calenta-can-48h" / "verify.py"
    runpy.run_path(str(verifier), run_name="__main__")
