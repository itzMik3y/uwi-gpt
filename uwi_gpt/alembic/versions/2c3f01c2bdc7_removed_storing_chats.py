"""Removed storing chats 

Revision ID: 2c3f01c2bdc7
Revises: 7b5e51457ea6
Create Date: 2025-05-11 21:17:44.778283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2c3f01c2bdc7'
down_revision: Union[str, None] = '7b5e51457ea6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # drop the dependent table first
    op.drop_table('chat_messages')
    op.drop_table('chats')


def downgrade() -> None:
    # recreate chats before chat_messages…
    op.create_table(
        'chats',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='chats_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='chats_pkey')
    )
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('role',
                  postgresql.ENUM('user', 'assistant', 'system', name='role_enum'),
                  nullable=False),
        sa.Column('content', sa.TEXT(), nullable=False),
        sa.Column('timestamp', postgresql.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], name='chat_messages_chat_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='chat_messages_pkey')
    )
