"""enforce Research Observation cross-table lineage integrity

Revision ID: 0012_component_observation_lineage_integrity
Revises: 0011_component_observation_lineage
Create Date: 2026-08-13 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_component_observation_lineage_integrity"
down_revision: str | Sequence[str] | None = "0011_component_observation_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM research_observations AS observation
                  LEFT JOIN research_agent_runs AS run
                    ON run.id = observation.research_agent_run_id
                  LEFT JOIN research_steps AS step
                    ON step.id = observation.research_step_id
                  LEFT JOIN research_tool_invocations AS invocation
                    ON invocation.id = observation.invocation_id
                 WHERE run.id IS NULL
                    OR step.id IS NULL
                    OR step.research_agent_run_id IS DISTINCT FROM observation.research_agent_run_id
                    OR observation.security_id IS DISTINCT FROM run.security_id
                    OR observation.snapshot_id IS DISTINCT FROM run.snapshot_id
                    OR (
                        observation.invocation_id IS NULL
                        AND step.tool_name IS NOT NULL
                    )
                    OR (
                        observation.invocation_id IS NOT NULL
                        AND (
                            invocation.id IS NULL
                            OR step.tool_name IS NULL
                            OR invocation.research_agent_run_id
                                IS DISTINCT FROM observation.research_agent_run_id
                            OR invocation.research_step_id
                                IS DISTINCT FROM observation.research_step_id
                        )
                    )
            ) THEN
                RAISE EXCEPTION 'OBSERVATION_HISTORICAL_LINEAGE_INVALID'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION stage7_validate_observation_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_run research_agent_runs%ROWTYPE;
            linked_step research_steps%ROWTYPE;
            linked_invocation research_tool_invocations%ROWTYPE;
        BEGIN
            SELECT * INTO linked_run
              FROM research_agent_runs
             WHERE id = NEW.research_agent_run_id;
            IF linked_run.id IS NULL THEN
                RAISE EXCEPTION 'OBSERVATION_RUN_NOT_FOUND'
                    USING ERRCODE = '23503';
            END IF;

            SELECT * INTO linked_step
              FROM research_steps
             WHERE id = NEW.research_step_id;
            IF linked_step.id IS NULL THEN
                RAISE EXCEPTION 'OBSERVATION_STEP_NOT_FOUND'
                    USING ERRCODE = '23503';
            END IF;
            IF linked_step.research_agent_run_id
                IS DISTINCT FROM NEW.research_agent_run_id THEN
                RAISE EXCEPTION 'OBSERVATION_STEP_RUN_MISMATCH'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.security_id IS DISTINCT FROM linked_run.security_id THEN
                RAISE EXCEPTION 'OBSERVATION_SECURITY_MISMATCH'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.snapshot_id IS DISTINCT FROM linked_run.snapshot_id THEN
                RAISE EXCEPTION 'OBSERVATION_SNAPSHOT_MISMATCH'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.invocation_id IS NULL THEN
                IF linked_step.tool_name IS NOT NULL THEN
                    RAISE EXCEPTION 'OBSERVATION_TOOL_INVOCATION_REQUIRED'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;

            SELECT * INTO linked_invocation
              FROM research_tool_invocations
             WHERE id = NEW.invocation_id;
            IF linked_invocation.id IS NULL THEN
                RAISE EXCEPTION 'OBSERVATION_INVOCATION_NOT_FOUND'
                    USING ERRCODE = '23503';
            END IF;
            IF linked_step.tool_name IS NULL THEN
                RAISE EXCEPTION 'OBSERVATION_COMPONENT_INVOCATION_FORBIDDEN'
                    USING ERRCODE = '23514';
            END IF;
            IF linked_invocation.research_agent_run_id
                IS DISTINCT FROM NEW.research_agent_run_id THEN
                RAISE EXCEPTION 'OBSERVATION_INVOCATION_RUN_MISMATCH'
                    USING ERRCODE = '23514';
            END IF;
            IF linked_invocation.research_step_id
                IS DISTINCT FROM NEW.research_step_id THEN
                RAISE EXCEPTION 'OBSERVATION_INVOCATION_STEP_MISMATCH'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_research_observations_validate_lineage
        BEFORE INSERT ON research_observations
        FOR EACH ROW EXECUTE FUNCTION stage7_validate_observation_lineage()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_research_observations_validate_lineage ON research_observations"
    )
    op.execute("DROP FUNCTION IF EXISTS stage7_validate_observation_lineage()")
