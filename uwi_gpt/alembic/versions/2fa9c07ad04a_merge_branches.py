"""Merge branches

Revision ID: 2fa9c07ad04a
Revises: 4ed2cbb4b2da, 5af77cfda370
Create Date: 2025-05-01 02:47:53.081084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2fa9c07ad04a'
down_revision: Union[str, None] = ('4ed2cbb4b2da', '5af77cfda370')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
