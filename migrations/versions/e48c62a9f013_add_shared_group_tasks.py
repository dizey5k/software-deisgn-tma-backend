"""add shared group tasks and memberships

Revision ID: e48c62a9f013
Revises: cbd402d1106c
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e48c62a9f013"
down_revision: Union[str, Sequence[str], None] = "cbd402d1106c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "group_memberships",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )
    op.alter_column("tasks", "is_shared", server_default=None)


def downgrade() -> None:
    op.drop_table("group_memberships")
    op.drop_column("tasks", "is_shared")
