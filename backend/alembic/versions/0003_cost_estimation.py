"""cost estimation catalogues recipes and resource lines

Revision ID: 0003_cost_estimation
Revises: 0002_estimate_item_notes
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_cost_estimation"
down_revision = "0002_estimate_item_notes"
branch_labels = None
depends_on = None

def priced_resource_table(name: str) -> None:
    op.create_table(name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("rate_net", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(7, 3), nullable=False),
        sa.Column("rate_gross", sa.Numeric(18, 4), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

def upgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.alter_column("canonical_name", new_column_name="name", existing_type=sa.String(255), nullable=False)
        batch.add_column(sa.Column("code", sa.String(80), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
    op.execute("UPDATE materials SET code = 'MAT-' || id WHERE code IS NULL")
    with op.batch_alter_table("materials") as batch:
        batch.alter_column("code", existing_type=sa.String(80), nullable=False)
        batch.create_unique_constraint("uq_material_code", ["code"])

    priced_resource_table("labor_resources")
    priced_resource_table("equipment_resources")
    priced_resource_table("other_resources")
    with op.batch_alter_table("work_recipes") as batch:
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_work_recipes_project", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.add_column("recipe_resources", sa.Column("notes", sa.Text(), nullable=True))

    op.create_table("project_resource_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("unit_price_net", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(7, 3), nullable=False),
        sa.Column("unit_price_gross", sa.Numeric(18, 4), nullable=False),
        sa.UniqueConstraint("project_id", "resource_type", "resource_id", name="uq_project_resource_price"),
    )
    op.create_table("estimate_resource_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("estimate_item_id", sa.Integer(), sa.ForeignKey("estimate_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipe_resource_id", sa.Integer(), sa.ForeignKey("recipe_resources.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.Integer()),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("waste_percent", sa.Numeric(7, 3), nullable=False),
        sa.Column("unit_price_net", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(7, 3), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("unit_price_gross", sa.Numeric(18, 4), nullable=False),
        sa.Column("subtotal_net", sa.Numeric(18, 2), nullable=False),
        sa.Column("subtotal_gross", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text()),
    )

def downgrade() -> None:
    op.drop_table("estimate_resource_lines")
    op.drop_table("project_resource_prices")
    op.drop_column("recipe_resources", "notes")
    with op.batch_alter_table("work_recipes") as batch:
        batch.drop_constraint("fk_work_recipes_project", type_="foreignkey")
        batch.drop_column("project_id")
    op.drop_table("other_resources")
    op.drop_table("equipment_resources")
    op.drop_table("labor_resources")
    with op.batch_alter_table("materials") as batch:
        batch.drop_constraint("uq_material_code", type_="unique")
        batch.drop_column("description")
        batch.drop_column("code")
        batch.alter_column("name", new_column_name="canonical_name", existing_type=sa.String(255), nullable=False)
