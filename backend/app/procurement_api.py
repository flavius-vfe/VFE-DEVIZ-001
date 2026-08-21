from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import select,delete
from sqlalchemy.orm import Session
from .db import get_db
from .deps import current_user
from .models import User,Project,Building,Level,EstimateSection,EstimateItem,EstimateResourceLine,Material,Supplier,SupplierLocation,SupplierProduct,ProductMatch,PriceObservation,DeliveryQuote,SupplierDeliveryRule,ProcurementPlan,ProcurementPlanItem,ProcurementPlanSupplierTotal
from .procurement import Candidate,Delivery,choose_delivery,estimated_delivery,optimize,freshness
from .procurement_exports import shopping_pdf,shopping_xlsx
from .config import settings
router=APIRouter(prefix="/api")

def need(db,model,id,msg):
    row=db.get(model,id)
    if not row:raise HTTPException(404,msg)
    return row
def scalar(v):return str(v) if isinstance(v,Decimal) else v
def result_dict(plan,items,totals):
    item_rows=[]
    for x in items:
        row={c.name:scalar(getattr(x,c.name)) for c in x.__table__.columns};row["price_freshness"]=freshness(x.price_checked_at,settings.price_freshness_hours);item_rows.append(row)
    return {"id":plan.id,"project_id":plan.project_id,"strategy":plan.strategy,"status":plan.status,"preferred_supplier_id":plan.preferred_supplier_id,"created_at":plan.created_at,"updated_at":plan.updated_at,"items":item_rows,"supplier_totals":[{**{c.name:scalar(getattr(x,c.name)) for c in x.__table__.columns},"supplier_code":""} for x in totals],"landed_total_gross":scalar(sum((x.landed_total_gross or Decimal("0") for x in totals),Decimal("0"))) if all(x.landed_total_gross is not None for x in totals) else None}

@router.put("/projects/{project_id}/delivery-destination")
def destination(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    p=need(db,Project,project_id,"Proiectul nu există.");locality=str(payload.get("delivery_locality","")).strip();county=str(payload.get("delivery_county","")).strip()
    if not locality or not county:raise HTTPException(422,"Localitatea și județul sunt obligatorii.")
    p.delivery_address=(str(payload.get("delivery_address","")).strip() or None);p.delivery_locality=locality;p.delivery_county=county;p.delivery_country="România";p.postal_code=payload.get("postal_code");p.latitude=payload.get("latitude");p.longitude=payload.get("longitude");db.commit();return {"status":"salvat"}

@router.get("/projects/{project_id}/delivery-quotes")
def quotes(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    need(db,Project,project_id,"Proiectul nu există.");rows=db.scalars(select(DeliveryQuote).where(DeliveryQuote.project_id==project_id).order_by(DeliveryQuote.checked_at.desc()));return [{c.name:scalar(getattr(x,c.name)) for c in x.__table__.columns} for x in rows]

@router.post("/projects/{project_id}/delivery-quotes/manual",status_code=201)
def manual_quote(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    p=need(db,Project,project_id,"Proiectul nu există.");supplier=need(db,Supplier,int(payload["supplier_id"]),"Furnizorul nu există.");cost=Decimal(str(payload["delivery_cost_gross"]))
    if cost<0:raise HTTPException(422,"Transportul nu poate fi negativ.")
    until=payload.get("valid_until");until=datetime.fromisoformat(str(until).replace("Z","+00:00")) if until else None
    q=DeliveryQuote(project_id=p.id,supplier_id=supplier.id,supplier_location_id=payload.get("supplier_location_id"),source="MANUAL",destination_address=p.delivery_address,destination_locality=p.delivery_locality,destination_county=p.delivery_county,basket_subtotal_gross=Decimal(str(payload.get("basket_subtotal_gross",0))),delivery_cost_gross=cost,currency="RON",valid_from=datetime.now(timezone.utc),valid_until=until,checked_at=datetime.now(timezone.utc),notes=payload.get("notes"),active=True);db.add(q);db.commit();db.refresh(q);return {"id":q.id,"source":q.source,"delivery_cost_gross":q.delivery_cost_gross}

@router.put("/suppliers/{supplier_id}/delivery-rule")
def delivery_rule(supplier_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    need(db,Supplier,supplier_id,"Furnizorul nu există.");row=db.scalar(select(SupplierDeliveryRule).where(SupplierDeliveryRule.supplier_id==supplier_id)) or SupplierDeliveryRule(supplier_id=supplier_id)
    for key in ("minimum_order_gross","fixed_delivery_cost","free_delivery_threshold","cost_per_km","cost_per_pallet","cost_per_kg","minimum_delivery_cost"):
        value=payload.get(key);value=Decimal(str(value)) if value not in (None,"") else None
        if value is not None and value<0:raise HTTPException(422,"Regulile de transport nu pot avea valori negative.")
        setattr(row,key,value)
    row.notes=payload.get("notes");row.active=bool(payload.get("active",True));db.add(row);db.commit();return {"status":"salvat"}

def current_inputs(db,project_id,include_unknown):
    resource_lines=list(db.scalars(select(EstimateResourceLine).join(EstimateItem).join(EstimateSection).join(Level).join(Building).where(Building.project_id==project_id,EstimateResourceLine.resource_type=="MATERIAL",EstimateResourceLine.resource_id.is_not(None))))
    aggregated={}
    for line in resource_lines:
        row=aggregated.setdefault(line.resource_id,{"quantity":Decimal("0"),"unit":line.unit,"estimate_resource_id":line.id});row["quantity"]+=line.quantity
    candidates=[]
    for material_id,required in aggregated.items():
        matches=db.scalars(select(ProductMatch).where(ProductMatch.material_id==material_id,ProductMatch.approved.is_(True)))
        for match in matches:
            product=db.get(SupplierProduct,match.supplier_product_id)
            if not product or not product.active or not product.package_quantity:continue
            price=db.scalar(select(PriceObservation).where(PriceObservation.supplier_product_id==product.id,PriceObservation.success.is_(True)).order_by(PriceObservation.checked_at.desc(),PriceObservation.id.desc()).limit(1))
            if not price or price.stock_status=="OUT_OF_STOCK":continue
            supplier=db.get(Supplier,product.supplier_id)
            candidates.append(Candidate(material_id,supplier.id,supplier.code,product.id,product.supplier_sku,product.name,product.product_url,required["quantity"],required["unit"],product.package_quantity,product.package_unit or required["unit"],price.price_gross,price.checked_at,price.stock_status,product.minimum_order_quantity,product.minimum_package_count,product.whole_pallet_only))
    project=need(db,Project,project_id,"Proiectul nu există.");all_quotes=[{c.name:getattr(x,c.name) for c in x.__table__.columns} for x in db.scalars(select(DeliveryQuote).where(DeliveryQuote.project_id==project_id,DeliveryQuote.active.is_(True)))]
    deliveries={}
    for supplier in db.scalars(select(Supplier).where(Supplier.active.is_(True))):
        rule=db.scalar(select(SupplierDeliveryRule).where(SupplierDeliveryRule.supplier_id==supplier.id,SupplierDeliveryRule.active.is_(True)));estimated=None
        if rule:estimated=estimated_delivery({c.name:getattr(rule,c.name) for c in rule.__table__.columns},0)
        deliveries[supplier.id]=choose_delivery(supplier.id,all_quotes,estimated)
    return candidates,deliveries,aggregated

@router.post("/projects/{project_id}/procurement/compare")
def compare(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    include=bool(payload.get("include_unknown_delivery",False));candidates,deliveries,_=current_inputs(db,project_id,include);results=[]
    suppliers=list(db.scalars(select(Supplier).where(Supplier.code.in_(["DEDEMAN","MATHAUS"]))))
    for supplier in sorted(suppliers,key=lambda x:x.code):
        try:r=optimize(candidates,deliveries,"PREFERRED_SUPPLIER",supplier.id,include);results.append({"label":supplier.code,"strategy":"PREFERRED_SUPPLIER","landed_total_gross":r["landed_total_gross"],"supplier_totals":r["supplier_totals"]})
        except ValueError as exc:results.append({"label":supplier.code,"strategy":"PREFERRED_SUPPLIER","error":str(exc)})
    for strategy,label in (("CHEAPEST_SINGLE_SUPPLIER","CEL MAI IEFTIN FURNIZOR UNIC"),("CHEAPEST_MIXED_SUPPLIERS","MIX OPTIM")):
        try:r=optimize(candidates,deliveries,strategy,None,include);results.append({"label":label,"strategy":strategy,"landed_total_gross":r["landed_total_gross"],"supplier_totals":r["supplier_totals"]})
        except ValueError as exc:results.append({"label":label,"strategy":strategy,"error":str(exc)})
    totals=[Decimal(str(x["landed_total_gross"])) for x in results if x.get("landed_total_gross") is not None];baseline=max(totals) if totals else None;best=min(totals) if totals else None
    estimate=sum((x.subtotal_gross for x in db.scalars(select(EstimateResourceLine).join(EstimateItem).join(EstimateSection).join(Level).join(Building).where(Building.project_id==project_id,EstimateResourceLine.resource_type=="MATERIAL"))),Decimal("0"))
    return {"results":results,"estimate_material_budget":estimate,"best_landed_total":best,"savings":(baseline-best if baseline is not None else None),"savings_percent":((baseline-best)*100/baseline if baseline else None)}

@router.post("/projects/{project_id}/procurement/calculate",status_code=201)
def calculate(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    strategy=payload.get("strategy","CHEAPEST_MIXED_SUPPLIERS");include=bool(payload.get("include_unknown_delivery",False));candidates,deliveries,aggregated=current_inputs(db,project_id,include)
    try:result=optimize(candidates,deliveries,strategy,payload.get("preferred_supplier_id"),include,{int(k):int(v) for k,v in payload.get("product_overrides",{}).items()},{int(k):int(v) for k,v in payload.get("package_overrides",{}).items()},{int(k):int(v) for k,v in payload.get("supplier_overrides",{}).items()})
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    plan=ProcurementPlan(project_id=project_id,strategy=strategy,preferred_supplier_id=payload.get("preferred_supplier_id"),status="CALCULATED",include_unknown_delivery=include);db.add(plan);db.flush()
    suppliers={x.id:x for x in db.scalars(select(Supplier))}
    for x in result["items"]:
        data={k:v for k,v in x.items() if k not in {"supplier_code"}};data["estimate_resource_id"]=aggregated[x["material_id"]]["estimate_resource_id"];data["procurement_plan_id"]=plan.id;data["supplier_name"]=suppliers[x["supplier_id"]].name;db.add(ProcurementPlanItem(**data))
    for x in result["supplier_totals"]:db.add(ProcurementPlanSupplierTotal(procurement_plan_id=plan.id,**{k:v for k,v in x.items() if k!="supplier_code"}))
    db.commit();return get_plan(project_id,plan.id,db,_)

@router.get("/projects/{project_id}/procurement/plans")
def plans(project_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    return [{c.name:scalar(getattr(x,c.name)) for c in x.__table__.columns} for x in db.scalars(select(ProcurementPlan).where(ProcurementPlan.project_id==project_id).order_by(ProcurementPlan.created_at.desc()))]

@router.get("/projects/{project_id}/procurement/plans/{plan_id}")
def get_plan(project_id:int,plan_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    plan=need(db,ProcurementPlan,plan_id,"Planul nu există.")
    if plan.project_id!=project_id:raise HTTPException(404,"Planul nu există.")
    items=list(db.scalars(select(ProcurementPlanItem).where(ProcurementPlanItem.procurement_plan_id==plan.id)));totals=list(db.scalars(select(ProcurementPlanSupplierTotal).where(ProcurementPlanSupplierTotal.procurement_plan_id==plan.id)));result=result_dict(plan,items,totals)
    for t in result["supplier_totals"]:t["supplier_code"]=db.get(Supplier,t["supplier_id"]).code
    result["newer_prices_available"]=any((db.scalar(select(PriceObservation.checked_at).where(PriceObservation.supplier_product_id==item.supplier_product_id,PriceObservation.success.is_(True)).order_by(PriceObservation.checked_at.desc(),PriceObservation.id.desc()).limit(1)) or item.price_checked_at)>item.price_checked_at for item in items)
    return result

@router.post("/projects/{project_id}/procurement/plans/{plan_id}/lock")
def lock(project_id:int,plan_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    plan=need(db,ProcurementPlan,plan_id,"Planul nu există.")
    if plan.project_id!=project_id:raise HTTPException(404,"Planul nu există.")
    if plan.status=="LOCKED":return {"status":"LOCKED"}
    if plan.status!="CALCULATED":raise HTTPException(409,"Numai un plan calculat poate fi blocat.")
    plan.status="LOCKED";db.commit();return {"status":"LOCKED"}

@router.get("/projects/{project_id}/procurement/plans/{plan_id}/export.{format}")
def export(project_id:int,plan_id:int,format:str,db:Session=Depends(get_db),_:User=Depends(current_user)):
    data=get_plan(project_id,plan_id,db,_)
    if format=="xlsx":return Response(shopping_xlsx(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="lista-cumparaturi-{plan_id}.xlsx"'})
    if format=="pdf":return Response(shopping_pdf(data),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="lista-cumparaturi-{plan_id}.pdf"'})
    raise HTTPException(404,"Format necunoscut.")
