from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from sqlalchemy import select,func
from app.models import AuditEvent,PurchaseOrder

D=Decimal
def ordered(c):
    p=c.post("/api/projects",json={"name":"Șantier recepții"}).json();s=c.post("/api/suppliers/local",json={"name":"Furnizor local","code":"LOCAL-REC","type":"LOCAL_MATERIAL_SUPPLIER"}).json();material=c.get("/api/catalog/materials").json()[0];q=c.post(f"/api/projects/{p['id']}/quotes",json={"supplier_id":s["id"],"quote_date":"2026-08-01T00:00:00+00:00","valid_until":"2027-08-01T00:00:00+00:00","transport_net":"100"}).json();q=c.post(f"/api/projects/{p['id']}/quotes/{q['id']}/items",json={"material_id":material["id"],"description":"Ciment","unit":"sac","quantity":"100","unit_price_net":"10.00","vat_rate":"21"}).json();c.post(f"/api/projects/{p['id']}/quotes/{q['id']}/status",json={"status":"ACTIVE"});o=c.post(f"/api/projects/{p['id']}/quotes/{q['id']}/purchase-order").json();c.post(f"/api/projects/{p['id']}/orders/{o['id']}/status",json={"status":"READY_TO_ORDER"});o=c.post(f"/api/projects/{p['id']}/orders/{o['id']}/status",json={"status":"ORDERED"}).json();return p,s,o
def delivery(c,p,o,received,damaged=0,rejected=0,price=None,confirm=False,note="",expected=100):
    item=o["items"][0];payload={"delivery_note_number":f"AV-{received}","transport_cost_actual":"120.00","items":[{"purchase_order_item_id":item["id"],"quantity_expected":str(expected),"quantity_received":str(received),"quantity_damaged":str(damaged),"quantity_rejected":str(rejected),"actual_unit_price_gross":price,"over_delivery_confirmed":confirm,"notes":note}]};return c.post(f"/api/projects/{p['id']}/orders/{o['id']}/deliveries",json=payload)

def test_partial_multiple_delivery_reconciliation_and_exports(authenticated_client,db):
    c=authenticated_client;p,s,o=ordered(c);d1=delivery(c,p,o,60);assert d1.status_code==201,d1.text;d1=d1.json();assert D(d1["items"][0]["quantity_missing"])==D("40");c.post(f"/api/projects/{p['id']}/deliveries/{d1['id']}/close",json={})
    assert db.get(PurchaseOrder,o["id"]).status=="PARTIALLY_DELIVERED"
    d2=delivery(c,p,o,38,expected=40);assert d2.status_code==201,d2.text;d2=d2.json();c.post(f"/api/projects/{p['id']}/deliveries/{d2['id']}/close",json={})
    rec=c.get(f"/api/projects/{p['id']}/orders/{o['id']}/reconciliation").json()["items"][0];assert D(rec["received_total"])==D("98") and D(rec["remaining_to_receive"])==D("2");assert db.get(PurchaseOrder,o["id"]).status=="PARTIALLY_DELIVERED"
    for ext in ("pdf","xlsx"):
        data=c.get(f"/api/projects/{p['id']}/deliveries/{d2['id']}/logistics-export.{ext}").content
        assert data.startswith(b"%PDF-1.4") if ext=="pdf" else ZipFile(BytesIO(data)).testzip() is None

def test_damage_rejection_price_variance_and_issue_resolution(authenticated_client,db):
    c=authenticated_client;p,s,o=ordered(c);r=delivery(c,p,o,50,3,2,"13.50");assert r.status_code==201;r=r.json();item=r["items"][0];assert D(item["quantity_accepted"])==D("45") and item["value_source"]=="ACTUAL_DELIVERY_PRICE" and D(item["received_value_gross"])==D("607.5");types={x["issue_type"] for x in r["issues"]};assert {"MISSING","DAMAGED","PRICE_DIFFERENCE"}<=types
    issue=r["issues"][0];resolved=c.post(f"/api/projects/{p['id']}/delivery-issues/{issue['id']}/status",json={"status":"RESOLVED","resolution_notes":"Clarificat"});assert resolved.json()["status"]=="RESOLVED";assert db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action=="ISSUE_RESOLVED"))==1

def test_overdelivery_validation_and_closed_immutability(authenticated_client):
    c=authenticated_client;p,s,o=ordered(c);assert delivery(c,p,o,101).status_code==422;ok=delivery(c,p,o,101,confirm=True,note="Furnizorul a livrat un sac în plus");assert ok.status_code==201;d=ok.json();c.post(f"/api/projects/{p['id']}/deliveries/{d['id']}/close",json={"accept_discrepancy":True});assert c.put(f"/api/projects/{p['id']}/deliveries/{d['id']}",json={"notes":"modificare"}).status_code==409

def test_return_flow_refund_history_and_immutability(authenticated_client):
    c=authenticated_client;p,s,o=ordered(c);d=delivery(c,p,o,100).json();c.post(f"/api/projects/{p['id']}/deliveries/{d['id']}/close",json={});ret=c.post(f"/api/projects/{p['id']}/returns",json={"supplier_id":s["id"],"delivery_id":d["id"],"purchase_order_id":o["id"],"return_number":"RET-001","reason":"DAMAGED","items":[{"delivery_item_id":d["items"][0]["id"],"quantity":"2","expected_refund_gross":"24.20"}]}).json()
    for status in ("REQUESTED","ACCEPTED","SENT","REFUNDED","CLOSED"):
        payload={"status":status};
        if status=="REFUNDED":payload["refund_amount_gross"]="24.20"
        response=c.post(f"/api/projects/{p['id']}/returns/{ret['id']}/status",json=payload);assert response.status_code==200,response.text;ret=response.json()
    assert D(ret["refund_amount_gross"])==D("24.20");rec=c.get(f"/api/projects/{p['id']}/orders/{o['id']}/reconciliation").json()["items"][0];assert D(rec["returned_total"])==D("2") and D(rec["accepted_total"])==D("100")
    assert c.post(f"/api/projects/{p['id']}/returns/{ret['id']}/status",json={"status":"REQUESTED"}).status_code==409
    assert c.get(f"/api/projects/{p['id']}/returns/{ret['id']}/logistics-export.pdf").content.startswith(b"%PDF-1.4");book=c.get(f"/api/projects/{p['id']}/returns/{ret['id']}/logistics-export.xlsx").content;assert ZipFile(BytesIO(book)).testzip() is None

def test_decimal_precision_and_attachment_security(authenticated_client,monkeypatch,tmp_path):
    from dataclasses import replace
    from app.config import settings
    monkeypatch.setattr("app.logistics_api.settings",replace(settings,data_root=str(tmp_path)))
    c=authenticated_client;p,s,o=ordered(c);d=delivery(c,p,o,"1.123456",price="12.3456").json();assert D(d["items"][0]["received_value_gross"])==D("13.8697383936")
    bad=c.post(f"/api/projects/{p['id']}/deliveries/{d['id']}/attachments",files={"file":("virus.exe",b"MZ","application/octet-stream")});assert bad.status_code==422
    good=c.post(f"/api/projects/{p['id']}/deliveries/{d['id']}/attachments",files={"file":("aviz.pdf",b"%PDF-1.4 document","application/pdf")});assert good.status_code==201
