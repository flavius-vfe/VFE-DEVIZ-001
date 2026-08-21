from __future__ import annotations
from dataclasses import dataclass,replace
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_CEILING
from itertools import product
from .calc import money
D=Decimal

@dataclass(frozen=True)
class Candidate:
    material_id:int;supplier_id:int;supplier_code:str;product_id:int;sku:str;name:str;url:str
    required_quantity:Decimal;required_unit:str;package_quantity:Decimal;package_unit:str;package_price:Decimal
    checked_at:datetime;stock_status:str="UNKNOWN";minimum_order_quantity:Decimal|None=None;minimum_packages:int=1;whole_pallet_only:bool=False;manual_override:bool=False

@dataclass(frozen=True)
class Delivery:
    supplier_id:int;cost:Decimal|None;source:str="UNKNOWN"

def freshness(checked_at:datetime|None,hours=72,now=None):
    if not checked_at:return {"status":"UNKNOWN","hours":None}
    now=now or datetime.now(timezone.utc);checked=checked_at if checked_at.tzinfo else checked_at.replace(tzinfo=timezone.utc);age=max(D("0"),D(str((now-checked).total_seconds()/3600)))
    return {"status":"ACTUAL" if age<=hours else "STALE","hours":age.quantize(D("0.1"))}

def packages(candidate:Candidate,override:int|None=None):
    required=max(candidate.required_quantity,candidate.minimum_order_quantity or D("0"));count=int((required/candidate.package_quantity).to_integral_value(rounding=ROUND_CEILING));count=max(count,candidate.minimum_packages)
    if override is not None:
        if override<count:raise ValueError("Numărul manual de pachete nu poate acoperi necesarul.")
        count=override
    purchased=candidate.package_quantity*count
    return count,purchased,purchased-candidate.required_quantity,money(candidate.package_price*count)

def estimated_delivery(rule,subtotal,weight=None,pallets=None,distance_km=None):
    subtotal=D(str(subtotal));
    if not rule or not rule.get("active",True):return Delivery(int(rule.get("supplier_id",0)) if rule else 0,None,"UNKNOWN")
    if rule.get("minimum_order_gross") is not None and subtotal<D(str(rule["minimum_order_gross"])):return Delivery(int(rule["supplier_id"]),None,"UNKNOWN")
    if rule.get("free_delivery_threshold") is not None and subtotal>=D(str(rule["free_delivery_threshold"])):cost=D("0")
    else:
        values=[]
        if rule.get("fixed_delivery_cost") is not None:values.append(D(str(rule["fixed_delivery_cost"])))
        if distance_km is not None and rule.get("cost_per_km") is not None:values.append(D(str(distance_km))*D(str(rule["cost_per_km"])))
        if pallets is not None and rule.get("cost_per_pallet") is not None:values.append(D(str(pallets))*D(str(rule["cost_per_pallet"])))
        if weight is not None and rule.get("cost_per_kg") is not None:values.append(D(str(weight))*D(str(rule["cost_per_kg"])))
        if not values:return Delivery(int(rule["supplier_id"]),None,"UNKNOWN")
        cost=sum(values,D("0"))
    if cost>0 and rule.get("minimum_delivery_cost") is not None:cost=max(cost,D(str(rule["minimum_delivery_cost"])))
    return Delivery(int(rule["supplier_id"]),money(cost),"ESTIMATED")

def choose_delivery(supplier_id,quotes,estimated=None,now=None):
    now=now or datetime.now(timezone.utc)
    def aware(value):return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    valid=[q for q in quotes if q["supplier_id"]==supplier_id and q.get("active",True) and (not q.get("valid_from") or aware(q["valid_from"])<=now) and (not q.get("valid_until") or aware(q["valid_until"])>=now) and q.get("delivery_cost_gross") is not None]
    priority={"MANUAL":3,"RETAILER":2,"ESTIMATED":1};valid.sort(key=lambda q:(priority.get(q.get("source"),0),q.get("checked_at") or datetime.min.replace(tzinfo=timezone.utc)),reverse=True)
    if valid:return Delivery(supplier_id,D(str(valid[0]["delivery_cost_gross"])),valid[0]["source"])
    return estimated or Delivery(supplier_id,None,"UNKNOWN")

def _line(candidate,override=None):
    count,bought,unused,subtotal=packages(candidate,override)
    return {"material_id":candidate.material_id,"supplier_id":candidate.supplier_id,"supplier_code":candidate.supplier_code,"supplier_product_id":candidate.product_id,"supplier_sku":candidate.sku,"product_name":candidate.name,"product_url":candidate.url,"required_quantity":candidate.required_quantity,"required_unit":candidate.required_unit,"package_quantity":candidate.package_quantity,"package_unit":candidate.package_unit,"packages_to_buy":count,"purchased_quantity":bought,"unused_quantity":unused,"unit_package_price_gross":candidate.package_price,"product_subtotal_gross":subtotal,"price_checked_at":candidate.checked_at,"stock_status":candidate.stock_status,"manual_override":candidate.manual_override or override is not None}

def basket(assignment,deliveries,include_unknown=False,package_overrides=None):
    package_overrides=package_overrides or {};lines=[_line(c,package_overrides.get(c.material_id)) for c in assignment];totals=[]
    for sid in sorted({x["supplier_id"] for x in lines}):
        selected=[x for x in lines if x["supplier_id"]==sid];subtotal=money(sum((x["product_subtotal_gross"] for x in selected),D("0")));delivery=deliveries.get(sid,Delivery(sid,None,"UNKNOWN"));landed=money(subtotal+delivery.cost) if delivery.cost is not None else None
        totals.append({"supplier_id":sid,"supplier_code":selected[0]["supplier_code"],"product_count":len(selected),"subtotal_gross":subtotal,"delivery_cost_gross":delivery.cost,"delivery_source":delivery.source,"landed_total_gross":landed})
    known=all(x["landed_total_gross"] is not None for x in totals);total=money(sum((x["landed_total_gross"] or x["subtotal_gross"] for x in totals),D("0"))) if known or include_unknown else None
    return {"items":lines,"supplier_totals":totals,"landed_total_gross":total,"delivery_known":known}

def optimize(candidates,deliveries,strategy="CHEAPEST_MIXED_SUPPLIERS",preferred_supplier_id=None,include_unknown=False,product_overrides=None,package_overrides=None,supplier_overrides=None):
    product_overrides=product_overrides or {};supplier_overrides=supplier_overrides or {};eligible=[c for c in candidates if c.stock_status!="OUT_OF_STOCK"]
    grouped={};
    for c in eligible:grouped.setdefault(c.material_id,[]).append(c)
    if not grouped:raise ValueError("Nu există materiale eligibile pentru aprovizionare.")
    for mid,rows in grouped.items():
        if mid in supplier_overrides:grouped[mid]=[replace(c,manual_override=True) for c in rows if c.supplier_id==supplier_overrides[mid]];rows=grouped[mid]
        if mid in product_overrides:grouped[mid]=[replace(c,manual_override=True) for c in rows if c.product_id==product_overrides[mid]]
        if not grouped[mid]:raise ValueError(f"Override invalid pentru materialul {mid}.")
        grouped[mid]=sorted(grouped[mid],key=lambda c:(c.package_price,c.supplier_code,c.product_id))
    materials=sorted(grouped);assignments=[]
    if strategy=="PREFERRED_SUPPLIER":
        assignment=[]
        for m in materials:
            preferred=[c for c in grouped[m] if c.supplier_id==preferred_supplier_id];pool=preferred or grouped[m];assignment.append(min(pool,key=lambda c:(packages(c)[3],c.supplier_code,c.product_id)))
        assignments=[assignment]
    elif strategy=="CHEAPEST_SINGLE_SUPPLIER":
        for sid in sorted({c.supplier_id for c in eligible}):
            if all(any(c.supplier_id==sid for c in grouped[m]) for m in materials):assignments.append([min((c for c in grouped[m] if c.supplier_id==sid),key=lambda c:(packages(c)[3],c.product_id)) for m in materials])
    elif strategy=="CHEAPEST_MIXED_SUPPLIERS":
        options=[[min((c for c in rows if c.supplier_id==sid),key=lambda c:(packages(c)[3],c.product_id)) for sid in sorted({x.supplier_id for x in rows})] for rows in (grouped[m] for m in materials)]
        if len(options)>22:raise ValueError("Prea multe materiale pentru evaluarea exactă; împărțiți planul.")
        assignments=product(*options)
    else:raise ValueError("Strategie de aprovizionare invalidă.")
    results=[]
    for a in assignments:
        result=basket(list(a),deliveries,include_unknown,package_overrides)
        if result["landed_total_gross"] is not None:
            fresh=sum((int(c.checked_at.timestamp()) for c in a));codes=tuple(sorted({c.supplier_code for c in a}));preferred_penalty=0 if preferred_supplier_id in {c.supplier_id for c in a} else 1
            results.append((result["landed_total_gross"],len(codes),-fresh,preferred_penalty,codes,result))
    if not results:raise ValueError("Niciun coș complet nu are transport cunoscut.")
    return min(results,key=lambda x:x[:-1])[-1]
