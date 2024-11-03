"""Add status field to InvReport

Revision ID: 5e74329e7949
Revises: ab41ef220c3b
Create Date: 2024-10-08 10:46:10.666778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e74329e7949'
down_revision: Union[str, None] = 'ab41ef220c3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('product_invreport')
    op.add_column('invreport_items', sa.Column('current_srp', sa.Float(), nullable=True))
    op.alter_column('invreport_items', 'offtake',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Integer(),
               existing_nullable=True)
    op.add_column('invreports', sa.Column('status', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('invreports', 'status')
    op.alter_column('invreport_items', 'offtake',
               existing_type=sa.Integer(),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
    op.drop_column('invreport_items', 'current_srp')
    op.create_table('product_invreport',
    sa.Column('product_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('invreport_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['invreport_id'], ['invreports.id'], name='product_invreport_invreport_id_fkey'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name='product_invreport_product_id_fkey')
    )
    # ### end Alembic commands ###
