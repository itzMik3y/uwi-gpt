"""Added course_code to prereqs

Revision ID: 79353ed2db61
Revises: fd68b88e7018
Create Date: 2025-05-09 19:09:36.177927
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "79353ed2db61"
down_revision = "fd68b88e7018"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1) add as nullable
    op.add_column(
        "catalog_prerequisites",
        sa.Column("course_code", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_catalog_prerequisites_course_code",
        "catalog_prerequisites",
        ["course_code"],
        unique=False
    )

    # 2) backfill every existing row
    op.execute(
        """
        UPDATE catalog_prerequisites
        SET course_code = split_part(subject, ' - ', 1) || number
        """
    )

    # 3) alter to NOT NULL
    op.alter_column(
        "catalog_prerequisites",
        "course_code",
        existing_type=sa.String(),
        nullable=False
    )

def downgrade() -> None:
    op.drop_index("ix_catalog_prerequisites_course_code", table_name="catalog_prerequisites")
    op.drop_column("catalog_prerequisites", "course_code")
