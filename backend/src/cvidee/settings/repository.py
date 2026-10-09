"""Settings snapshots and rule parameter adapters shared by API and runner."""

import hashlib
import json
from dataclasses import replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.analysis.types import PipelineConfig
from cvidee.api.schemas.settings import AnalysisSettings
from cvidee.rules.base import RuleParams
from cvidee.rules.registry import RuleRegistry
from cvidee.store.models import SettingsRevision

ALIASES = {
    "min_observation_h": "min_observation_hours",
    "structural_days": "repetition_days",
    "window_days": "repetition_window_days",
}


def current_revision(session: Session) -> SettingsRevision | None:
    return session.scalar(select(SettingsRevision).order_by(SettingsRevision.id.desc()).limit(1))


def settings_hash(values: AnalysisSettings) -> str:
    payload = json.dumps(values.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def revision_token(row: SettingsRevision | None) -> str:
    return (
        f"{row.id}:{row.config_hash}"
        if row is not None
        else f"0:{settings_hash(AnalysisSettings())}"
    )


def effective_values(row: SettingsRevision | None) -> AnalysisSettings:
    raw = {} if row is None else dict(row.values)
    if "retention.raw_days" in raw and "retention_days" not in raw:
        raw["retention_days"] = raw["retention.raw_days"]
    return AnalysisSettings.model_validate(
        {key: value for key, value in raw.items() if key in AnalysisSettings.model_fields}
    )


def rule_params(registry: RuleRegistry, rule_id: str, values: AnalysisSettings) -> RuleParams:
    """Use registered schemas for validation; explicit aliases bridge the UI vocabulary."""
    raw = {
        field: getattr(values, ALIASES.get(field, field))
        for field in registry.get(rule_id).params_schema.model_fields
        if hasattr(values, ALIASES.get(field, field))
    }
    return registry.validate_params(rule_id, raw)


def settings_schema(registry: RuleRegistry) -> dict[str, Any]:
    """Design-compatible UI schema plus the complete schemas of registered rules."""
    schema = AnalysisSettings.model_json_schema()
    schema["x-rule-schemas"] = {
        rule.id: rule.params_schema.model_json_schema() for rule in registry
    }
    for rule in registry:
        for field, definition in rule.params_schema.model_json_schema()["properties"].items():
            target = ALIASES.get(field, field)
            if target not in schema["properties"]:
                continue
            prop = schema["properties"][target]
            prop["x-rule"] = sorted(set((*prop.get("x-rule", []), rule.id)))
            # The intersection preserves both the UI and registered rule constraints.
            if "minimum" in definition:
                prop["minimum"] = max(
                    prop.get("minimum", definition["minimum"]), definition["minimum"]
                )
            if "maximum" in definition:
                prop["maximum"] = min(
                    prop.get("maximum", definition["maximum"]), definition["maximum"]
                )
    return schema


def pipeline_settings(base: PipelineConfig | None, values: AnalysisSettings) -> PipelineConfig:
    base = base if base is not None else PipelineConfig(signals=())
    lookahead = values.demand_after_stop_s * 1000
    return replace(
        base, end_reason_lookahead_ms=lookahead, settle_ms=max(base.settle_ms, lookahead)
    )
