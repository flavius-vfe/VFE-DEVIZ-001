from decimal import Decimal
import pytest
from app.estimation import (
    aggregate_totals, calculate_cost, convert_unit, gross_from_net_exact,
    net_from_gross_exact, recipe_quantity,
)

def test_recipe_quantity_waste_and_decimal_precision():
    assert recipe_quantity("12.345678", "0.333333", "7.5") == Decimal("4.423864")
    assert recipe_quantity("10", "2.5", "10") == Decimal("27.500000")

def test_cost_vat_and_net_gross_conversion():
    assert gross_from_net_exact("100", "21") == Decimal("121.0000")
    assert net_from_gross_exact("121", "21") == Decimal("100.0000")
    cost = calculate_cost("3.333333", "12.3456", "21")
    assert cost.subtotal_net == Decimal("41.15")
    assert cost.subtotal_gross == Decimal("49.79")
    assert cost.vat_amount == Decimal("8.64")

def test_unit_conversions():
    assert convert_unit("1.25", "tona", "kg") == Decimal("1250.000000")
    assert convert_unit("750", "kg", "tona") == Decimal("0.750000")
    assert convert_unit("2", "sac", "sac") == Decimal("2.000000")
    with pytest.raises(ValueError):
        convert_unit("1", "m2", "kg")

def test_totals_aggregation():
    totals = aggregate_totals([
        {"resource_type": "MATERIAL", "subtotal_net": Decimal("100.01"), "subtotal_gross": Decimal("121.01")},
        {"resource_type": "LABOR", "subtotal_net": Decimal("50.00"), "subtotal_gross": Decimal("60.50")},
    ])
    assert totals["MATERIAL"] == Decimal("121.01")
    assert totals["LABOR"] == Decimal("60.50")
    assert totals["total_net"] == Decimal("150.01")
    assert totals["vat"] == Decimal("31.50")
    assert totals["total_gross"] == Decimal("181.51")

def hierarchy(client, project_id, work_item_id):
    building = client.post(f"/api/projects/{project_id}/buildings", json={"name":"Corp"}).json()
    level = client.post(f"/api/buildings/{building['id']}/levels", json={"name":"Parter"}).json()
    section = client.post(f"/api/levels/{level['id']}/sections", json={"code":"01","name":"Structură"}).json()
    return client.post(f"/api/sections/{section['id']}/items", json={"code":"01.1","description":"Lucrare","unit":"m3","quantity":"10","work_item_id":work_item_id}).json()

def test_catalog_recipe_project_override_generation_and_totals(authenticated_client):
    c = authenticated_client
    project = c.post("/api/projects", json={"name":"Deviz resurse"}).json()
    material = c.post("/api/catalog/materials", json={"code":"MAT-CEM","name":"Ciment generic","category":"Lianți","base_unit":"sac","attributes":{"greutate_kg":"40"},"active":True}).json()
    labor = c.post("/api/catalog/labor", json={"code":"MAN-ZID","name":"Zidar","unit":"ora","rate_net":"50.1234","vat_rate":"21","active":True}).json()
    equipment = c.post("/api/catalog/equipment", json={"code":"UT-BET","name":"Betonieră","unit":"ora","rate_net":"20","vat_rate":"21","active":True}).json()
    work = c.post("/api/catalog/work-items", json={"code":"LC-BET","name":"Turnare beton","category":"Beton","unit":"m3","active":True}).json()

    standard = c.post("/api/recipes", json={"work_item_id":work["id"],"scope":"STANDARD","version":1}).json()
    c.post(f"/api/recipes/{standard['id']}/resources", json={"resource_type":"MATERIAL","resource_id":material["id"],"quantity_per_unit":"2","waste_percent":"5","unit":"sac"})
    company = c.post("/api/recipes", json={"work_item_id":work["id"],"scope":"COMPANY_OVERRIDE","version":2}).json()
    c.post(f"/api/recipes/{company['id']}/resources", json={"resource_type":"EQUIPMENT","resource_id":equipment["id"],"quantity_per_unit":"0.2","waste_percent":"0","unit":"ora"})
    project_recipe = c.post("/api/recipes", json={"work_item_id":work["id"],"scope":"PROJECT_OVERRIDE","project_id":project["id"],"version":3}).json()
    c.post(f"/api/recipes/{project_recipe['id']}/resources", json={"resource_type":"LABOR","resource_id":labor["id"],"quantity_per_unit":"1.5","waste_percent":"10","unit":"ora","notes":"Echipă proiect"})
    c.put(f"/api/projects/{project['id']}/resource-prices", json={"resource_type":"LABOR","resource_id":labor["id"],"unit_price_net":"55.5555","vat_rate":"21"})

    item = hierarchy(c, project["id"], work["id"])
    generated = c.post(f"/api/estimate-items/{item['id']}/resources/generate")
    assert generated.status_code == 200
    lines = generated.json()
    assert len(lines) == 1
    assert lines[0]["resource_type"] == "LABOR"
    assert Decimal(str(lines[0]["quantity"])) == Decimal("16.500000")
    assert Decimal(str(lines[0]["unit_price_net"])) == Decimal("55.5555")
    assert c.get(f"/api/recipes/{standard['id']}/resources").json()[0]["resource_type"] == "MATERIAL"

    manual = c.post(f"/api/estimate-items/{item['id']}/resources", json={"resource_type":"OTHER","description":"Protecții","unit":"set","quantity":"2","waste_percent":"5","unit_price_net":"10","vat_rate":"21"})
    assert manual.status_code == 201
    assert Decimal(str(manual.json()["quantity"])) == Decimal("2.100000")
    totals = c.get(f"/api/projects/{project['id']}/estimate-totals").json()
    assert Decimal(str(totals["LABOR"])) > Decimal("1000")
    assert Decimal(str(totals["OTHER"])) == Decimal("25.41")
    assert Decimal(str(totals["total_gross"])) == Decimal(str(totals["total_net"])) + Decimal(str(totals["vat"]))
