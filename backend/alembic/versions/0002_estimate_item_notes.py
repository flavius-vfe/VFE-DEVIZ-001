"""add estimate item notes

Revision ID: 0002_estimate_item_notes
Revises: 0001_initial_schema
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_estimate_item_notes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("estimate_items", sa.Column("notes", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("estimate_items", "notes")
