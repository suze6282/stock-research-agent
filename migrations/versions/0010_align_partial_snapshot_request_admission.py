"""align partial snapshot request admission

Revision ID: 0010_partial_request
Revises: 0009_controlled_live_evidence
Create Date: 2026-08-12 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_partial_request"
down_revision: str | Sequence[str] | None = "0009_controlled_live_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stage7_validate_request_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_security_id uuid;
            linked_as_of timestamptz;
            linked_status varchar;
        BEGIN
            SELECT security_id, research_as_of_time, status
              INTO linked_security_id, linked_as_of, linked_status
              FROM data_snapshots WHERE id = NEW.snapshot_id;
            IF linked_security_id IS DISTINCT FROM NEW.security_id
               OR linked_as_of > NEW.research_as_of_time
               OR linked_status NOT IN ('COMPLETE', 'PARTIAL') THEN
                RAISE EXCEPTION 'research request snapshot context does not match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stage7_validate_request_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_security_id uuid;
            linked_as_of timestamptz;
            linked_status varchar;
        BEGIN
            SELECT security_id, research_as_of_time, status
              INTO linked_security_id, linked_as_of, linked_status
              FROM data_snapshots WHERE id = NEW.snapshot_id;
            IF linked_security_id IS DISTINCT FROM NEW.security_id
               OR linked_as_of > NEW.research_as_of_time
               OR linked_status <> 'COMPLETE' THEN
                RAISE EXCEPTION 'research request snapshot context does not match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
