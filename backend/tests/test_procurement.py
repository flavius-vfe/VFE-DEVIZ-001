from datetime import datetime,timezone,timedelta
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
import pytest
from sqlalchemy import select
from app.procurement import Candidate,Delivery,basket,choose_delivery,estimated_delivery,freshness,optimize,packages
from app.procurement_exports import shopping_pdf,shopping_xlsx
from app.models import Material,Supplier,ProcurementPlan,PriceObservation,EstimateResourceLine
D=Decimal;NOW=datetime(2026,8,21,tzinfo=timezone.utc)
def c(mid,sid,code,price,stock="IN_STOCK",age=1,product_id=None):return Candidate(mid,sid,code,product_id or mid*10+sid,f"SKU-{mid}-{sid}",f"Produs {mid} {code}",f"https://example.ro/{mid}",D("10"),"kg",D("3"),"kg",D(str(price)),NOW-timedelta(hours=age),stock)

def test_landed_cost_and_one_delivery_per_supplier():
    result=basket([c(1,1,"DEDEMAN",10),c(2,1,"DEDEMAN",20)],{1:Delivery(1,D("50"),"MANUAL")})
    assert result["supplier_totals"][0]["delivery_cost_gross"]==50
    assert result["landed_total_gross"]==D("170.00")

def test_preferred_supplier_with_fallback():
    rows=[c(1,1,"DEDEMAN",10),c(1,2,"MATHAUS",9),c(2,2,"MATHAUS",11)]
    out=optimize(rows,{1:Delivery(1,D("5")),2:Delivery(2,D("5"))},"PREFERRED_SUPPLIER",1)
    assert [x["supplier_code"] for x in out["items"]]==["DEDEMAN","MATHAUS"]

def test_cheapest_single_delivery_changes_winner_mandatory_edge():
    rows=[c(1,1,"DEDEMAN",10),c(2,1,"DEDEMAN",10),c(1,2,"MATHAUS",11),c(2,2,"MATHAUS",11)]
    out=optimize(rows,{1:Delivery(1,D("100")),2:Delivery(2,D("5"))},"CHEAPEST_SINGLE_SUPPLIER")
    assert {x["supplier_code"] for x in out["items"]}=={"MATHAUS"}

def test_cheapest_mixed_accounts_for_delivery_and_is_deterministic():
    rows=[c(1,1,"DEDEMAN",5),c(1,2,"MATHAUS",6),c(2,1,"DEDEMAN",20),c(2,2,"MATHAUS",5)]
    deliveries={1:Delivery(1,D("20")),2:Delivery(2,D("20"))}
    first=optimize(rows,deliveries,"CHEAPEST_MIXED_SUPPLIERS");second=optimize(list(reversed(rows)),deliveries,"CHEAPEST_MIXED_SUPPLIERS")
    assert first["landed_total_gross"]==second["landed_total_gross"]
    assert [x["supplier_code"] for x in first["items"]]==[x["supplier_code"] for x in second["items"]]

def test_four_supplier_branch_and_bound_exact_result():
    codes=["DEDEMAN","MATHAUS","LEROY_MERLIN","HORNBACH"]
    rows=[c(mid,sid,code,5+((mid*sid)%7)) for mid in range(1,13) for sid,code in enumerate(codes,1)]
    deliveries={sid:Delivery(sid,D(str(10*sid))) for sid in range(1,5)}
    first=optimize(rows,deliveries);second=optimize(list(reversed(rows)),deliveries)
    assert first["optimization_method"]=="BRANCH_AND_BOUND"
    assert first["landed_total_gross"]==second["landed_total_gross"]
    assert [(x["material_id"],x["supplier_id"]) for x in first["items"]]==[(x["material_id"],x["supplier_id"]) for x in second["items"]]

def test_unknown_delivery_default_off_and_optional_on():
    rows=[c(1,1,"DEDEMAN",5)]
    with pytest.raises(ValueError,match="transport cunoscut"):optimize(rows,{1:Delivery(1,None)},include_unknown=False)
    assert optimize(rows,{1:Delivery(1,None)},include_unknown=True)["delivery_known"] is False

def test_stale_unknown_and_current_prices():
    assert freshness(NOW-timedelta(hours=6),72,NOW)["status"]=="ACTUAL"
    assert freshness(NOW-timedelta(days=4),72,NOW)["status"]=="STALE"
    assert freshness(None,72,NOW)["status"]=="UNKNOWN"

def test_out_of_stock_exclusion_and_unknown_allowed():
    rows=[c(1,1,"DEDEMAN",1,"OUT_OF_STOCK"),c(1,2,"MATHAUS",2,"UNKNOWN")]
    out=optimize(rows,{2:Delivery(2,D("0"))});assert out["items"][0]["supplier_code"]=="MATHAUS"

def test_package_pallet_rounding_and_manual_override():
    row=c(1,1,"DEDEMAN",10);assert packages(row)[0]==4
    pallet=Candidate(**{**row.__dict__,"package_quantity":D("48"),"required_quantity":D("49"),"whole_pallet_only":True,"minimum_packages":2})
    assert packages(pallet)[0]==2 and packages(row,6)[0]==6
    with pytest.raises(ValueError):packages(row,2)

def test_delivery_rule_and_manual_override_priority_math():
    rule={"supplier_id":1,"fixed_delivery_cost":"20","cost_per_pallet":"5","minimum_delivery_cost":"30","active":True}
    assert estimated_delivery(rule,100,pallets=1).cost==D("30.00")
    rule["free_delivery_threshold"]="100";assert estimated_delivery(rule,100).cost==0
    quotes=[{"supplier_id":1,"source":"RETAILER","delivery_cost_gross":"10","checked_at":NOW,"active":True},{"supplier_id":1,"source":"MANUAL","delivery_cost_gross":"30","checked_at":NOW,"active":True}]
    assert choose_delivery(1,quotes).source=="MANUAL" and choose_delivery(1,quotes).cost==30

def test_supplier_product_and_package_manual_overrides_are_marked():
    rows=[c(1,1,"DEDEMAN",5,product_id=11),c(1,2,"MATHAUS",6,product_id=12)]
    out=optimize(rows,{1:Delivery(1,D("0")),2:Delivery(2,D("0"))},supplier_overrides={1:2},package_overrides={1:5})
    assert out["items"][0]["supplier_product_id"]==12 and out["items"][0]["packages_to_buy"]==5 and out["items"][0]["manual_override"]

def export_data():return {"strategy":"CHEAPEST_MIXED_SUPPLIERS","landed_total_gross":"120.00","supplier_totals":[{"supplier_id":1,"supplier_code":"Dedeman","subtotal_gross":"100","delivery_cost_gross":"20","landed_total_gross":"120"}],"items":[{"supplier_id":1,"supplier_code":"Dedeman","material_id":1,"product_name":"Adeziv","supplier_sku":"SKU1","required_quantity":"10","required_unit":"kg","package_quantity":"25","package_unit":"kg","packages_to_buy":1,"purchased_quantity":"25","unit_package_price_gross":"100","product_subtotal_gross":"100","stock_status":"IN_STOCK","price_checked_at":"2026-08-21","product_url":"https://www.dedeman.ro/p"}]}
def test_pdf_and_xlsx_data_correctness():
    pdf=shopping_pdf(export_data());assert pdf.startswith(b"%PDF-1.4") and b"SKU1" in pdf
    xlsx=shopping_xlsx(export_data());z=ZipFile(BytesIO(xlsx));workbook=z.read("xl/workbook.xml").decode();assert all(x in workbook for x in ["Rezumat","Dedeman","MatHaus","Materiale","Comparație"]);assert b"Adeziv" in z.read("xl/worksheets/sheet2.xml")

def test_procurement_api_lock_and_new_plan_after_price_refresh(authenticated_client,db):
    cclient=authenticated_client;project=cclient.post("/api/projects",json={"name":"Achiziții"}).json();building=cclient.post(f"/api/projects/{project['id']}/buildings",json={"name":"Corp"}).json();level=cclient.post(f"/api/buildings/{building['id']}/levels",json={"name":"Parter"}).json();section=cclient.post(f"/api/levels/{level['id']}/sections",json={"code":"01","name":"Materiale"}).json();item=cclient.post(f"/api/sections/{section['id']}/items",json={"code":"A","description":"Adeziv","unit":"kg","quantity":"10","waste_percent":"0"}).json();material=db.scalar(select(Material).limit(1));db.add(EstimateResourceLine(estimate_item_id=item["id"],source="MANUAL",resource_type="MATERIAL",resource_id=material.id,description=material.name,unit="kg",quantity=10,waste_percent=0,unit_price_net=1,vat_rate=21,vat_amount=2.1,unit_price_gross=1.21,subtotal_net=10,subtotal_gross=12.1));db.commit()
    product=cclient.post("/api/suppliers/import-fixture",json={"fixture":"dedeman_adeziv.html"}).json();cclient.post(f"/api/catalog/materials/{material.id}/products/{product['id']}/match",json={"approved":True});supplier=db.scalar(select(Supplier).where(Supplier.code=="DEDEMAN"));cclient.post(f"/api/projects/{project['id']}/delivery-quotes/manual",json={"supplier_id":supplier.id,"delivery_cost_gross":"20"})
    plan=cclient.post(f"/api/projects/{project['id']}/procurement/calculate",json={"strategy":"CHEAPEST_SINGLE_SUPPLIER"});assert plan.status_code==201,plan.text;old=plan.json();assert cclient.post(f"/api/projects/{project['id']}/procurement/plans/{old['id']}/lock").json()["status"]=="LOCKED"
    cclient.post("/api/suppliers/import-fixture",json={"fixture":"dedeman_adeziv.html"});new=cclient.post(f"/api/projects/{project['id']}/procurement/calculate",json={"strategy":"CHEAPEST_SINGLE_SUPPLIER"}).json();assert new["id"]!=old["id"];assert cclient.get(f"/api/projects/{project['id']}/procurement/plans/{old['id']}").json()["status"]=="LOCKED"
    assert cclient.get(f"/api/projects/{project['id']}/procurement/plans/{old['id']}/export.xlsx").status_code==200
