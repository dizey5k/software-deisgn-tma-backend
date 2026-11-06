"""add user timezone

Revision ID: f937c50a20bd
Revises: e48c62a9f013
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f937c50a20bd"
down_revision: Union[str, Sequence[str], None] = "e48c62a9f013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone_name",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/Moscow",
        ),
    )
    op.alter_column("users", "timezone_name", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "timezone_name")
