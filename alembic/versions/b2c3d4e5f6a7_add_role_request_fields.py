"""add role request fields to users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('solicita_rol', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('hotel_id_solicitado', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'hotel_id_solicitado')
    op.drop_column('users', 'solicita_rol')
