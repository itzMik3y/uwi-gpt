"""merge branches

Revision ID: 95f556a6b3eb
Revises: 24eadc7fdacc, f77b2ef207b8
Create Date: 2025-05-11 16:40:13.048863

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95f556a6b3eb'
down_revision: Union[str, None] = ('24eadc7fdacc', 'f77b2ef207b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
