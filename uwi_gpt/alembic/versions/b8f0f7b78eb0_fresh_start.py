"""Fresh start

Revision ID: b8f0f7b78eb0
Revises: 7a2dc406e221
Create Date: 2025-04-17 19:29:34.541103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8f0f7b78eb0'
down_revision: Union[str, None] = '7a2dc406e221'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
