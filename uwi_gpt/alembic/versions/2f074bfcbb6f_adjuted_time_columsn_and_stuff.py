"""adjusted time columns and casting from VARCHAR to TIME

Revision ID: 2f074bfcbb6f
Revises: 78e09a6ed8a7
Create Date: 2025-05-13 05:34:13.195237
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2f074bfcbb6f"
down_revision: Union[str, None] = "78e09a6ed8a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ Use raw SQL to cast VARCHAR to TIME using `USING` clause
    op.execute(
        """
        ALTER TABLE calendar_sessions
        ALTER COLUMN start_time
        TYPE TIME WITHOUT TIME ZONE
        USING start_time::time;
    """
    )
    op.execute(
        """
        ALTER TABLE calendar_sessions
        ALTER COLUMN end_time
        TYPE TIME WITHOUT TIME ZONE
        USING end_time::time;
    """
    )


def downgrade() -> None:
    # If rolling back, convert TIME back to VARCHAR
    op.alter_column(
        "calendar_sessions",
        "end_time",
        existing_type=sa.Time(),
        type_=sa.VARCHAR(),
        existing_nullable=True,
    )
    op.alter_column(
        "calendar_sessions",
        "start_time",
        existing_type=sa.Time(),
        type_=sa.VARCHAR(),
        existing_nullable=True,
    )
