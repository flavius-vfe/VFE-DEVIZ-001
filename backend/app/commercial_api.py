from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import json,re,uuid
from fastapi import APIRouter,Depends,HTTPException,Response,UploadFile,File,Form
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .deps import current_user
from .models import User,Project,Supplier,SupplierQuote,SupplierQuoteItem,Discount,Attachment,PurchaseOrder,PurchaseOrderItem,PurchaseOrderSequence,AuditEvent,ProcurementPlan,ProcurementPlanItem,ProcurementPlanSupplierTotal,Material,PurchaseDelivery,DeliveryIssue,MaterialReturn
from .commercial import dec,line_calculation,quote_calculation,validity,validate_attachment,validate_signature,DISCOUNT_TYPES
from .commercial_exports import quote_pdf,quote_xlsx,order_pdf,order_xlsx
from .config import settings
router=APIRouter(prefix="/api")
def need(db,m,id,msg):
    x=db.get(m,id)
    if not x:raise HTTPException(404,msg)
    return x
def iso(v):return datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None
def audit(db,entity,id,action,details=None):db.add(AuditEvent(entity_type=entity,entity_id=id,action=action,details=details or {}))
def cols(x):return {c.name:(str(getattr(x,c.name)) if isinstance(getattr(x,c.name),Decimal) else getattr(x,c.name)) for c in x.__table__.columns}

@router.post("/suppliers/local",status_code=201)
def create_supplier(p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    typ=p.get("type","MANUAL")
    if typ not in {"RETAILER","LOCAL_MATERIAL_SUPPLIER","READY_MIX_CONCRETE","MANUAL"}:raise HTTPException(422,"Tip de furnizor invalid.")
    code=re.sub(r"[^A-Z0-9_]+","_",str(p.get("code","")).upper()).strip("_")
    if not code or not str(p.get("name","")).strip():raise HTTPException(422,"Codul și denumirea sunt obligatorii.")
    row=Supplier(code=code,name=str(p["name"]).strip(),type=typ,website=p.get("website"),phone=p.get("phone"),email=p.get("email"),address=p.get("address"),locality=p.get("locality"),county=p.get("county"),notes=p.get("notes"),active=bool(p.get("active",True)));db.add(row)
    try:db.commit()
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"Codul sau denumirea furnizorului există deja.") from exc
    db.refresh(row);return cols(row)

@router.put("/suppliers/{supplier_id}")
def edit_supplier(supplier_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    row=need(db,Supplier,supplier_id,"Furnizorul nu există.")
    for key in ("name","type","phone","email","address","locality","county","website","notes","active"):
        if key in p:setattr(row,key,p[key])
    db.commit();return cols(row)

def recalc_quote(db,q):
    items=list(db.scalars(select(SupplierQuoteItem).where(SupplierQuoteItem.quote_id==q.id)));now=datetime.now(timezone.utc);rows=db.scalars(select(Discount).where(((Discount.scope_type=="QUOTE")&(Discount.scope_id==q.id))|((Discount.scope_type=="SUPPLIER")&(Discount.scope_id==q.supplier_id)),Discount.active.is_(True)));discounts=[cols(x) for x in rows if (not x.valid_from or (x.valid_from if x.valid_from.tzinfo else x.valid_from.replace(tzinfo=timezone.utc))<=now) and (not x.valid_until or (x.valid_until if x.valid_until.tzinfo else x.valid_until.replace(tzinfo=timezone.utc))>=now)]
    total=quote_calculation([cols(x) for x in items],discounts,q.transport_net,q.pump_fixed_cost,q.pump_hourly_cost,q.pump_hours,q.waiting_cost,q.other_cost)
    q.subtotal_net=total["subtotal_net"];q.discount_total_net=total["discount_total_net"];q.vat_total=total["vat_total"];q.total_gross=total["total_gross"]
def quote_dict(db,q):
    out=cols(q);out["validity"]=validity(q.valid_until);out["supplier_name"]=db.get(Supplier,q.supplier_id).name;out["items"]=[cols(x) for x in db.scalars(select(SupplierQuoteItem).where(SupplierQuoteItem.quote_id==q.id))];out["discounts"]=[cols(x) for x in db.scalars(select(Discount).where(Discount.scope_type=="QUOTE",Discount.scope_id==q.id))];return out

@router.get("/projects/{project_id}/quotes")
def list_quotes(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    need(db,Project,project_id,"Proiectul nu există.");return [quote_dict(db,x) for x in db.scalars(select(SupplierQuote).where(SupplierQuote.project_id==project_id).order_by(SupplierQuote.created_at.desc()))]
@router.get("/projects/{project_id}/quotes/{quote_id}")
def get_quote(project_id:int,quote_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.")
    if q.project_id!=project_id:raise HTTPException(404,"Oferta nu există.")
    return quote_dict(db,q)
@router.post("/projects/{project_id}/quotes",status_code=201)
def create_quote(project_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    need(db,Project,project_id,"Proiectul nu există.");need(db,Supplier,int(p["supplier_id"]),"Furnizorul nu există.")
    q=SupplierQuote(project_id=project_id,supplier_id=int(p["supplier_id"]),quote_number=p.get("quote_number"),quote_date=iso(p.get("quote_date")) or datetime.now(timezone.utc),valid_until=iso(p.get("valid_until")),status="DRAFT",transport_net=dec(p.get("transport_net")),pump_fixed_cost=dec(p.get("pump_fixed_cost")),pump_hourly_cost=dec(p.get("pump_hourly_cost")),pump_hours=dec(p.get("pump_hours")),waiting_cost=dec(p.get("waiting_cost")),other_cost=dec(p.get("other_cost")),notes=p.get("notes"),conditions=p.get("conditions") or {});db.add(q);db.flush();audit(db,"SUPPLIER_QUOTE",q.id,"QUOTE_CREATED");db.commit();return quote_dict(db,q)
@router.put("/projects/{project_id}/quotes/{quote_id}")
def edit_quote(project_id:int,quote_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.")
    if q.project_id!=project_id or q.status=="ARCHIVED":raise HTTPException(409,"Oferta nu poate fi editată.")
    for key in ("supplier_id","quote_number","notes","conditions"):
        if key in p:setattr(q,key,p[key])
    for key in ("transport_net","pump_fixed_cost","pump_hourly_cost","pump_hours","waiting_cost","other_cost"):
        if key in p:setattr(q,key,dec(p[key]))
    if "quote_date" in p:q.quote_date=iso(p["quote_date"])
    if "valid_until" in p:q.valid_until=iso(p["valid_until"])
    recalc_quote(db,q);db.commit();return quote_dict(db,q)
@router.post("/projects/{project_id}/quotes/{quote_id}/items",status_code=201)
def add_quote_item(project_id:int,quote_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.")
    if q.project_id!=project_id:raise HTTPException(404,"Oferta nu există.")
    calc=line_calculation(p["quantity"],p["unit_price_net"],p.get("vat_rate",21),p.get("line_discount_type"),p.get("line_discount_value"))
    row=SupplierQuoteItem(quote_id=q.id,material_id=p.get("material_id"),supplier_product_id=p.get("supplier_product_id"),description=str(p["description"]).strip(),supplier_sku=p.get("supplier_sku"),unit=p["unit"],quantity=dec(p["quantity"]),unit_price_net=dec(p["unit_price_net"]),vat_rate=dec(p.get("vat_rate",21)),line_discount_type=p.get("line_discount_type"),line_discount_value=dec(p.get("line_discount_value")) if p.get("line_discount_value") is not None else None,attributes=p.get("attributes") or {},notes=p.get("notes"),**{k:calc[k] for k in ("unit_price_gross","line_total_net","line_vat","line_total_gross")});db.add(row);db.flush();recalc_quote(db,q);db.commit();return quote_dict(db,q)
@router.put("/projects/{project_id}/quotes/{quote_id}/items/{item_id}")
def edit_quote_item(project_id:int,quote_id:int,item_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.");item=need(db,SupplierQuoteItem,item_id,"Poziția nu există.")
    if q.project_id!=project_id or item.quote_id!=q.id:raise HTTPException(404,"Poziția nu există.")
    for key in ("material_id","supplier_product_id","description","supplier_sku","unit","notes","attributes"):
        if key in p:setattr(item,key,p[key])
    for key in ("quantity","unit_price_net","vat_rate","line_discount_value"):
        if key in p:setattr(item,key,dec(p[key]) if p[key] is not None else None)
    if "line_discount_type" in p:item.line_discount_type=p["line_discount_type"]
    calc=line_calculation(item.quantity,item.unit_price_net,item.vat_rate,item.line_discount_type,item.line_discount_value)
    for key in ("unit_price_gross","line_total_net","line_vat","line_total_gross"):setattr(item,key,calc[key])
    recalc_quote(db,q);db.commit();return quote_dict(db,q)
@router.delete("/projects/{project_id}/quotes/{quote_id}/items/{item_id}",status_code=204)
def delete_quote_item(project_id:int,quote_id:int,item_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.");item=need(db,SupplierQuoteItem,item_id,"Poziția nu există.")
    if q.project_id!=project_id or item.quote_id!=q.id:raise HTTPException(404,"Poziția nu există.")
    db.delete(item);db.flush();recalc_quote(db,q);db.commit();return Response(status_code=204)
@router.post("/projects/{project_id}/quotes/{quote_id}/discounts",status_code=201)
def add_discount(project_id:int,quote_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.");typ=p.get("discount_type")
    if q.project_id!=project_id or typ not in DISCOUNT_TYPES:raise HTTPException(422,"Discount invalid.")
    d=Discount(scope_type="QUOTE",scope_id=q.id,discount_type=typ,value=dec(p["value"]),description=p.get("description"),valid_from=iso(p.get("valid_from")),valid_until=iso(p.get("valid_until")),conditions=p.get("conditions"),active=True);db.add(d);db.flush();recalc_quote(db,q);audit(db,"SUPPLIER_QUOTE",q.id,"DISCOUNT_CHANGED",{"type":typ});db.commit();return quote_dict(db,q)

@router.post("/discounts",status_code=201)
def create_scoped_discount(p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    scope=p.get("scope_type");typ=p.get("discount_type");scope_id=int(p.get("scope_id",0))
    if scope not in {"SUPPLIER","QUOTE","LINE"} or typ not in DISCOUNT_TYPES or scope_id<=0:raise HTTPException(422,"Discount invalid.")
    row=Discount(scope_type=scope,scope_id=scope_id,discount_type=typ,value=dec(p["value"]),description=p.get("description"),valid_from=iso(p.get("valid_from")),valid_until=iso(p.get("valid_until")),conditions=p.get("conditions"),active=bool(p.get("active",True)));db.add(row);db.flush()
    if scope=="LINE":
        item=need(db,SupplierQuoteItem,scope_id,"Poziția nu există.");item.line_discount_type="PERCENT" if typ in {"PERCENT","PAYMENT_CONDITION","VOLUME_DISCOUNT"} else "FIXED_AMOUNT";item.line_discount_value=row.value;calc=line_calculation(item.quantity,item.unit_price_net,item.vat_rate,item.line_discount_type,item.line_discount_value)
        for key in ("unit_price_gross","line_total_net","line_vat","line_total_gross"):setattr(item,key,calc[key])
        recalc_quote(db,db.get(SupplierQuote,item.quote_id))
    elif scope=="QUOTE":recalc_quote(db,need(db,SupplierQuote,scope_id,"Oferta nu există."))
    else:
        for quote in db.scalars(select(SupplierQuote).where(SupplierQuote.supplier_id==scope_id)):recalc_quote(db,quote)
    audit(db,"DISCOUNT",row.id,"DISCOUNT_CHANGED",{"scope":scope});db.commit();return cols(row)
@router.post("/projects/{project_id}/quotes/{quote_id}/status")
def quote_status(project_id:int,quote_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.");status=p.get("status")
    if q.project_id!=project_id or status not in {"DRAFT","ACTIVE","SELECTED","REJECTED","ARCHIVED"}:raise HTTPException(422,"Status invalid.")
    q.status=status;audit(db,"SUPPLIER_QUOTE",q.id,"QUOTE_SELECTED" if status=="SELECTED" else f"QUOTE_{status}");db.commit();return quote_dict(db,q)
@router.post("/projects/{project_id}/quotes/{quote_id}/duplicate",status_code=201)
def duplicate_quote(project_id:int,quote_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    src=need(db,SupplierQuote,quote_id,"Oferta nu există.");data=cols(src);data.pop("id");data.update(status="DRAFT",quote_number=None,created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc));q=SupplierQuote(**data);db.add(q);db.flush()
    for item in db.scalars(select(SupplierQuoteItem).where(SupplierQuoteItem.quote_id==src.id)):d=cols(item);d.pop("id");d["quote_id"]=q.id;db.add(SupplierQuoteItem(**d))
    recalc_quote(db,q);audit(db,"SUPPLIER_QUOTE",q.id,"QUOTE_CREATED",{"duplicated_from":src.id});db.commit();return quote_dict(db,q)

def next_number(db):
    year=datetime.now(timezone.utc).year;seq=db.scalar(select(PurchaseOrderSequence).where(PurchaseOrderSequence.year==year).with_for_update())
    if not seq:seq=PurchaseOrderSequence(year=year,value=0);db.add(seq);db.flush()
    seq.value+=1;return f"PO-{year}-{seq.value:04d}"
def order_dict(db,o):
    from .logistics_api import reconciliation
    out=cols(o);out["supplier_name"]=db.get(Supplier,o.supplier_id).name;out["project_name"]=db.get(Project,o.project_id).name;out["items"]=[cols(x) for x in db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id==o.id))];out["reconciliation"]=reconciliation(db,o);return out
def recalc_order(db,o):
    items=list(db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id==o.id)));o.subtotal_net=sum((x.line_total_net+x.discount_net for x in items),Decimal("0"));o.discount_total=sum((x.discount_net for x in items),Decimal("0"));o.vat_total=sum((x.line_vat for x in items),Decimal("0"))+o.transport_cost*Decimal("0.21");o.total_gross=o.subtotal_net-o.discount_total+o.transport_cost+o.vat_total
def order_from_quote(db,q):
    project=db.get(Project,q.project_id);number=next_number(db);commercial_transport=q.transport_net+q.pump_fixed_cost+q.pump_hourly_cost*q.pump_hours+q.waiting_cost+q.other_cost;o=PurchaseOrder(project_id=q.project_id,supplier_id=q.supplier_id,supplier_quote_id=q.id,order_number=number,status="DRAFT",delivery_address=project.delivery_address or f"{project.delivery_locality}, {project.delivery_county}",subtotal_net=q.subtotal_net,discount_total=q.discount_total_net,transport_cost=commercial_transport,vat_total=q.vat_total,total_gross=q.total_gross,notes=q.notes);db.add(o);db.flush()
    for x in db.scalars(select(SupplierQuoteItem).where(SupplierQuoteItem.quote_id==q.id)):db.add(PurchaseOrderItem(purchase_order_id=o.id,material_id=x.material_id,supplier_product_id=x.supplier_product_id,quote_item_id=x.id,description=x.description,sku=x.supplier_sku,unit=x.unit,quantity=x.quantity,unit_price_net=x.unit_price_net,vat_rate=x.vat_rate,unit_price_gross=x.unit_price_gross,discount_net=(x.quantity*x.unit_price_net-x.line_total_net),line_total_net=x.line_total_net,line_vat=x.line_vat,line_total_gross=x.line_total_gross,notes=x.notes))
    audit(db,"PURCHASE_ORDER",o.id,"ORDER_CREATED",{"quote_id":q.id});return o
@router.post("/projects/{project_id}/quotes/{quote_id}/purchase-order",status_code=201)
def create_order_quote(project_id:int,quote_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.")
    if q.project_id!=project_id or validity(q.valid_until)=="EXPIRED":raise HTTPException(409,"Oferta expirată nu poate genera automat o comandă.")
    o=order_from_quote(db,q);q.status="SELECTED";audit(db,"SUPPLIER_QUOTE",q.id,"QUOTE_SELECTED",{"purchase_order_id":o.id})
    try:db.commit()
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"Numărul comenzii există deja.") from exc
    return order_dict(db,o)
@router.get("/projects/{project_id}/orders")
def list_orders(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):return [order_dict(db,x) for x in db.scalars(select(PurchaseOrder).where(PurchaseOrder.project_id==project_id).order_by(PurchaseOrder.created_at.desc()))]
@router.get("/projects/{project_id}/orders/{order_id}")
def get_order(project_id:int,order_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    o=need(db,PurchaseOrder,order_id,"Comanda nu există.")
    if o.project_id!=project_id:raise HTTPException(404,"Comanda nu există.")
    return order_dict(db,o)
@router.post("/projects/{project_id}/orders/{order_id}/status")
def order_status(project_id:int,order_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    o=need(db,PurchaseOrder,order_id,"Comanda nu există.");target=p.get("status");allowed={"DRAFT":{"READY_TO_ORDER","CANCELLED"},"READY_TO_ORDER":{"ORDERED","CANCELLED"},"ORDERED":set(),"CANCELLED":set()}
    if o.project_id!=project_id or target not in allowed.get(o.status,set()):raise HTTPException(409,"Tranziție de status nepermisă.")
    o.status=target
    if o.procurement_plan_id and target=="ORDERED":
        for item in db.scalars(select(ProcurementPlanItem).where(ProcurementPlanItem.procurement_plan_id==o.procurement_plan_id,ProcurementPlanItem.supplier_id==o.supplier_id)):item.procurement_status="ORDERED"
    audit(db,"PURCHASE_ORDER",o.id,"ORDER_MARKED_ORDERED" if target=="ORDERED" else "ORDER_CANCELLED" if target=="CANCELLED" else "ORDER_READY");db.commit();return order_dict(db,o)
@router.put("/projects/{project_id}/orders/{order_id}")
def edit_order(project_id:int,order_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    o=need(db,PurchaseOrder,order_id,"Comanda nu există.")
    if o.project_id!=project_id or o.status=="ORDERED":raise HTTPException(409,"Valorile comerciale ale comenzii plasate sunt blocate.")
    o.notes=p.get("notes",o.notes);o.requested_delivery_date=iso(p.get("requested_delivery_date")) if "requested_delivery_date" in p else o.requested_delivery_date;db.commit();return order_dict(db,o)
@router.put("/projects/{project_id}/orders/{order_id}/items/{item_id}")
def edit_order_item(project_id:int,order_id:int,item_id:int,p:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    o=need(db,PurchaseOrder,order_id,"Comanda nu există.");item=need(db,PurchaseOrderItem,item_id,"Poziția nu există.")
    if o.project_id!=project_id or item.purchase_order_id!=o.id or o.status=="ORDERED":raise HTTPException(409,"Valorile comerciale ale comenzii plasate sunt blocate.")
    for key in ("description","sku","unit","notes"):
        if key in p:setattr(item,key,p[key])
    for key in ("quantity","unit_price_net","vat_rate"):
        if key in p:setattr(item,key,dec(p[key]))
    discount=dec(p.get("discount_net",item.discount_net));base=item.quantity*item.unit_price_net;item.discount_net=min(discount,base);item.line_total_net=base-item.discount_net;item.unit_price_gross=item.unit_price_net*(Decimal("1")+item.vat_rate/Decimal("100"));item.line_vat=item.line_total_net*item.vat_rate/Decimal("100");item.line_total_gross=item.line_total_net+item.line_vat;recalc_order(db,o);db.commit();return order_dict(db,o)
@router.post("/projects/{project_id}/orders/{order_id}/revision",status_code=201)
def revise_order(project_id:int,order_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    src=need(db,PurchaseOrder,order_id,"Comanda nu există.");data=cols(src);data.pop("id");data.update(order_number=next_number(db),status="DRAFT",revision_of_id=src.id,created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc));o=PurchaseOrder(**data);db.add(o);db.flush()
    for item in db.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id==src.id)):d=cols(item);d.pop("id");d["purchase_order_id"]=o.id;db.add(PurchaseOrderItem(**d))
    audit(db,"PURCHASE_ORDER",o.id,"ORDER_CREATED",{"revision_of":src.id});db.commit();return order_dict(db,o)

@router.post("/projects/{project_id}/procurement/plans/{plan_id}/purchase-orders",status_code=201)
def orders_from_plan(project_id:int,plan_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    plan=need(db,ProcurementPlan,plan_id,"Planul nu există.");project=need(db,Project,project_id,"Proiectul nu există.");items=list(db.scalars(select(ProcurementPlanItem).where(ProcurementPlanItem.procurement_plan_id==plan.id)));totals={x.supplier_id:x for x in db.scalars(select(ProcurementPlanSupplierTotal).where(ProcurementPlanSupplierTotal.procurement_plan_id==plan.id))};orders=[]
    for supplier_id in sorted({x.supplier_id for x in items}):
        selected=[x for x in items if x.supplier_id==supplier_id];subtotal=sum((x.product_subtotal_gross for x in selected),Decimal("0"));delivery_gross=(totals.get(supplier_id).delivery_cost_gross if totals.get(supplier_id) and totals.get(supplier_id).delivery_cost_gross is not None else Decimal("0"));transport_net=delivery_gross/Decimal("1.21");o=PurchaseOrder(project_id=project_id,supplier_id=supplier_id,procurement_plan_id=plan.id,order_number=next_number(db),status="DRAFT",delivery_address=project.delivery_address or f"{project.delivery_locality}, {project.delivery_county}",subtotal_net=subtotal/Decimal("1.21"),discount_total=0,transport_cost=transport_net,vat_total=(subtotal+delivery_gross)-(subtotal+delivery_gross)/Decimal("1.21"),total_gross=subtotal+delivery_gross);db.add(o);db.flush()
        for x in selected:
            db.add(PurchaseOrderItem(purchase_order_id=o.id,estimate_resource_id=x.estimate_resource_id,material_id=x.material_id,supplier_product_id=x.supplier_product_id,description=x.product_name,sku=x.supplier_sku,unit=x.package_unit,quantity=x.purchased_quantity,package_quantity=x.package_quantity,package_count=x.packages_to_buy,unit_price_net=x.unit_package_price_gross/Decimal("1.21"),vat_rate=21,unit_price_gross=x.unit_package_price_gross,discount_net=0,line_total_net=x.product_subtotal_gross/Decimal("1.21"),line_vat=x.product_subtotal_gross-x.product_subtotal_gross/Decimal("1.21"),line_total_gross=x.product_subtotal_gross))
            x.procurement_status="ORDER_DRAFT"
        audit(db,"PURCHASE_ORDER",o.id,"ORDER_CREATED",{"plan_id":plan.id});orders.append(o)
    db.commit();return [order_dict(db,x) for x in orders]

@router.get("/projects/{project_id}/{kind}/{entity_id}/export.{format}")
def commercial_export(project_id:int,kind:str,entity_id:int,format:str,db:Session=Depends(get_db),_:User=Depends(current_user)):
    if kind=="quotes":data=get_quote(project_id,entity_id,db,_);pdf,xlsx=quote_pdf,quote_xlsx
    elif kind=="orders":data=get_order(project_id,entity_id,db,_);pdf,xlsx=order_pdf,order_xlsx
    else:raise HTTPException(404,"Export necunoscut.")
    if format=="json":return data
    if format=="pdf":return Response(pdf(data),media_type="application/pdf")
    if format=="xlsx":return Response(xlsx(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    raise HTTPException(404,"Format necunoscut.")

@router.post("/projects/{project_id}/quotes/{quote_id}/attachments",status_code=201)
async def upload_attachment(project_id:int,quote_id:int,file:UploadFile=File(...),description:str|None=Form(None),db:Session=Depends(get_db),_:User=Depends(current_user)):
    q=need(db,SupplierQuote,quote_id,"Oferta nu există.")
    if q.project_id!=project_id:raise HTTPException(404,"Oferta nu există.")
    content=await file.read(10*1024*1024+1)
    try:ext=validate_attachment(file.filename or "",file.content_type or "",len(content));validate_signature(ext,content)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    folder=Path(settings.data_root)/"projects"/str(project_id)/"supplier-quotes";folder.mkdir(parents=True,exist_ok=True);stored=f"{uuid.uuid4().hex}{ext}";(folder/stored).write_bytes(content);relative=f"projects/{project_id}/supplier-quotes/{stored}"
    original=re.sub(r"[^A-Za-z0-9._ -]+","_",Path(file.filename or "document").name)[:255]
    row=Attachment(project_id=project_id,entity_type="SUPPLIER_QUOTE",entity_id=q.id,original_filename=original,stored_filename=stored,mime_type=file.content_type or "",file_size=len(content),relative_path=relative,description=description);db.add(row);db.commit();db.refresh(row);return cols(row)
@router.get("/projects/{project_id}/quotes/{quote_id}/attachments")
def list_attachments(project_id:int,quote_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    need(db,SupplierQuote,quote_id,"Oferta nu există.");return [cols(x) for x in db.scalars(select(Attachment).where(Attachment.project_id==project_id,Attachment.entity_type=="SUPPLIER_QUOTE",Attachment.entity_id==quote_id))]
@router.get("/projects/{project_id}/attachments/{attachment_id}")
def download_attachment(project_id:int,attachment_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    row=need(db,Attachment,attachment_id,"Fișierul nu există.");root=Path(settings.data_root).resolve();path=(root/row.relative_path).resolve()
    if row.project_id!=project_id or root not in path.parents or not path.is_file():raise HTTPException(404,"Fișierul nu există.")
    return Response(path.read_bytes(),media_type=row.mime_type,headers={"Content-Disposition":f'attachment; filename="{row.original_filename}"',"X-Content-Type-Options":"nosniff"})

@router.get("/projects/{project_id}/commercial-dashboard")
def dashboard(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    quotes=list(db.scalars(select(SupplierQuote).where(SupplierQuote.project_id==project_id)));orders=list(db.scalars(select(PurchaseOrder).where(PurchaseOrder.project_id==project_id)));deliveries=list(db.scalars(select(PurchaseDelivery).where(PurchaseDelivery.project_id==project_id)));delivery_ids=[x.id for x in deliveries];issues=list(db.scalars(select(DeliveryIssue).where(DeliveryIssue.delivery_id.in_(delivery_ids),DeliveryIssue.status=="OPEN"))) if delivery_ids else [];returns=list(db.scalars(select(MaterialReturn).where(MaterialReturn.project_id==project_id)))
    return {"active_quotes":sum(x.status in {"ACTIVE","SELECTED"} and validity(x.valid_until)!="EXPIRED" for x in quotes),"expiring_quotes":sum(validity(x.valid_until)=="EXPIRING_SOON" for x in quotes),"draft_orders":sum(x.status=="DRAFT" for x in orders),"ready_orders":sum(x.status=="READY_TO_ORDER" for x in orders),"ordered":sum(x.status=="ORDERED" for x in orders),"expected_deliveries":sum(x.status=="EXPECTED" for x in deliveries),"partial_deliveries":sum(x.status=="PARTIALLY_RECEIVED" for x in deliveries)+sum(x.status=="PARTIALLY_DELIVERED" for x in orders),"open_delivery_issues":len(issues),"open_returns":sum(x.status not in {"CLOSED","REJECTED"} for x in returns)}
