"""geometry quantity engine

Revision ID: 0004_geometry_engine
Revises: 0003_cost_estimation
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_geometry_engine"
down_revision = "0003_cost_estimation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("geometry_calculations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estimate_item_id", sa.Integer(), sa.ForeignKey("estimate_items.id", ondelete="SET NULL")),
        sa.Column("parent_calculation_id", sa.Integer(), sa.ForeignKey("geometry_calculations.id", ondelete="SET NULL")),
        sa.Column("geometry_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("selected_result", sa.String(80), nullable=False),
        sa.Column("calculated_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("calculated_unit", sa.String(20), nullable=False),
        sa.Column("waste_percent", sa.Numeric(7, 3), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("geometry_estimate_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("geometry_calculation_id", sa.Integer(), sa.ForeignKey("geometry_calculations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estimate_item_id", sa.Integer(), sa.ForeignKey("estimate_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_key", sa.String(80), nullable=False),
        sa.Column("waste_percent", sa.Numeric(7, 3), nullable=False),
        sa.UniqueConstraint("geometry_calculation_id", "estimate_item_id", "result_key", name="uq_geometry_item_result"),
    )
    op.create_table("mesh_catalogue_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("wire_diameter_mm", sa.Numeric(8, 3), nullable=False),
        sa.Column("spacing_x_mm", sa.Numeric(10, 3), nullable=False),
        sa.Column("spacing_y_mm", sa.Numeric(10, 3), nullable=False),
        sa.Column("sheet_length_m", sa.Numeric(12, 4), nullable=False),
        sa.Column("sheet_width_m", sa.Numeric(12, 4), nullable=False),
        sa.Column("sheet_area_m2", sa.Numeric(18, 6), nullable=False),
        sa.Column("weight_kg_per_sheet", sa.Numeric(18, 4), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

def downgrade() -> None:
    op.drop_table("mesh_catalogue_items")
    op.drop_table("geometry_estimate_links")
    op.drop_table("geometry_calculations")
