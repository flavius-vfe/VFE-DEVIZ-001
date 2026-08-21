"""supplier quotes discounts and purchase orders

Revision ID: 0009_quotes_orders
Revises: 0008_leroy_hornbach
"""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models  # noqa: F401

revision="0009_quotes_orders";down_revision="0008_leroy_hornbach";branch_labels=None;depends_on=None
TABLES=["supplier_quotes","supplier_quote_items","discounts","attachments","purchase_orders","purchase_order_items","purchase_order_sequences","audit_events"]

def upgrade():
    for column in [sa.Column("phone",sa.String(60)),sa.Column("email",sa.String(255)),sa.Column("address",sa.Text()),sa.Column("locality",sa.String(160)),sa.Column("county",sa.String(160))]:op.add_column("suppliers",column)
    op.add_column("procurement_plan_items",sa.Column("procurement_status",sa.String(30),nullable=False,server_default="NOT_ORDERED"))
    bind=op.get_bind()
    for name in TABLES:Base.metadata.tables[name].create(bind,checkfirst=True)
    with op.batch_alter_table("procurement_plan_items") as batch:
        batch.add_column(sa.Column("quote_item_id",sa.Integer(),sa.ForeignKey("supplier_quote_items.id",name="fk_procurement_quote_item")))
        batch.alter_column("supplier_product_id",existing_type=sa.Integer(),nullable=True)

def downgrade():
    for name in reversed(TABLES):op.drop_table(name)
    op.drop_column("procurement_plan_items","quote_item_id");op.drop_column("procurement_plan_items","procurement_status")
    for name in ["county","locality","address","email","phone"]:op.drop_column("suppliers",name)
