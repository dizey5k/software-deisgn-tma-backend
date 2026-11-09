"""add group chat title to memberships

Revision ID: c134a8e7d29f
Revises: f937c50a20bd
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c134a8e7d29f"
down_revision: Union[str, Sequence[str], None] = "f937c50a20bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_memberships",
        sa.Column("chat_title", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("group_memberships", "chat_title")
