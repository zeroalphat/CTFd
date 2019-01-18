"""Adding Hints and Unlocks tables

Revision ID: c7225db614c1
Revises: d6514ec92738
Create Date: 2017-03-23 01:31:43.940187

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7225db614c1'
down_revision = 'd6514ec92738'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('hints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Integer(), nullable=True),
    sa.Column('chal', sa.Integer(), nullable=True),
    sa.Column('hint', sa.Text(), nullable=True),
    sa.Column('cost', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['chal'], ['challenges.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('unlocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('teamid', sa.Integer(), nullable=True),
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.Column('itemid', sa.Integer(), nullable=True),
    sa.Column('model', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['teamid'], ['teams.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('unlocks')
    op.drop_table('hints')
    # ### end Alembic commands ###
