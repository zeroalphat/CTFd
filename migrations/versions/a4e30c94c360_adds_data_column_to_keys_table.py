"""Add data column to keys table

Revision ID: a4e30c94c360
Revises: 87733981ca0e
Create Date: 2017-02-13 21:43:46.929248

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4e30c94c360'
down_revision = '87733981ca0e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('keys', sa.Column('data', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('keys', 'data')
    # ### end Alembic commands ###
