"""long_term_memory

Create the canonical durable memory layer tables:
  * conversation_memories
  * memory_provenance
  * memory_index_outbox

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-10-02 06:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_memories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("memory_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("source_conversation_id", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("supersedes_memory_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "conversation_id",
            "scope",
            "memory_type",
            "normalized_content",
            name="uq_memory_dedup",
        ),
        sa.Index("ix_conversation_memories_organization_id", "organization_id"),
        sa.Index("ix_conversation_memories_user_id", "user_id"),
        sa.Index("ix_conversation_memories_conversation_id", "conversation_id"),
        sa.Index("ix_conversation_memories_scope", "scope"),
        sa.Index("ix_conversation_memories_memory_type", "memory_type"),
        sa.Index("ix_conversation_memories_normalized_content", "normalized_content"),
        sa.Index("ix_conversation_memories_active", "active"),
    )

    op.create_table(
        "memory_provenance",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("memory_id", sa.String(), nullable=False),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("source_conversation_id", sa.String(), nullable=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["memory_id"], ["conversation_memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_id", "source_message_id", name="uq_memory_provenance_message"),
        sa.UniqueConstraint("memory_id", "source_conversation_id", name="uq_memory_provenance_conversation"),
        sa.Index("ix_memory_provenance_memory_id", "memory_id"),
        sa.Index("ix_memory_provenance_organization_id", "organization_id"),
        sa.Index("ix_memory_provenance_user_id", "user_id"),
    )

    op.create_table(
        "memory_index_outbox",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("memory_id", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["memory_id"], ["conversation_memories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_memory_index_outbox_memory_id", "memory_id"),
        sa.Index("ix_memory_index_outbox_status", "status"),
    )


def downgrade() -> None:
    op.drop_index("ix_memory_index_outbox_status", table_name="memory_index_outbox")
    op.drop_index("ix_memory_index_outbox_memory_id", table_name="memory_index_outbox")
    op.drop_table("memory_index_outbox")

    op.drop_index("ix_memory_provenance_user_id", table_name="memory_provenance")
    op.drop_index("ix_memory_provenance_organization_id", table_name="memory_provenance")
    op.drop_index("ix_memory_provenance_memory_id", table_name="memory_provenance")
    op.drop_constraint("uq_memory_provenance_conversation", "memory_provenance", type_="unique")
    op.drop_constraint("uq_memory_provenance_message", "memory_provenance", type_="unique")
    op.drop_table("memory_provenance")

    op.drop_index("ix_conversation_memories_active", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_normalized_content", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_memory_type", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_scope", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_conversation_id", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_user_id", table_name="conversation_memories")
    op.drop_index("ix_conversation_memories_organization_id", table_name="conversation_memories")
    op.drop_constraint("uq_memory_dedup", "conversation_memories", type_="unique")
    op.drop_table("conversation_memories")
