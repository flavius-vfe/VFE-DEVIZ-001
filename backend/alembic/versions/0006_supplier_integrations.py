"""supplier integrations

Revision ID: 0006_supplier_integrations
Revises: 0005_standard_catalogue
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_supplier_integrations"
down_revision = "0005_standard_catalogue"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("projects", sa.Column("material_price_strategy", sa.String(40), nullable=False, server_default="MANUAL"))
    op.add_column("suppliers", sa.Column("code", sa.String(40), nullable=True))
    for name, column in [
        ("requests_per_minute", sa.Column("requests_per_minute", sa.Integer(), nullable=False, server_default="10")),
        ("request_timeout", sa.Column("request_timeout", sa.Integer(), nullable=False, server_default="15")),
        ("retry_count", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="2")),
        ("backoff_seconds", sa.Column("backoff_seconds", sa.Integer(), nullable=False, server_default="5")),
        ("requests", sa.Column("requests", sa.Integer(), nullable=False, server_default="0")),
        ("successes", sa.Column("successes", sa.Integer(), nullable=False, server_default="0")),
        ("failures", sa.Column("failures", sa.Integer(), nullable=False, server_default="0")),
        ("parse_failures", sa.Column("parse_failures", sa.Integer(), nullable=False, server_default="0")),
        ("last_success", sa.Column("last_success", sa.DateTime(timezone=True))),
        ("last_error", sa.Column("last_error", sa.Text())),
    ]: op.add_column("suppliers", column)
    op.execute("UPDATE suppliers SET code = UPPER(REPLACE(name, ' ', '_')) WHERE code IS NULL")
    with op.batch_alter_table("suppliers") as batch:
        batch.alter_column("code", nullable=False)
    op.create_index("ix_suppliers_code_unique", "suppliers", ["code"], unique=True)
    for column in [sa.Column("code", sa.String(80), nullable=True), sa.Column("latitude", sa.Numeric(10,7)), sa.Column("longitude", sa.Numeric(10,7)), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())]: op.add_column("supplier_locations", column)
    op.execute("UPDATE supplier_locations SET code = 'LOC_' || CAST(id AS VARCHAR) WHERE code IS NULL")
    op.execute("UPDATE supplier_locations SET code='DEDEMAN_PIATRA_NEAMT' WHERE name='Dedeman Piatra Neamț'")
    op.execute("UPDATE supplier_locations SET code='ARABESQUE_PIATRA_NEAMT' WHERE name='Arabesque Piatra-Neamț'")
    with op.batch_alter_table("supplier_locations") as batch:
        batch.alter_column("code", nullable=False)
    with op.batch_alter_table("supplier_products") as batch:
        batch.add_column(sa.Column("supplier_location_id", sa.Integer(), sa.ForeignKey("supplier_locations.id", name="fk_supplier_product_location")))
        batch.add_column(sa.Column("category", sa.String(200)))
        batch.add_column(sa.Column("image_url", sa.Text()))
        batch.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE supplier_products SET first_seen_at = COALESCE(last_seen_at, CURRENT_TIMESTAMP)")
    with op.batch_alter_table("supplier_products") as batch:
        batch.alter_column("first_seen_at", nullable=False)
    op.rename_table("product_matches", "material_product_matches")
    op.add_column("material_product_matches", sa.Column("match_status", sa.String(20), nullable=False, server_default="AUTO"))
    op.add_column("material_product_matches", sa.Column("approved_at", sa.DateTime(timezone=True)))
    with op.batch_alter_table("material_product_matches") as batch:
        batch.alter_column("matching_notes", new_column_name="notes")
    op.add_column("price_observations", sa.Column("vat_amount", sa.Numeric(18,4)))
    op.add_column("price_observations", sa.Column("stock_text", sa.Text()))
    op.create_table("supplier_refresh_jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False), sa.Column("supplier_product_id", sa.Integer(), sa.ForeignKey("supplier_products.id", ondelete="CASCADE")), sa.Column("job_type", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("error_message", sa.Text()))
    op.create_table("delivery_quotes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False), sa.Column("supplier_location_id", sa.Integer(), sa.ForeignKey("supplier_locations.id")), sa.Column("destination_locality", sa.String(160), nullable=False), sa.Column("destination_county", sa.String(160), nullable=False), sa.Column("cost_gross", sa.Numeric(18,2)), sa.Column("source", sa.String(20), nullable=False), sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False), sa.Column("notes", sa.Text()))
    for column in [sa.Column("supplier_product_id", sa.Integer()), sa.Column("product_name", sa.String(500)), sa.Column("package_quantity", sa.Numeric(18,6)), sa.Column("package_unit", sa.String(20)), sa.Column("purchase_quantity", sa.Numeric(18,6)), sa.Column("packages_to_buy", sa.Integer())]: op.add_column("estimate_snapshot_lines", column)
    op.execute("INSERT INTO suppliers (code,name,type,website,active,requests_per_minute,request_timeout,retry_count,backoff_seconds,requests,successes,failures,parse_failures) SELECT 'DEDEMAN','Dedeman','RETAILER','https://www.dedeman.ro',true,10,15,2,5,0,0,0,0 WHERE NOT EXISTS (SELECT 1 FROM suppliers WHERE code='DEDEMAN')")
    op.execute("INSERT INTO suppliers (code,name,type,website,active,requests_per_minute,request_timeout,retry_count,backoff_seconds,requests,successes,failures,parse_failures) SELECT 'MATHAUS','MatHaus','RETAILER','https://mathaus.ro',true,10,15,2,5,0,0,0,0 WHERE NOT EXISTS (SELECT 1 FROM suppliers WHERE code='MATHAUS')")
    op.execute("INSERT INTO supplier_locations (supplier_id,code,name,address,locality,county,preferred,active) SELECT id,'DEDEMAN_PIATRA_NEAMT','Dedeman Piatra Neamț','Str. Dumbravei nr. 29','Dumbrava Roșie','Neamț',true,true FROM suppliers WHERE code='DEDEMAN' AND NOT EXISTS (SELECT 1 FROM supplier_locations WHERE code='DEDEMAN_PIATRA_NEAMT')")
    op.execute("INSERT INTO supplier_locations (supplier_id,code,name,locality,county,preferred,active) SELECT id,'ARABESQUE_PIATRA_NEAMT','Arabesque Piatra-Neamț','Piatra-Neamț','Neamț',true,true FROM suppliers WHERE code='MATHAUS' AND NOT EXISTS (SELECT 1 FROM supplier_locations WHERE code='ARABESQUE_PIATRA_NEAMT')")

def downgrade() -> None:
    for name in ["packages_to_buy","purchase_quantity","package_unit","package_quantity","product_name","supplier_product_id"]: op.drop_column("estimate_snapshot_lines", name)
    op.drop_table("delivery_quotes"); op.drop_table("supplier_refresh_jobs")
    op.drop_column("price_observations", "stock_text"); op.drop_column("price_observations", "vat_amount")
    with op.batch_alter_table("material_product_matches") as batch:
        batch.alter_column("notes", new_column_name="matching_notes")
    op.drop_column("material_product_matches", "approved_at"); op.drop_column("material_product_matches", "match_status")
    op.rename_table("material_product_matches", "product_matches")
    for name in ["first_seen_at","image_url","category","supplier_location_id"]: op.drop_column("supplier_products", name)
    for name in ["active","longitude","latitude","code"]: op.drop_column("supplier_locations", name)
    op.drop_index("ix_suppliers_code_unique", table_name="suppliers")
    for name in ["last_error","last_success","parse_failures","failures","successes","requests","backoff_seconds","retry_count","request_timeout","requests_per_minute","code"]: op.drop_column("suppliers", name)
    op.drop_column("projects", "material_price_strategy")
