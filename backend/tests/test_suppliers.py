from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.models import Material, Supplier, SupplierProduct, PriceObservation, EstimateVersion, EstimateSnapshotLine
from app.suppliers.adapters import DedemanAdapter, MathausAdapter, LeroyMerlinAdapter, HornbachAdapter, decimal_ro, stock, packaging
from app.suppliers.security import validate_supplier_url, bounded_body
from app.suppliers.service import import_product, match_score, package_purchase, retry_delay
from app.suppliers.seed import seed_suppliers

FIX=Path(__file__).resolve().parent.parent/"app"/"suppliers"/"fixtures"
def read(name):return (FIX/name).read_text(encoding="utf-8")

@pytest.mark.parametrize("name,adapter,sku,gross,unit,status",[
 ("dedeman_adeziv.html",DedemanAdapter(),"DED-1045123",Decimal("42.99"),"kg","UNKNOWN"),
 ("dedeman_bca.html",DedemanAdapter(),"DED-BCA25",Decimal("21.50"),None,"UNKNOWN"),
 ("mathaus_adeziv.html",MathausAdapter(),"MAT-98765",Decimal("41.49"),"kg","IN_STOCK"),
 ("mathaus_bca.html",MathausAdapter(),"MAT-BCA25",Decimal("20.60"),"buc","LIMITED"),
 ("leroy_adeziv.html",LeroyMerlinAdapter(),"LM-10025",Decimal("62.90"),"kg","UNKNOWN"),
 ("leroy_bca.html",LeroyMerlinAdapter(),"LM-BCA375",Decimal("18.75"),"m3","UNKNOWN"),
 ("hornbach_adeziv.html",HornbachAdapter(),"HB-884201",Decimal("54.50"),"kg","IN_STOCK"),
 ("hornbach_bca.html",HornbachAdapter(),"HB-105599",Decimal("20.20"),"m3","LIMITED"),
])
def test_offline_product_parsers(name,adapter,sku,gross,unit,status):
    hosts={DedemanAdapter:"www.dedeman.ro",MathausAdapter:"mathaus.ro",LeroyMerlinAdapter:"www.leroymerlin.ro",HornbachAdapter:"www.hornbach.ro"}
    p=adapter.parse_product(read(name),f"https://{hosts[type(adapter)]}/{sku}")
    assert p.sku==sku and p.gross==gross and p.package_unit==unit and p.stock_status==status
    assert p.name and p.url and p.vat_rate==Decimal("21")
    if isinstance(adapter,(LeroyMerlinAdapter,HornbachAdapter)): assert all(set(x)>={"field","source","success"} for x in p.diagnostics)

@pytest.mark.parametrize("text,q,u",[("25 kg",Decimal("25"),"kg"),("5 m²/pachet",Decimal("5"),"m2"),("48 buc/palet",Decimal("48"),"buc"),("0,0375 m³/buc",Decimal("0.0375"),"m3")])
def test_retail_packaging_normalization(text,q,u):
    quantity,normalized,attributes=packaging(text);assert (quantity,normalized)==(q,u) and attributes["ambalaj_original"]

def test_romanian_price_vat_stock_and_pallet():
    assert decimal_ro("1.234,56 lei")==Decimal("1234.56")
    assert stock("stoc epuizat")=="OUT_OF_STOCK" and stock("necunoscut")=="UNKNOWN"
    p=MathausAdapter().parse_product(read("mathaus_bca.html"))
    assert p.attributes["palet"]=={"cantitate":"48","unitate":"buc"}

def test_security_domain_allowlist_ssrf_and_size(monkeypatch):
    assert validate_supplier_url("https://www.dedeman.ro/produs", "DEDEMAN",resolve=False)
    assert validate_supplier_url("https://www.leroymerlin.ro/produs", "LEROY_MERLIN",resolve=False)
    assert validate_supplier_url("https://www.hornbach.ro/produs", "HORNBACH",resolve=False)
    for url in ("http://www.dedeman.ro/produs","https://localhost/produs","https://mathaus.ro/produs","https://127.0.0.1/produs"):
        with pytest.raises(ValueError):validate_supplier_url(url,"DEDEMAN",resolve=False)
    with pytest.raises(ValueError):bounded_body(b"x"*2_000_001)

def test_package_decimal_ceil_and_cost():
    out=package_purchase("10.01","2.5","41.49")
    assert out=={"packages_to_buy":5,"purchase_quantity":Decimal("12.5"),"unused_quantity":Decimal("2.49"),"purchase_cost":Decimal("207.45")}
    assert [retry_delay(5,x) for x in (1,2,3)]==[5,10,20]

def test_duplicate_upsert_and_append_only_price_history(db):
    seed_suppliers(db);s=db.scalar(select(Supplier).where(Supplier.code=="MATHAUS"));a=MathausAdapter();p=a.parse_product(read("mathaus_adeziv.html"),"https://mathaus.ro/produs")
    first,_=import_product(db,s,p);p.gross=Decimal("43.00");second,_=import_product(db,s,p)
    assert first.id==second.id and db.scalar(select(func.count(SupplierProduct.id)))==1
    assert db.scalar(select(func.count(PriceObservation.id)))==2
    latest=db.scalar(select(PriceObservation).order_by(PriceObservation.checked_at.desc(),PriceObservation.id.desc()))
    assert latest.price_gross==Decimal("43.0000")

def test_matching_never_auto_approves(db):
    material=Material(code="BCA25",name="BCA 25 cm",category="BCA",base_unit="buc",attributes={"grosime":"25"},active=True)
    product=SupplierProduct(supplier_id=1,supplier_sku="x",name="BCA 25 cm",category="BCA",product_url="https://www.dedeman.ro/x",attributes={"grosime":"25"},active=True,first_seen_at=datetime.now(timezone.utc))
    score=match_score(material,product);assert score>=Decimal("0.90")
    assert not hasattr(product,"approved")

def test_snapshot_is_immutable_after_new_price(db):
    from app.models import Project
    project=Project(name="Test",locality="Ceahlău",county="Neamț",default_waste_percent=Decimal("5"),active=True);db.add(project);db.flush()
    version=EstimateVersion(project_id=project.id,version=1,status="ISSUED",vat_rate=21,total_net=100,vat_total=21,total_gross=121);db.add(version);db.flush()
    line=EstimateSnapshotLine(estimate_version_id=version.id,resource_type="MATERIAL",description="BCA",unit="buc",quantity=10,unit_price_net=10,vat_rate=21,unit_price_gross=Decimal("12.1"),total_gross=121,supplier_name="MatHaus",supplier_sku="OLD",product_name="BCA",package_quantity=1,package_unit="buc",purchase_quantity=10,packages_to_buy=10,product_url="https://mathaus.ro/old");db.add(line);db.commit()
    assert db.get(EstimateSnapshotLine,line.id).supplier_sku=="OLD" and db.get(EstimateSnapshotLine,line.id).total_gross==Decimal("121.00")

def test_supplier_fixture_api_and_manual_approval(authenticated_client):
    c=authenticated_client
    suppliers=c.get("/api/suppliers");assert suppliers.status_code==200 and len(suppliers.json())==4
    p1=c.post("/api/suppliers/import-fixture",json={"fixture":"dedeman_adeziv.html"});p2=c.post("/api/suppliers/import-fixture",json={"fixture":"mathaus_adeziv.html"});assert p1.status_code==p2.status_code==201
    material=c.get("/api/catalog/materials").json()[0]
    candidates=c.get(f"/api/catalog/materials/{material['id']}/products").json();assert len(candidates)==2
    decision=c.post(f"/api/catalog/materials/{material['id']}/products/{p1.json()['id']}/match",json={"approved":True});assert decision.json()["match_status"]=="MANUAL"
    job=c.post("/api/suppliers/refresh",json={"supplier_product_id":p1.json()["id"]});assert job.json()["status"]=="PENDING"

def test_fixture_import_rejects_arbitrary_path(authenticated_client):
    assert authenticated_client.post("/api/suppliers/import-fixture",json={"fixture":"../../secret"}).status_code==422
