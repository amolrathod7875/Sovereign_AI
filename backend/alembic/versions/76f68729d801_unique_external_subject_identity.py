"""unique_external_subject_identity

Revision ID: 76f68729d801
Revises: a1b2c3d4e5f6
Create Date: 2026-10-04 09:09:36.224641

A1A: enforce uniqueness for non-null OIDC external_subject values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76f68729d801'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.create_index(
            "uq_users_external_subject",
            ["external_subject"],
            unique=True,
            postgresql_where=sa.text("external_subject IS NOT NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("uq_users_external_subject", postgresql_where=sa.text("external_subject IS NOT NULL"))
