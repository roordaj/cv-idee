"""Loading of scenario fixtures and a standalone run of pipeline stages 1-4.

``cvidee.analysis.pipeline.run_pipeline`` is not implemented yet (runner work in progress), so
:func:`run_stages` composes the existing stage functions the same way it will.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cvidee.analysis.cycles import detect_cycles
from cvidee.analysis.modes import classify_modes
from cvidee.analysis.quality import QualityResult, apply_quality
from cvidee.analysis.timeline import build_stage1
from cvidee.analysis.types import BurnerCycle, ModeSegment
from cvidee.testing.generator import GeneratedData

SCENARIO_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "scenarios"


def scenario_dirs() -> list[Path]:
    return sorted(p for p in SCENARIO_ROOT.iterdir() if (p / "scenario.py").is_file())


def load_build(directory: Path) -> GeneratedData:
    spec = importlib.util.spec_from_file_location(
        f"scenario_{directory.name.replace('-', '_')}", directory / "scenario.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.build()
    assert isinstance(data, GeneratedData)
    return data


def load_expected(directory: Path) -> dict[str, Any]:
    loaded = yaml.safe_load((directory / "expected.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@dataclass(frozen=True, slots=True)
class StageRun:
    quality: QualityResult
    modes: tuple[ModeSegment, ...]
    cycles: tuple[BurnerCycle, ...]


def run_stages(data: GeneratedData) -> StageRun:
    stage1 = build_stage1(data.observations, data.connection_events, data.config, data.window)
    quality = apply_quality(stage1.timelines, data.config, data.window, stage1.outages)
    modes = classify_modes(quality.timelines, data.config, data.window)
    cycles = detect_cycles(quality.timelines, modes, data.config, data.window)
    return StageRun(quality, modes, cycles)
