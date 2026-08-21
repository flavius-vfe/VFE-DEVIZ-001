from datetime import datetime,timezone,timedelta
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
import pytest
from sqlalchemy import select,func
from app.commercial import line_calculation,quote_calculation,validity,validate_attachment,validate_signature
from app.commercial_exports import quote_pdf,quote_xlsx,order_pdf,order_xlsx
from app.models import SupplierQuote,PurchaseOrder,PurchaseOrderSequence,AuditEvent
from app.procurement import Candidate,Delivery,optimize
D=Decimal

def test_line_discount_vat_and_decimal_precision():
    x=line_calculation("3.333333","4.2000","21","PERCENT","5")
    assert x=={"unit_price_gross":D("5.08"),"discount_net":D("0.70"),"line_total_net":D("13.30"),"line_vat":D("2.79"),"line_total_gross":D("16.09")}

def test_discount_order_percentage_then_fixed_then_transport_vat():
    line={"line_total_net":D("100"),"line_vat":D("21"),"discount_net":D("0")}
    out=quote_calculation([line],[{"discount_type":"PERCENT","value":"10"},{"discount_type":"FIXED_AMOUNT","value":"5"}],transport_net="10")
    assert out["discount_total_net"]==D("15.00") and out["vat_total"]==D("19.95") and out["total_gross"]==D("114.95")

def test_concrete_additional_costs_separate():
    line={"line_total_net":D("100"),"line_vat":D("21"),"discount_net":D("0")}
    out=quote_calculation([line],transport_net=10,pump_fixed_cost=20,pump_hourly_cost=5,pump_hours=2,waiting_cost=3,other_cost=2)
    assert out["extras_net"]==D("45.00") and out["total_gross"]==D("175.45")

def test_quote_validity_states():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert validity(now-timedelta(seconds=1),now)=="EXPIRED"
    assert validity(now+timedelta(days=2),now)=="EXPIRING_SOON"
    assert validity(now+timedelta(days=10),now)=="VALID"

def candidate(sid,code,price):return Candidate(1,sid,code,sid,f"S{sid}",code,"/oferta",D("100"),"kg",D("1"),"kg",D(str(price)),datetime.now(timezone.utc),"IN_STOCK")
def test_local_negotiated_landed_cost_beats_cheaper_shelf_price():
    # Retail: 4.00/kg + transport 150; local: 4.50/kg + transport 20.
    out=optimize([candidate(1,"DEDEMAN",4),candidate(2,"LOCAL",4.5)],{1:Delivery(1,D("150")),2:Delivery(2,D("20"))})
    assert out["items"][0]["supplier_code"]=="LOCAL" and out["landed_total_gross"]==D("470.00")
def test_five_percent_negotiated_discount_changes_winner():
    base=quote_calculation([{"line_total_net":D("100"),"line_vat":D("21"),"discount_net":0}],[{"discount_type":"PERCENT","value":"5"}])
    assert base["total_gross"]==D("114.95") and base["total_gross"]<D("121")

@pytest.mark.parametrize("name,mime",[("oferta.pdf","application/pdf"),("foto.JPG","image/jpeg"),("calcul.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
def test_attachment_validation(name,mime):assert validate_attachment(name,mime,100)
def test_attachment_rejects_mime_size_and_execution():
    for args in [("x.exe","application/octet-stream",2),("x.pdf","text/html",2),("x.pdf","application/pdf",20_000_000)]:
        with pytest.raises(ValueError):validate_attachment(*args)
    with pytest.raises(ValueError):validate_signature(".pdf",b"<script>")

def create_project_supplier(client):
    project=client.post("/api/projects",json={"name":"Casă ofertată"}).json()
    supplier=client.post("/api/suppliers/local",json={"name":"Oțel Local","code":"OTEL_LOCAL","type":"LOCAL_MATERIAL_SUPPLIER","phone":"0700000000","locality":"Piatra-Neamț","county":"Neamț"}).json()
    return project,supplier

def test_quote_to_order_snapshot_status_and_exports(authenticated_client,db):
    c=authenticated_client;project,supplier=create_project_supplier(c);material=c.get("/api/catalog/materials").json()[0]
    q=c.post(f"/api/projects/{project['id']}/quotes",json={"supplier_id":supplier["id"],"quote_number":"OF-10","quote_date":"2026-08-21T00:00:00+00:00","valid_until":"2027-08-21T00:00:00+00:00","transport_net":"50","conditions":{"avans_percent":"20"}});assert q.status_code==201,q.text;q=q.json()
    q=c.post(f"/api/projects/{project['id']}/quotes/{q['id']}/items",json={"material_id":material["id"],"description":"Fier beton BST500 Ø12","unit":"kg","quantity":"1000","unit_price_net":"4.20","vat_rate":"21","line_discount_type":"PERCENT","line_discount_value":"2","attributes":{"diameter_mm":"12","bar_length_m":"12","steel_grade":"B500C"}}).json()
    q=c.post(f"/api/projects/{project['id']}/quotes/{q['id']}/discounts",json={"discount_type":"PERCENT","value":"5","description":"Volum"}).json();assert D(q["discount_total_net"])>0
    c.post(f"/api/projects/{project['id']}/quotes/{q['id']}/status",json={"status":"ACTIVE"})
    order=c.post(f"/api/projects/{project['id']}/quotes/{q['id']}/purchase-order");assert order.status_code==201,order.text;order=order.json();snapshot=order["total_gross"]
    c.put(f"/api/projects/{project['id']}/quotes/{q['id']}",json={"transport_net":"999"})
    assert c.get(f"/api/projects/{project['id']}/orders/{order['id']}").json()["total_gross"]==snapshot
    assert c.post(f"/api/projects/{project['id']}/orders/{order['id']}/status",json={"status":"READY_TO_ORDER"}).status_code==200
    assert c.post(f"/api/projects/{project['id']}/orders/{order['id']}/status",json={"status":"ORDERED"}).status_code==200
    assert c.put(f"/api/projects/{project['id']}/orders/{order['id']}",json={"notes":"schimbare"}).status_code==409
    for kind in ("quotes","orders"):
        entity=q["id"] if kind=="quotes" else order["id"]
        assert c.get(f"/api/projects/{project['id']}/{kind}/{entity}/export.pdf").content.startswith(b"%PDF-1.4")
        data=c.get(f"/api/projects/{project['id']}/{kind}/{entity}/export.xlsx").content;assert ZipFile(BytesIO(data)).testzip() is None
    assert db.scalar(select(func.count(AuditEvent.id)))>=5

def test_expired_quote_cannot_create_order(authenticated_client):
    c=authenticated_client;p,s=create_project_supplier(c);q=c.post(f"/api/projects/{p['id']}/quotes",json={"supplier_id":s["id"],"quote_date":"2020-01-01T00:00:00+00:00","valid_until":"2020-01-02T00:00:00+00:00"}).json()
    assert c.post(f"/api/projects/{p['id']}/quotes/{q['id']}/purchase-order").status_code==409

def test_order_number_sequence_unique(authenticated_client,db):
    c=authenticated_client;p,s=create_project_supplier(c);numbers=[]
    for n in range(2):
        q=c.post(f"/api/projects/{p['id']}/quotes",json={"supplier_id":s["id"],"quote_number":str(n),"quote_date":"2026-01-01T00:00:00+00:00","valid_until":"2027-01-01T00:00:00+00:00"}).json();numbers.append(c.post(f"/api/projects/{p['id']}/quotes/{q['id']}/purchase-order").json()["order_number"])
    assert len(set(numbers))==2 and numbers[0].endswith("0001") and numbers[1].endswith("0002")

def test_export_payload_contains_required_data():
    q={"quote_number":"Q","supplier_name":"Local","subtotal_net":"10","discount_total_net":"1","transport_net":"2","vat_total":"2.31","total_gross":"13.31","items":[{"description":"Beton C25/30","supplier_sku":None,"quantity":"1","unit":"m3","unit_price_net":"10","vat_rate":"21","line_total_gross":"12.10"}]}
    qbook=ZipFile(BytesIO(quote_xlsx(q)));assert b"OFERTA FURNIZOR" in quote_pdf(q) and b"Beton C25/30" in qbook.read("xl/worksheets/sheet2.xml")
    o={"project_name":"Casă","supplier_name":"Beton local","order_number":"PO-2026-0001","delivery_address":"Ceahlău, Neamț","subtotal_net":"10","discount_total":"0","transport_cost":"0","vat_total":"2.1","total_gross":"12.1","items":[{"description":"Beton C25/30","sku":None,"quantity":"1","unit":"m3","unit_price_net":"10","discount_net":"0","line_total_gross":"12.1"}]}
    obook=ZipFile(BytesIO(order_xlsx(o)));assert b"COMANDA MATERIALE" in order_pdf(o) and b"PO-2026-0001" in obook.read("xl/worksheets/sheet1.xml")
