"""merge branches

Revision ID: b910d5ba07c4
Revises: 2c3f01c2bdc7, 2f074bfcbb6f
Create Date: 2025-05-13 07:55:11.911993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b910d5ba07c4'
down_revision: Union[str, None] = ('2c3f01c2bdc7', '2f074bfcbb6f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
