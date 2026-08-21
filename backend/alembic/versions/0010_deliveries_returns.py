"""purchase deliveries issues and material returns

Revision ID: 0010_deliveries_returns
Revises: 0009_quotes_orders
"""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision="0010_deliveries_returns";down_revision="0009_quotes_orders";branch_labels=None;depends_on=None
TABLES=["purchase_deliveries","delivery_items","delivery_issues","material_returns","material_return_items"]

def upgrade():
    bind=op.get_bind()
    for name in TABLES:Base.metadata.tables[name].create(bind,checkfirst=True)

def downgrade():
    for name in reversed(TABLES):op.drop_table(name)
