"""Leroy Merlin and Hornbach suppliers

Revision ID: 0008_leroy_hornbach
Revises: 0007_procurement_landed_cost
"""
from alembic import op
import sqlalchemy as sa

revision="0008_leroy_hornbach"; down_revision="0007_procurement_landed_cost"; branch_labels=None; depends_on=None

def upgrade():
    op.add_column("suppliers", sa.Column("manual_imports", sa.Integer(), nullable=False, server_default="0"))
    bind=op.get_bind()
    suppliers=sa.table("suppliers",sa.column("id",sa.Integer),sa.column("code",sa.String),sa.column("name",sa.String),sa.column("type",sa.String),sa.column("website",sa.Text),sa.column("active",sa.Boolean))
    locations=sa.table("supplier_locations",sa.column("supplier_id",sa.Integer),sa.column("code",sa.String),sa.column("name",sa.String),sa.column("locality",sa.String),sa.column("county",sa.String),sa.column("preferred",sa.Boolean),sa.column("active",sa.Boolean))
    for code,name,website,location,locality,county in [
        ("LEROY_MERLIN","Leroy Merlin","https://www.leroymerlin.ro","LEROY_BACAU","Bacău","Bacău"),
        ("HORNBACH","Hornbach","https://www.hornbach.ro","HORNBACH_ONLINE_REGIONAL",None,None),
    ]:
        existing=bind.execute(sa.select(suppliers.c.id).where(suppliers.c.code==code)).scalar()
        if existing is None:
            bind.execute(suppliers.insert().values(code=code,name=name,type="RETAILER",website=website,active=True))
            existing=bind.execute(sa.select(suppliers.c.id).where(suppliers.c.code==code)).scalar_one()
        present=bind.execute(sa.select(locations.c.supplier_id).where(locations.c.supplier_id==existing,locations.c.code==location)).first()
        if not present: bind.execute(locations.insert().values(supplier_id=existing,code=location,name="Leroy Merlin Bacău" if code=="LEROY_MERLIN" else "Hornbach online/regional",locality=locality,county=county,preferred=True,active=True))

def downgrade():
    op.drop_column("suppliers","manual_imports")
