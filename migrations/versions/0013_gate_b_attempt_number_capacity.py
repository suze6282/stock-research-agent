"""increase physical Gate B attempt-number capacity

Revision ID: 0013_gate_b_attempt_number_capacity
Revises: 0012_component_observation_lineage_integrity
Create Date: 2026-08-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_gate_b_attempt_number_capacity"
down_revision: str | Sequence[str] | None = "0012_component_observation_lineage_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_provider_request_attempts_bounds"
_TABLE_NAME = "provider_request_attempts"
_MAX_FOUR_CHECK = (
    "attempt_number BETWEEN 1 AND 4 "
    "AND response_bytes >= 0 "
    "AND (response_status_code IS NULL "
    "OR response_status_code BETWEEN 100 AND 599)"
)
_MAX_THREE_CHECK = (
    "attempt_number BETWEEN 1 AND 3 "
    "AND response_bytes >= 0 "
    "AND (response_status_code IS NULL "
    "OR response_status_code BETWEEN 100 AND 599)"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, _TABLE_NAME, _MAX_FOUR_CHECK)


def downgrade() -> None:
    attempt_four_rows = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM provider_request_attempts WHERE attempt_number = 4")
    )
    if attempt_four_rows:
        raise RuntimeError("GATE_B_ATTEMPT_FOUR_PREVENTS_DOWNGRADE")

    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, _TABLE_NAME, _MAX_THREE_CHECK)
