from decimal import Decimal
import pytest
from app.geometry import room, foundation, slab, beam, column, rebar, stirrups, mesh, roof, wall
from app.models import EstimateVersion, EstimateSnapshotLine

D=Decimal

def test_room_openings_and_skirting():
    result=room({"length_m":"5","width_m":"4","height_m":"2.8","openings":[{"type":"DOOR","width_m":"0.9","height_m":"2.1","quantity":"1"},{"type":"WINDOW","width_m":"1.2","height_m":"1.4","quantity":"2"}]})
    assert result["floor_area_m2"]==D("20")
    assert result["perimeter_m"]==D("18")
    assert result["gross_wall_area_m2"]==D("50.4")
    assert result["opening_area_m2"]==D("5.25")
    assert result["net_wall_area_m2"]==D("45.15")
    assert result["skirting_length_m"]==D("17.1")

def test_wall_validation_and_volume():
    assert wall({"length_m":"10","height_m":"3","thickness_m":"0.25","openings":[]})["volume_m3"]==D("7.50")
    with pytest.raises(ValueError,match="golurilor"): wall({"length_m":"1","height_m":"1","thickness_m":".2","openings":[{"type":"DOOR","width_m":"2","height_m":"2","quantity":1}]})

def test_foundation_slab_beam_column():
    f=foundation({"length_m":"10","excavation_width_m":"0.8","excavation_depth_m":"1.2","concrete_width_m":"0.5","concrete_height_m":"0.8","blinding_thickness_m":"0.1"})
    assert f=={"excavation_m3":D("9.60"),"concrete_m3":D("4.00"),"blinding_concrete_m3":D("0.80"),"side_formwork_m2":D("16.0")}
    s=slab({"length_m":"10","width_m":"8","thickness_m":"0.15"}); assert s["concrete_volume_m3"]==D("12.00") and s["bottom_formwork_m2"]==D("80")
    b=beam({"length_m":"5","width_m":".3","height_m":".5","quantity":2,"exposed_faces":["bottom","side_left","side_right","ends"]}); assert b["concrete_volume_m3"]==D("1.50") and b["formwork_area_m2"]==D("13.60")
    c=column({"width_m":".4","depth_m":".3","height_m":"3","quantity":4}); assert c["concrete_volume_m3"]==D("1.44") and c["formwork_area_m2"]==D("16.8")

def test_rebar_laps_hooks_waste_and_precision():
    r=rebar({"diameter_mm":12,"bar_length_m":"6.123456","quantity":10,"lap_allowance_m":".6","hook_allowance_m":".2","waste_percent":"5"})
    assert r["kg_per_m"]==D("144")/D("162")
    assert r["total_length_m"]==D("69.234560")
    assert r["total_weight_kg"]==r["base_weight_kg"]*D("1.05")
    with pytest.raises(ValueError,match="diametrul|Diametrul"): rebar({"diameter_mm":7,"bar_length_m":1,"quantity":1})

def test_stirrups_count_cutting_and_weight():
    r=stirrups({"beam_length_m":"5","beam_width_m":".3","beam_height_m":".5","concrete_cover_mm":25,"stirrup_diameter_mm":8,"spacing_mm":200,"hook_length_m":".1"})
    assert r["number_of_stirrups"]==D("26")
    assert r["cutting_length_m"]==D("1.6")
    assert r["total_length_m"]==D("41.6")
    assert r["total_weight_kg"]==D("41.6")*D("64")/D("162")

def test_mesh_layout_overlap_layers_and_weight():
    r=mesh({"coverage_length_m":"8","coverage_width_m":"5","sheet_length_m":"5","sheet_width_m":"2","overlap_x_m":".5","overlap_y_m":".2","layers":2,"weight_kg_per_sheet":"20","waste_percent":"5"})
    assert r["sheets_x"]==2 and r["sheets_y"]==3
    assert r["total_sheets"]==D("13") and r["total_weight_kg"]==D("260")

def test_gable_roof():
    r=roof({"building_length_m":"10","building_width_m":"8","pitch_degrees":"30","eave_overhang_m":".5","gable_overhang_m":".3"})
    assert r["ridge_length_m"]==D("10.6") and r["eave_length_m"]==D("21.2")
    assert r["slope_length_m"].quantize(D(".001"))==D("5.196")
    assert r["total_roof_surface_m2"].quantize(D(".01"))==D("110.16")

def make_hierarchy(c):
    p=c.post("/api/projects",json={"name":"Geometrie"}).json(); b=c.post(f"/api/projects/{p['id']}/buildings",json={"name":"Corp"}).json(); l=c.post(f"/api/buildings/{b['id']}/levels",json={"name":"Parter"}).json(); s=c.post(f"/api/levels/{l['id']}/sections",json={"code":"01","name":"Finisaje"}).json(); return p,s

def test_geometry_sync_recipe_recalculation_and_snapshot_immutability(authenticated_client,db):
    c=authenticated_client; p,s=make_hierarchy(c)
    labor=c.post("/api/catalog/labor",json={"code":"MAN-GEO","name":"Zugrav","unit":"ora","rate_net":"50","vat_rate":"21","active":True}).json(); work=c.post("/api/catalog/work-items",json={"code":"LC-GEO","name":"Vopsire","category":"Finisaje","unit":"m2","active":True}).json(); recipe=c.post("/api/recipes",json={"work_item_id":work["id"],"scope":"STANDARD","version":1}).json(); c.post(f"/api/recipes/{recipe['id']}/resources",json={"resource_type":"LABOR","resource_id":labor["id"],"quantity_per_unit":"0.5","waste_percent":"0","unit":"ora"})
    item=c.post(f"/api/sections/{s['id']}/items",json={"code":"01.1","description":"Vopsea","unit":"m2","quantity":"1","work_item_id":work["id"]}).json()
    version=EstimateVersion(project_id=p["id"],version=1,total_net=D("10"),vat_total=D("2.1"),total_gross=D("12.1")); db.add(version); db.flush(); snap=EstimateSnapshotLine(estimate_version_id=version.id,source_item_id=item["id"],resource_type="LABOR",description="Istoric",unit="ora",quantity=D("1"),unit_price_net=D("10"),vat_rate=D("21"),unit_price_gross=D("12.1"),total_gross=D("12.1")); db.add(snap); db.commit()
    payload={"estimate_item_id":item["id"],"geometry_type":"ROOM","name":"Camera 1","input_data":{"length_m":"5","width_m":"4","height_m":"2.8","openings":[]},"selected_result":"net_wall_area_m2","waste_percent":"5"}
    created=c.post(f"/api/projects/{p['id']}/geometry",json=payload); assert created.status_code==201
    assert D(str(c.get(f"/api/sections/{s['id']}/items").json()[0]["quantity"]))==D("52.920")
    lines=c.get(f"/api/estimate-items/{item['id']}/resources").json(); assert D(str(lines[0]["quantity"]))==D("26.46")
    payload["input_data"]["length_m"]="6"; updated=c.put(f"/api/geometry/{created.json()['id']}",json=payload); assert updated.status_code==200
    assert D(str(c.get(f"/api/sections/{s['id']}/items").json()[0]["quantity"]))==D("58.800")
    db.refresh(snap); assert snap.quantity==D("1") and snap.total_gross==D("12.1")
