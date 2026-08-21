from decimal import Decimal
from sqlalchemy import select,func
from app.catalogue import seed_catalogue
from app.models import WorkCategory,WorkItem,WorkRecipe,RecipeResource,Material,LaborResource,EstimateSnapshotLine

def hierarchy(c):
    p=c.post("/api/projects",json={"name":"Catalog"}).json();b=c.post(f"/api/projects/{p['id']}/buildings",json={"name":"Corp"}).json();l=c.post(f"/api/buildings/{b['id']}/levels",json={"name":"Parter"}).json();s=c.post(f"/api/levels/{l['id']}/sections",json={"code":"05","name":"Zidărie"}).json();return p,s

def test_seed_idempotency_and_counts(authenticated_client,db):
    first=seed_catalogue(db); second=seed_catalogue(db)
    assert first==second=={"catalogue_version":"2026.08","categories":20,"materials":15,"labor":8,"works":51,"recipes":9}
    assert db.scalar(select(func.count()).select_from(WorkCategory))==20
    assert db.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.description.like("Coeficienții%")))==51
    assert db.scalar(select(func.count()).select_from(WorkRecipe))==9

def test_standard_update_preserves_custom_catalogue(authenticated_client,db):
    custom=WorkItem(code="CUSTOM-01",name="Lucrare companie",category="Companie",unit="m2",active=True);db.add(custom);db.commit()
    r=authenticated_client.post("/api/catalog/admin/reset-standard");assert r.status_code==200
    db.refresh(custom);assert custom.active is True

def test_catalogue_export_import(authenticated_client):
    c=authenticated_client; exported=c.get("/api/catalog/admin/export");assert exported.status_code==200
    data=exported.json();assert data["schema_version"]=="1" and len(data["categories"])==20 and len(data["works"])>=51
    imported=c.post("/api/catalog/admin/import",json=data);assert imported.status_code==200
    assert imported.json()["works"]>=51

def test_work_to_estimate_pins_recipe_and_generates_resources(authenticated_client):
    c=authenticated_client;p,s=hierarchy(c);work=next(x for x in c.get("/api/catalog/work-items").json() if x["code"]=="05.025")
    created=c.post(f"/api/sections/{s['id']}/items/from-catalog",json={"work_item_id":work["id"],"code":"05.025.1","quantity":"10","waste_percent":"0"});assert created.status_code==201
    item=created.json();assert item["pinned_recipe_id"] is not None
    lines=c.get(f"/api/estimate-items/{item['id']}/resources").json();assert len(lines)==3
    assert Decimal(str(next(x for x in lines if x["description"]=="BCA 25 cm")["quantity"]))==Decimal("2.625")
    old_recipe=item["pinned_recipe_id"]
    new=c.post("/api/recipes",json={"work_item_id":work["id"],"scope":"COMPANY_OVERRIDE","version":2}).json()
    labor=next(x for x in c.get("/api/catalog/labor").json() if x["code"]=="STD-MAN-ZIDAR")
    c.post(f"/api/recipes/{new['id']}/resources",json={"resource_type":"LABOR","resource_id":labor["id"],"quantity_per_unit":"99","waste_percent":"0","unit":"ora"})
    c.post(f"/api/estimate-items/{item['id']}/resources/generate")
    regenerated=c.get(f"/api/estimate-items/{item['id']}/resources").json();assert len(regenerated)==3
    assert c.get(f"/api/sections/{s['id']}/items").json()[0]["pinned_recipe_id"]==old_recipe

def test_geometry_catalogue_recipe_recalculation(authenticated_client):
    c=authenticated_client;p,s=hierarchy(c);work=next(x for x in c.get("/api/catalog/work-items").json() if x["code"]=="05.025")
    item=c.post(f"/api/sections/{s['id']}/items/from-catalog",json={"work_item_id":work["id"],"code":"GEO-ZID","quantity":"1"}).json()
    geo=c.post(f"/api/projects/{p['id']}/geometry",json={"estimate_item_id":item["id"],"geometry_type":"ROOM","name":"Camera","input_data":{"length_m":"5","width_m":"4","height_m":"2.8","openings":[]},"selected_result":"net_wall_area_m2","waste_percent":"0"}).json()
    before=c.get(f"/api/estimate-items/{item['id']}/resources").json();bca=next(x for x in before if x["description"]=="BCA 25 cm");assert Decimal(str(bca["quantity"]))==Decimal("13.23")
    payload={"estimate_item_id":item["id"],"geometry_type":"ROOM","name":"Camera","input_data":{"length_m":"6","width_m":"4","height_m":"2.8","openings":[]},"selected_result":"net_wall_area_m2","waste_percent":"0"}
    assert c.put(f"/api/geometry/{geo['id']}",json=payload).status_code==200
    after=c.get(f"/api/estimate-items/{item['id']}/resources").json();assert Decimal(str(next(x for x in after if x["description"]=="BCA 25 cm")["quantity"]))==Decimal("14.70")
