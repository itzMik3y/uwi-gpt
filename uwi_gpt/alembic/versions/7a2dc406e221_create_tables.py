"""create tables

Revision ID: 7a2dc406e221
Revises: 
Create Date: 2025-04-15 21:50:22.133640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a2dc406e221'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('courses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fullname', sa.String(), nullable=True),
    sa.Column('shortname', sa.String(), nullable=True),
    sa.Column('idnumber', sa.String(), nullable=True),
    sa.Column('summary', sa.String(), nullable=True),
    sa.Column('summaryformat', sa.Integer(), nullable=True),
    sa.Column('startdate', sa.Integer(), nullable=True),
    sa.Column('enddate', sa.Integer(), nullable=True),
    sa.Column('visible', sa.Boolean(), nullable=True),
    sa.Column('showactivitydates', sa.Boolean(), nullable=True),
    sa.Column('showcompletionconditions', sa.Boolean(), nullable=True),
    sa.Column('fullnamedisplay', sa.String(), nullable=True),
    sa.Column('viewurl', sa.String(), nullable=True),
    sa.Column('coursecategory', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('firstname', sa.String(), nullable=False),
    sa.Column('lastname', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('student_id', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('terms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('term_code', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('semester_gpa', sa.Float(), nullable=True),
    sa.Column('cumulative_gpa', sa.Float(), nullable=True),
    sa.Column('degree_gpa', sa.Float(), nullable=True),
    sa.Column('credits_earned_to_date', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('enrolled_courses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('course_id', sa.Integer(), nullable=True),
    sa.Column('term_id', sa.Integer(), nullable=True),
    sa.Column('course_code', sa.String(), nullable=True),
    sa.Column('course_title', sa.String(), nullable=True),
    sa.Column('credit_hours', sa.Float(), nullable=True),
    sa.Column('grade_earned', sa.String(), nullable=True),
    sa.Column('whatif_grade', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.ForeignKeyConstraint(['term_id'], ['terms.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('enrolled_courses')
    op.drop_table('terms')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('courses')
    # ### end Alembic commands ###
