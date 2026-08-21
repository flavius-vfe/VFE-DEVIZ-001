from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import re,uuid
from fastapi import APIRouter,Depends,HTTPException,Response,UploadFile,File,Form
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .deps import current_user
from .models import User,Project,Supplier,PurchaseOrder,PurchaseOrderItem,PurchaseDelivery,DeliveryItem,DeliveryIssue,MaterialReturn,MaterialReturnItem,Attachment,AuditEvent
from .commercial import dec,validate_attachment,validate_signature
from .config import settings
from .logistics_exports import delivery_pdf,delivery_xlsx,return_pdf,return_xlsx

router=APIRouter(prefix="/api")
DELIVERY_STATUSES={"EXPECTED","PARTIALLY_RECEIVED","RECEIVED","WITH_ISSUES","CLOSED","CANCELLED"}; ISSUE_TYPES={"MISSING","DAMAGED","WRONG_PRODUCT","WRONG_QUANTITY","PRICE_DIFFERENCE","QUALITY_PROBLEM","OTHER"}; RETURN_REASONS={"DAMAGED","EXCESS","WRONG_PRODUCT","NONCONFORMING","OTHER"}
def need(db,m,id,msg):
    x=db.get(m,id)
    if not x:raise HTTPException(404,msg)
    return x
def cols(x):return {c.name:(str(getattr(x,c.name)) if isinstance(getattr(x,c.name),Decimal) else getattr(x,c.name)) for c in x.__table__.columns}
def audit(db,entity,id,action,details=None):db.add(AuditEvent(entity_type=entity,entity_id=id,action=action,details=details or {}))
def parse_date(v):return datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else datetime.now(timezone.utc)
def previous_received(db,order_item_id,exclude=None):return sum((x.quantity_received for x in db.scalars(select(DeliveryItem).join(PurchaseDelivery).where(DeliveryItem.purchase_order_item_id==order_item_id,PurchaseDelivery.status!="CANCELLED",PurchaseDelivery.id!=exclude))),Decimal("0"))
def returned(db,order_item_id):return sum((x.quantity for x in db.scalars(select(MaterialReturnItem).join(MaterialReturn).join(DeliveryItem).where(DeliveryItem.purchase_order_item_id==order_item_id,MaterialReturn.status.not_in(["DRAFT","REJECTED"])))),Decimal("0"))
def reconciliation(db,order):
    result=[]
    for item in db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id==order.id)):
        rows=list(db.scalars(select(DeliveryItem).join(PurchaseDelivery).where(DeliveryItem.purchase_order_item_id==item.id,PurchaseDelivery.status!="CANCELLED")));received=sum((x.quantity_received for x in rows),Decimal("0"));accepted=sum((x.quantity_accepted for x in rows),Decimal("0"));damaged=sum((x.quantity_damaged for x in rows),Decimal("0"));rejected=sum((x.quantity_rejected for x in rows),Decimal("0"));ret=returned(db,item.id);remaining=max(item.quantity-received,Decimal("0"));result.append({"purchase_order_item_id":item.id,"description":item.description,"unit":item.unit,"ordered":str(item.quantity),"received_total":str(received),"accepted_total":str(accepted),"damaged_total":str(damaged),"rejected_total":str(rejected),"returned_total":str(ret),"remaining_to_receive":str(remaining),"progress_percent":str(min(Decimal("100"),received*100/item.quantity) if item.quantity else 100)})
    return result
def sync_order(db,order,accept_discrepancy=False):
    rows=reconciliation(db,order);received=sum(Decimal(x["received_total"]) for x in rows);ordered=sum(Decimal(x["ordered"]) for x in rows);remaining=sum(Decimal(x["remaining_to_receive"]) for x in rows)
    if received and (remaining or not accept_discrepancy):order.status="PARTIALLY_DELIVERED" if remaining else "DELIVERED"
    if accept_discrepancy and received:order.status="DELIVERED"
    return rows
def item_values(db,item):
    order_item=db.get(PurchaseOrderItem,item.purchase_order_item_id);price=item.actual_unit_price_gross if item.actual_unit_price_gross is not None else order_item.unit_price_gross;out=cols(item);out["effective_unit_price_gross"]=str(price);out["value_source"]="ACTUAL_DELIVERY_PRICE" if item.actual_unit_price_gross is not None else "ORDER_PRICE";out["received_value_gross"]=str(item.quantity_accepted*price);out["ordered_unit_price_gross"]=str(order_item.unit_price_gross);out["unit_price_variance"]=str(price-order_item.unit_price_gross);return out
def delivery_dict(db,d):
    order=db.get(PurchaseOrder,d.purchase_order_id);items=[item_values(db,x) for x in db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id==d.id))];out=cols(d);out.update(project_name=db.get(Project,d.project_id).name,supplier_name=db.get(Supplier,d.supplier_id).name,order_number=order.order_number,transport_estimated=str(order.transport_cost),transport_variance=str(d.transport_cost_actual-order.transport_cost) if d.transport_cost_actual is not None else None,items=items,issues=[cols(x) for x in db.scalars(select(DeliveryIssue).where(DeliveryIssue.delivery_id==d.id))],received_value_gross=str(sum((Decimal(x["received_value_gross"]) for x in items),Decimal("0"))));return out
def validate_line(p,outstanding):
    received=dec(p.get("quantity_received"));damaged=dec(p.get("quantity_damaged"));rejected=dec(p.get("quantity_rejected"));expected=dec(p.get("quantity_expected",outstanding))
    if min(received,damaged,rejected,expected)<0:raise HTTPException(422,"Cantitățile nu pot fi negative.")
    if damaged+rejected>received:raise HTTPException(422,"Cantitatea deteriorată și respinsă nu poate depăși cantitatea primită.")
    if received>outstanding and (not p.get("over_delivery_confirmed") or not str(p.get("notes","")).strip()):raise HTTPException(422,"Supralivrarea necesită confirmare explicită și observație.")
    return expected,received,damaged,rejected,max(expected-received,Decimal("0")),max(received-damaged-rejected,Decimal("0"))

@router.post("/projects/{project_id}/orders/{order_id}/deliveries",status_code=201)
def create_delivery(project_id:int,order_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    order=need(db,PurchaseOrder,order_id,"Comanda nu există.")
    if order.project_id!=project_id or (order.status not in {"ORDERED","PARTIALLY_DELIVERED"} and not p.get("_correction_of_id")):raise HTTPException(409,"Doar comenzile plasate pot fi recepționate.")
    d=PurchaseDelivery(project_id=project_id,purchase_order_id=order.id,supplier_id=order.supplier_id,delivery_number=p.get("delivery_number"),delivery_note_number=p.get("delivery_note_number"),delivery_date=parse_date(p.get("delivery_date")),status="EXPECTED",transport_cost_actual=dec(p["transport_cost_actual"]) if p.get("transport_cost_actual") not in (None,"") else None,notes=p.get("notes"),correction_of_id=p.get("_correction_of_id"));db.add(d);db.flush();provided={int(x["purchase_order_item_id"]):x for x in p.get("items",[])}
    for oi in db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id==order.id)):
        outstanding=max(oi.quantity-previous_received(db,oi.id),Decimal("0"));line=provided.get(oi.id,{"quantity_expected":outstanding,"quantity_received":0});expected,received,damaged,rejected,missing,accepted=validate_line(line,outstanding);di=DeliveryItem(delivery_id=d.id,purchase_order_item_id=oi.id,material_id=oi.material_id,supplier_product_id=oi.supplier_product_id,description=oi.description,sku=oi.sku,unit=oi.unit,quantity_ordered=oi.quantity,quantity_expected=expected,quantity_received=received,quantity_damaged=damaged,quantity_rejected=rejected,quantity_missing=missing,quantity_accepted=accepted,actual_unit_price_gross=dec(line["actual_unit_price_gross"]) if line.get("actual_unit_price_gross") not in (None,"") else None,notes=line.get("notes"),over_delivery_confirmed=bool(line.get("over_delivery_confirmed")));db.add(di);db.flush()
        if missing>0:db.add(DeliveryIssue(delivery_id=d.id,delivery_item_id=di.id,issue_type="MISSING",quantity=missing,description=f"Lipsă {missing} {oi.unit}: {oi.description}"));audit(db,"DELIVERY",d.id,"QUANTITY_DISCREPANCY",{"item_id":di.id,"missing":str(missing)})
        if damaged>0:db.add(DeliveryIssue(delivery_id=d.id,delivery_item_id=di.id,issue_type="DAMAGED",quantity=damaged,description=f"Cantitate deteriorată: {oi.description}"))
        if di.actual_unit_price_gross is not None and di.actual_unit_price_gross!=oi.unit_price_gross:db.add(DeliveryIssue(delivery_id=d.id,delivery_item_id=di.id,issue_type="PRICE_DIFFERENCE",description=f"Preț comandat {oi.unit_price_gross}; preț recepționat {di.actual_unit_price_gross}"))
    db.flush();delivery_items=list(db.scalars(select(DeliveryItem).where(DeliveryItem.delivery_id==d.id)));has_issues=db.scalar(select(DeliveryIssue.id).where(DeliveryIssue.delivery_id==d.id).limit(1)) is not None
    d.status="WITH_ISSUES" if has_issues else "RECEIVED" if delivery_items and all(x.quantity_missing==0 for x in delivery_items) else "PARTIALLY_RECEIVED" if any(x.quantity_received>0 for x in delivery_items) else "EXPECTED"
    audit(db,"DELIVERY",d.id,"DELIVERY_CREATED");db.commit();return delivery_dict(db,d)

@router.get("/projects/{project_id}/deliveries")
def list_deliveries(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):return [delivery_dict(db,x) for x in db.scalars(select(PurchaseDelivery).where(PurchaseDelivery.project_id==project_id).order_by(PurchaseDelivery.delivery_date.desc()))]
@router.get("/projects/{project_id}/deliveries/{delivery_id}")
def get_delivery(project_id:int,delivery_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    d=need(db,PurchaseDelivery,delivery_id,"Recepția nu există.")
    if d.project_id!=project_id:raise HTTPException(404,"Recepția nu există.")
    return delivery_dict(db,d)
@router.put("/projects/{project_id}/deliveries/{delivery_id}")
def edit_delivery(project_id:int,delivery_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    d=need(db,PurchaseDelivery,delivery_id,"Recepția nu există.")
    if d.project_id!=project_id or d.status=="CLOSED":raise HTTPException(409,"Recepția închisă este blocată. Creează o corecție.")
    for key in ("delivery_note_number","notes"):
        if key in p:setattr(d,key,p[key])
    if "transport_cost_actual" in p:d.transport_cost_actual=dec(p["transport_cost_actual"]) if p["transport_cost_actual"] not in (None,"") else None
    for line in p.get("items",[]):
        di=need(db,DeliveryItem,int(line["id"]),"Poziția recepției nu există.");outstanding=max(db.get(PurchaseOrderItem,di.purchase_order_item_id).quantity-previous_received(db,di.purchase_order_item_id,d.id),Decimal("0"));expected,received,damaged,rejected,missing,accepted=validate_line(line,outstanding)
        di.quantity_expected=expected;di.quantity_received=received;di.quantity_damaged=damaged;di.quantity_rejected=rejected;di.quantity_missing=missing;di.quantity_accepted=accepted;di.actual_unit_price_gross=dec(line["actual_unit_price_gross"]) if line.get("actual_unit_price_gross") not in (None,"") else None;di.notes=line.get("notes");di.over_delivery_confirmed=bool(line.get("over_delivery_confirmed"))
    db.commit();return delivery_dict(db,d)
@router.post("/projects/{project_id}/deliveries/{delivery_id}/close")
def close_delivery(project_id:int,delivery_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    d=need(db,PurchaseDelivery,delivery_id,"Recepția nu există.")
    if d.project_id!=project_id or d.status=="CLOSED":raise HTTPException(409,"Recepția este deja închisă.")
    issues=list(db.scalars(select(DeliveryIssue).where(DeliveryIssue.delivery_id==d.id,DeliveryIssue.status=="OPEN")));d.discrepancy_accepted=bool(p.get("accept_discrepancy"));d.status="WITH_ISSUES" if issues and not d.discrepancy_accepted else "CLOSED";sync_order(db,db.get(PurchaseOrder,d.purchase_order_id),d.discrepancy_accepted);audit(db,"DELIVERY",d.id,"DELIVERY_RECEIVED");db.commit();return delivery_dict(db,d)
@router.post("/projects/{project_id}/deliveries/{delivery_id}/correction",status_code=201)
def correct_delivery(project_id:int,delivery_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    src=need(db,PurchaseDelivery,delivery_id,"Recepția nu există.")
    if src.status!="CLOSED":raise HTTPException(409,"Corecția este disponibilă doar pentru recepții închise.")
    return create_delivery(project_id,src.purchase_order_id,{"delivery_number":f"CORECȚIE-{src.id}","notes":f"Corecție pentru recepția {src.id}","_correction_of_id":src.id},db,_)

@router.post("/projects/{project_id}/deliveries/{delivery_id}/issues",status_code=201)
def create_issue(project_id:int,delivery_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    d=need(db,PurchaseDelivery,delivery_id,"Recepția nu există.");kind=p.get("issue_type")
    if d.project_id!=project_id or kind not in ISSUE_TYPES:raise HTTPException(422,"Tip de problemă invalid.")
    x=DeliveryIssue(delivery_id=d.id,delivery_item_id=p.get("delivery_item_id"),issue_type=kind,quantity=dec(p["quantity"]) if p.get("quantity") not in (None,"") else None,description=str(p.get("description","")).strip(),status="OPEN");db.add(x);db.flush();audit(db,"DELIVERY_ISSUE",x.id,"ISSUE_CREATED");db.commit();return cols(x)
@router.post("/projects/{project_id}/delivery-issues/{issue_id}/status")
def issue_status(project_id:int,issue_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    x=need(db,DeliveryIssue,issue_id,"Problema nu există.");d=db.get(PurchaseDelivery,x.delivery_id);target=p.get("status")
    if d.project_id!=project_id or target not in {"RESOLVED","ACCEPTED","REJECTED"}:raise HTTPException(422,"Status problemă invalid.")
    x.status=target;x.resolution_notes=p.get("resolution_notes");x.resolved_at=datetime.now(timezone.utc);audit(db,"DELIVERY_ISSUE",x.id,"ISSUE_RESOLVED");db.commit();return cols(x)

def return_dict(db,r):
    out=cols(r);out.update(project_name=db.get(Project,r.project_id).name,supplier_name=db.get(Supplier,r.supplier_id).name,items=[cols(x) for x in db.scalars(select(MaterialReturnItem).where(MaterialReturnItem.material_return_id==r.id))]);return out
@router.post("/projects/{project_id}/returns",status_code=201)
def create_return(project_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    if p.get("reason") not in RETURN_REASONS:raise HTTPException(422,"Motiv de retur invalid.")
    need(db,Project,project_id,"Proiectul nu există.");need(db,Supplier,int(p["supplier_id"]),"Furnizorul nu există.")
    if p.get("delivery_id") and need(db,PurchaseDelivery,int(p["delivery_id"]),"Recepția nu există.").project_id!=project_id:raise HTTPException(404,"Recepția nu există.")
    r=MaterialReturn(project_id=project_id,supplier_id=int(p["supplier_id"]),delivery_id=p.get("delivery_id"),purchase_order_id=p.get("purchase_order_id"),return_number=p.get("return_number") or f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}",return_date=parse_date(p.get("return_date")),reason=p["reason"],status="DRAFT",refund_amount_gross=dec(p["refund_amount_gross"]) if p.get("refund_amount_gross") not in (None,"") else None,notes=p.get("notes"));db.add(r);db.flush()
    for line in p.get("items",[]):
        di=need(db,DeliveryItem,int(line["delivery_item_id"]),"Poziția recepției nu există.");qty=dec(line["quantity"])
        if qty<=0 or qty>di.quantity_accepted:raise HTTPException(422,"Cantitatea returnată trebuie să fie pozitivă și cel mult cantitatea acceptată.")
        db.add(MaterialReturnItem(material_return_id=r.id,delivery_item_id=di.id,material_id=di.material_id,description=di.description,sku=di.sku,quantity=qty,unit=di.unit,expected_refund_gross=dec(line["expected_refund_gross"]) if line.get("expected_refund_gross") not in (None,"") else None,actual_refund_gross=dec(line["actual_refund_gross"]) if line.get("actual_refund_gross") not in (None,"") else None,notes=line.get("notes")))
    audit(db,"MATERIAL_RETURN",r.id,"RETURN_CREATED");db.commit();return return_dict(db,r)
@router.get("/projects/{project_id}/returns")
def list_returns(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):return [return_dict(db,x) for x in db.scalars(select(MaterialReturn).where(MaterialReturn.project_id==project_id).order_by(MaterialReturn.created_at.desc()))]
@router.post("/projects/{project_id}/returns/{return_id}/status")
def return_status(project_id:int,return_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    r=need(db,MaterialReturn,return_id,"Returul nu există.");target=p.get("status");allowed={"DRAFT":{"REQUESTED"},"REQUESTED":{"ACCEPTED","REJECTED"},"ACCEPTED":{"SENT"},"SENT":{"REFUNDED"},"REFUNDED":{"CLOSED"}}
    if r.project_id!=project_id or target not in allowed.get(r.status,set()):raise HTTPException(409,"Tranziție de status retur nepermisă.")
    r.status=target
    if target=="REFUNDED" and p.get("refund_amount_gross") is not None:r.refund_amount_gross=dec(p["refund_amount_gross"])
    audit(db,"MATERIAL_RETURN",r.id,"RETURN_ACCEPTED" if target=="ACCEPTED" else "RETURN_REFUNDED" if target=="REFUNDED" else f"RETURN_{target}");db.commit();return return_dict(db,r)

@router.get("/projects/{project_id}/orders/{order_id}/reconciliation")
def order_reconciliation(project_id:int,order_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    order=need(db,PurchaseOrder,order_id,"Comanda nu există.")
    if order.project_id!=project_id:raise HTTPException(404,"Comanda nu există.")
    return {"items":reconciliation(db,order)}
@router.get("/projects/{project_id}/supplier-delivery-performance")
def performance(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    result=[]
    for supplier in db.scalars(select(Supplier)):
        ds=list(db.scalars(select(PurchaseDelivery).where(PurchaseDelivery.project_id==project_id,PurchaseDelivery.supplier_id==supplier.id)));ids=[x.id for x in ds];issues=list(db.scalars(select(DeliveryIssue).where(DeliveryIssue.delivery_id.in_(ids)))) if ids else [];returns=list(db.scalars(select(MaterialReturn).where(MaterialReturn.project_id==project_id,MaterialReturn.supplier_id==supplier.id)));result.append({"supplier_id":supplier.id,"supplier_name":supplier.name,"ordered_deliveries":len(ds),"on_time_deliveries":None,"incomplete_deliveries":sum(x.status in {"EXPECTED","PARTIALLY_RECEIVED","WITH_ISSUES"} for x in ds),"issue_count":len(issues),"damaged_quantity":str(sum((x.quantity or 0 for x in issues if x.issue_type=="DAMAGED"),Decimal("0"))),"returns_count":len(returns)})
    return result

@router.get("/projects/{project_id}/{kind}/{entity_id}/logistics-export.{format}")
def export(project_id:int,kind:str,entity_id:int,format:str,db:Session=Depends(get_db),_:User=Depends(current_user)):
    if kind=="deliveries":data=get_delivery(project_id,entity_id,db,_);pdf,xlsx=delivery_pdf,delivery_xlsx
    elif kind=="returns":r=need(db,MaterialReturn,entity_id,"Returul nu există.");data=return_dict(db,r);pdf,xlsx=return_pdf,return_xlsx
    else:raise HTTPException(404,"Export necunoscut.")
    if format=="pdf":return Response(pdf(data),media_type="application/pdf")
    if format=="xlsx":return Response(xlsx(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    raise HTTPException(404,"Format necunoscut.")

@router.post("/projects/{project_id}/{kind}/{entity_id}/attachments",status_code=201)
async def upload(project_id:int,kind:str,entity_id:int,file:UploadFile=File(...),description:str|None=Form(None),issue_id:int|None=Form(None),db:Session=Depends(get_db),_:User=Depends(current_user)):
    entity_type={"deliveries":"DELIVERY_ISSUE" if issue_id else "PURCHASE_DELIVERY","returns":"MATERIAL_RETURN"}.get(kind)
    if not entity_type:raise HTTPException(404,"Tip document necunoscut.")
    if kind=="deliveries":
        delivery=need(db,PurchaseDelivery,entity_id,"Recepția nu există.")
        if delivery.project_id!=project_id:raise HTTPException(404,"Recepția nu există.")
        if issue_id:
            issue=need(db,DeliveryIssue,issue_id,"Problema nu există.")
            if issue.delivery_id!=delivery.id:raise HTTPException(404,"Problema nu există.")
    else:
        material_return=need(db,MaterialReturn,entity_id,"Returul nu există.")
        if material_return.project_id!=project_id:raise HTTPException(404,"Returul nu există.")
    content=await file.read(10*1024*1024+1)
    try:ext=validate_attachment(file.filename or "",file.content_type or "",len(content));validate_signature(ext,content)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    folder_name="deliveries" if kind=="deliveries" else "returns";folder=Path(settings.data_root)/"projects"/str(project_id)/folder_name;folder.mkdir(parents=True,exist_ok=True);stored=f"{uuid.uuid4().hex}{ext}";(folder/stored).write_bytes(content);original=re.sub(r"[^A-Za-z0-9._ -]+","_",Path(file.filename or "document").name)[:255];row=Attachment(project_id=project_id,entity_type=entity_type,entity_id=issue_id or entity_id,original_filename=original,stored_filename=stored,mime_type=file.content_type or "",file_size=len(content),relative_path=f"projects/{project_id}/{folder_name}/{stored}",description=description);db.add(row);db.commit();return cols(row)
