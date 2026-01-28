"""create mcp_idempotency table

Revision ID: 9276b1d33386
Revises: 
Create Date: 2026-01-27 16:37:11.288459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9276b1d33386'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'mcp_idempotency',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('principal_id', sa.String(), nullable=False),
        sa.Column('request_digest', sa.String(), nullable=False),
        sa.Column('tool_effect_id', sa.String(), nullable=True),
        sa.Column('tool_effect_digest', sa.String(), nullable=True),
        sa.Column('tool_effect_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('server_id', 'tool_name', 'idempotency_key', 'principal_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('mcp_idempotency')

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9276b1d33386'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'mcp_idempotency',
        sa.Column('server_id', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('tool_effect_id', sa.String(), nullable=True),
        sa.Column('tool_effect_digest', sa.String(), nullable=True),
        sa.Column('tool_effect_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('server_id', 'tool_name', 'idempotency_key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
