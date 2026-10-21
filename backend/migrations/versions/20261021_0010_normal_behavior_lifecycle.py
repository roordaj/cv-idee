"""Persist versioned normal-behavior model lifecycle and metric references.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "normal_behavior_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at_ts", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ts", sa.BigInteger(), nullable=False),
        sa.Column("effective_from_ts", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("paused_at_ts", sa.BigInteger(), nullable=True),
        sa.Column("status_before_pause", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "status IN ('insufficient_data', 'learning', 'active', 'paused')",
            name=op.f("ck_normal_behavior_models_status"),
        ),
        sa.CheckConstraint(
            "status_before_pause IS NULL OR status_before_pause IN "
            "('insufficient_data', 'learning', 'active', 'paused')",
            name=op.f("ck_normal_behavior_models_status_before_pause"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_normal_behavior_models_version_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_normal_behavior_models")),
        sa.UniqueConstraint(
            "metric_name", "version", name=op.f("uq_normal_behavior_models_metric_name_version")
        ),
    )
    op.create_index(
        "ix_normal_behavior_models_metric_current",
        "normal_behavior_models",
        ["metric_name", "is_current"],
    )
    op.create_table(
        "normal_behavior_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("window_kind", sa.String(length=16), nullable=False),
        sa.Column("window_start_ts", sa.BigInteger(), nullable=False),
        sa.Column("window_end_ts", sa.BigInteger(), nullable=False),
        sa.Column("cycle_start_ts", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("time_basis_seconds", sa.Float(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=True),
        sa.Column("settings_revision_id", sa.Integer(), nullable=True),
        sa.Column("profile_version_id", sa.Integer(), nullable=True),
        sa.Column("analysis_version", sa.String(length=64), nullable=True),
        sa.Column("context", sa.JSON(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "coverage >= 0 AND coverage <= 1",
            name=op.f("ck_normal_behavior_observations_coverage_fraction"),
        ),
        sa.CheckConstraint(
            "time_basis_seconds >= 0",
            name=op.f("ck_normal_behavior_observations_time_basis_nonnegative"),
        ),
        sa.CheckConstraint(
            "window_end_ts > window_start_ts",
            name=op.f("ck_normal_behavior_observations_window_end_after_start"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_normal_behavior_observations_analysis_run_id_analysis_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["normal_behavior_models.id"],
            name=op.f("fk_normal_behavior_observations_model_id_normal_behavior_models"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_version_id"],
            ["installation_profiles.id"],
            name=op.f("fk_normal_behavior_observations_profile_version_id_installation_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["settings_revision_id"],
            ["settings_revisions.id"],
            name=op.f("fk_normal_behavior_observations_settings_revision_id_settings_revisions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_normal_behavior_observations")),
        sa.UniqueConstraint(
            "model_id",
            "metric_name",
            "mode",
            "window_kind",
            "window_start_ts",
            "cycle_start_ts",
            name=op.f(
                "uq_normal_behavior_observations_model_id_metric_name_mode_window_kind_window_start_ts_cycle_start_ts"
            ),
        ),
    )
    op.create_index(
        "ix_normal_behavior_observations_period",
        "normal_behavior_observations",
        ["window_start_ts", "window_end_ts"],
    )
    op.create_table(
        "normal_behavior_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("occurred_at_ts", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("effective_from_ts", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('created', 'paused', 'resumed', 'reference_started')",
            name=op.f("ck_normal_behavior_events_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["normal_behavior_models.id"],
            name=op.f("fk_normal_behavior_events_model_id_normal_behavior_models"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_normal_behavior_events")),
    )


def downgrade() -> None:
    op.drop_table("normal_behavior_events")
    op.drop_index(
        "ix_normal_behavior_observations_period", table_name="normal_behavior_observations"
    )
    op.drop_table("normal_behavior_observations")
    op.drop_index("ix_normal_behavior_models_metric_current", table_name="normal_behavior_models")
    op.drop_table("normal_behavior_models")
