"""conversation_summary

Create the persistent rolling conversation summary table.

Revision ID: f1a2b3c4d5e6
Revises: e9cfda7e5b83
Create Date: 2026-10-01 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e9cfda7e5b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("summarized_through_sequence_no", sa.Integer(), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_conversation_summary"),
    )
    op.create_index(op.f("ix_conversation_summaries_conversation_id"), "conversation_summaries", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_conversation_summaries_updated_at"), "conversation_summaries", ["updated_at"], unique=False)
    op.create_index("ix_conversation_summaries_org_owner", "conversation_summaries", ["organization_id", "owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_conversation_summaries_org_owner", table_name="conversation_summaries")
    op.drop_index(op.f("ix_conversation_summaries_updated_at"), table_name="conversation_summaries")
    op.drop_index(op.f("ix_conversation_summaries_conversation_id"), table_name="conversation_summaries")
    op.drop_table("conversation_summaries")
