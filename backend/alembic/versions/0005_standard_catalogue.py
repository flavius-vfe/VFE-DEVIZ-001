"""standard Romanian work catalogue and pinned recipes

Revision ID: 0005_standard_catalogue
Revises: 0004_geometry_engine
"""
from alembic import op
import sqlalchemy as sa
revision="0005_standard_catalogue"; down_revision="0004_geometry_engine"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("work_categories",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("code",sa.String(20),nullable=False,unique=True),sa.Column("name",sa.String(160),nullable=False),sa.Column("sort_order",sa.Integer(),nullable=False))
    with op.batch_alter_table("estimate_items") as batch:
        batch.add_column(sa.Column("pinned_recipe_id",sa.Integer(),nullable=True))
        batch.create_foreign_key("fk_estimate_item_pinned_recipe","work_recipes",["pinned_recipe_id"],["id"],ondelete="SET NULL")
def downgrade():
    with op.batch_alter_table("estimate_items") as batch:
        batch.drop_constraint("fk_estimate_item_pinned_recipe",type_="foreignkey"); batch.drop_column("pinned_recipe_id")
    op.drop_table("work_categories")
