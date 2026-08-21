from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Supplier, SupplierLocation

DATA={
 "DEDEMAN":dict(name="Dedeman",website="https://www.dedeman.ro",location=("DEDEMAN_PIATRA_NEAMT","Dedeman Piatra Neamț","Str. Dumbravei nr. 29","Dumbrava Roșie","Neamț")),
 "MATHAUS":dict(name="MatHaus",website="https://mathaus.ro",location=("ARABESQUE_PIATRA_NEAMT","Arabesque Piatra-Neamț",None,"Piatra-Neamț","Neamț")),
 "LEROY_MERLIN":dict(name="Leroy Merlin",website="https://www.leroymerlin.ro",location=("LEROY_BACAU","Leroy Merlin Bacău",None,"Bacău","Bacău")),
 "HORNBACH":dict(name="Hornbach",website="https://www.hornbach.ro",location=("HORNBACH_ONLINE_REGIONAL","Hornbach online/regional",None,None,None)),
}
def seed_suppliers(db:Session):
    for code,data in DATA.items():
        row=db.scalar(select(Supplier).where(Supplier.code==code)) or Supplier(code=code,name=data["name"],type="RETAILER",website=data["website"],active=True)
        db.add(row); db.flush(); lc,name,address,locality,county=data["location"]
        loc=db.scalar(select(SupplierLocation).where(SupplierLocation.supplier_id==row.id,SupplierLocation.code==lc)) or SupplierLocation(supplier_id=row.id,code=lc,name=name)
        loc.address=address; loc.locality=locality; loc.county=county; loc.preferred=True; loc.active=True; db.add(loc)
    db.commit()
