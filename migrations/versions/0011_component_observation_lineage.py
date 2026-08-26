"""add structural component Observation lineage

Revision ID: 0011_component_observation_lineage
Revises: 0010_partial_request
Create Date: 2026-08-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_component_observation_lineage"
down_revision: str | Sequence[str] | None = "0010_partial_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    _drop_observation_immutable_trigger()
    op.add_column(
        "research_observations",
        sa.Column("research_step_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE research_observations AS observation
           SET research_step_id = invocation.research_step_id
          FROM research_tool_invocations AS invocation
         WHERE invocation.id = observation.invocation_id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM research_observations
                WHERE research_step_id IS NULL
            ) THEN
                RAISE EXCEPTION 'RESEARCH_OBSERVATION_STEP_BACKFILL_FAILED'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )

    op.create_foreign_key(
        "fk_research_observations_step",
        "research_observations",
        "research_steps",
        ["research_step_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "research_observations",
        "research_step_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_constraint(
        "uq_research_observations_invocation",
        "research_observations",
        type_="unique",
    )
    op.alter_column(
        "research_observations",
        "invocation_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_index(
        "ux_research_observations_invocation_nonnull",
        "research_observations",
        ["invocation_id"],
        unique=True,
        postgresql_where=sa.text("invocation_id IS NOT NULL"),
    )
    op.create_index(
        "ux_research_observations_component_step",
        "research_observations",
        ["research_step_id"],
        unique=True,
        postgresql_where=sa.text("invocation_id IS NULL"),
    )
    _create_observation_immutable_trigger()


def downgrade() -> None:
    component_observations = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM research_observations WHERE invocation_id IS NULL")
    )
    if component_observations:
        raise RuntimeError("COMPONENT_OBSERVATIONS_PREVENT_DOWNGRADE")

    _drop_observation_immutable_trigger()
    op.drop_index(
        "ux_research_observations_component_step",
        table_name="research_observations",
    )
    op.drop_index(
        "ux_research_observations_invocation_nonnull",
        table_name="research_observations",
    )
    op.alter_column(
        "research_observations",
        "invocation_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_research_observations_invocation",
        "research_observations",
        ["invocation_id"],
    )
    op.drop_constraint(
        "fk_research_observations_step",
        "research_observations",
        type_="foreignkey",
    )
    op.drop_column("research_observations", "research_step_id")
    _create_observation_immutable_trigger()


def _drop_observation_immutable_trigger() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_research_observations_immutable ON research_observations"
    )


def _create_observation_immutable_trigger() -> None:
    op.execute(
        """
        CREATE TRIGGER trg_research_observations_immutable
        BEFORE UPDATE OR DELETE ON research_observations
        FOR EACH ROW EXECUTE FUNCTION stage7_reject_mutation()
        """
    )
