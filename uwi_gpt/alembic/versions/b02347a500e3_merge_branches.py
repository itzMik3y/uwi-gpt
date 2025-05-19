"""merge branches

Revision ID: b02347a500e3
Revises: 65e677843c26, b910d5ba07c4
Create Date: 2025-05-17 18:46:45.798486

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b02347a500e3'
down_revision: Union[str, None] = ('65e677843c26', 'b910d5ba07c4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
