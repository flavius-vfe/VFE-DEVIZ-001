def test_setup_login_project_flow(client):
    assert client.get("/api/setup/status").json() == {"configured": False}
    r = client.post("/api/setup", json={
        "username": "administrator",
        "password": "Parola-Foarte-Sigura-123!",
        "server_ip": "192.168.0.50",
        "locality": "Ceahlău",
        "county": "Neamț",
        "vat_rate": "21"
    })
    assert r.status_code == 201
    assert client.get("/api/setup/status").json() == {"configured": True}
    assert client.post("/api/setup", json={
        "username": "administrator2",
        "password": "Alta-Parola-Sigura-123!",
        "server_ip": "192.168.0.50"
    }).status_code == 409

    bad = client.post("/api/auth/login", json={"username": "administrator", "password": "bad-password"})
    assert bad.status_code == 401

    good = client.post("/api/auth/login", json={
        "username": "administrator", "password": "Parola-Foarte-Sigura-123!"
    })
    assert good.status_code == 200
    assert "Max-Age=604800" in good.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 200

    project = client.post("/api/projects", json={
        "name": "Casă Ceahlău",
        "client": "Beneficiar test",
        "locality": "Ceahlău",
        "county": "Neamț",
        "default_waste_percent": "5"
    })
    assert project.status_code == 201
    body = project.json()
    assert body["name"] == "Casă Ceahlău"
    assert client.get("/api/projects").json()[0]["id"] == body["id"]

    out = client.post("/api/auth/logout")
    assert out.status_code == 204
    assert client.get("/api/auth/me").status_code == 401

def test_cors_allows_configured_unraid_frontend(client):
    response = client.options("/api/auth/login", headers={
        "Origin": "http://192.168.0.50:3080",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.0.50:3080"
    assert response.headers["access-control-allow-credentials"] == "true"

def test_calc_endpoints(authenticated_client):
    c = authenticated_client
    vat = c.post("/api/calc/vat", json={"amount": "100", "vat_rate": "21"}).json()
    assert vat["gross"] == 121.0

    packages = c.post("/api/calc/packages", json={
        "required_quantity": "83",
        "waste_percent": "5",
        "package_quantity": "5.5",
        "package_price_gross": "100"
    }).json()
    assert packages["packages"] == 16
    assert packages["total_gross"] == 1600.0

    room = c.post("/api/calc/room", json={
        "length_m": "4", "width_m": "3.5", "height_m": "2.7", "openings_m2": "4.59"
    }).json()
    assert room["wall_net_m2"] == 35.91

def test_boq_hierarchy_flow(authenticated_client):
    c = authenticated_client
    project = c.post("/api/projects", json={"name": "Casă BOQ"}).json()
    building = c.post(f"/api/projects/{project['id']}/buildings", json={"name": "Corp principal"})
    assert building.status_code == 201
    building_id = building.json()["id"]

    level = c.post(f"/api/buildings/{building_id}/levels", json={"name": "Parter", "elevation_m": "0"})
    assert level.status_code == 201
    level_id = level.json()["id"]

    section = c.post(f"/api/levels/{level_id}/sections", json={"code": "01", "name": "Fundații"})
    assert section.status_code == 201
    section_id = section.json()["id"]

    item = c.post(f"/api/sections/{section_id}/items", json={
        "code": "01.001", "description": "Beton fundații", "unit": "m3", "quantity": "19.2"
    })
    assert item.status_code == 201
    assert item.json()["quantity"] == "19.200000"
    assert c.get(f"/api/projects/{project['id']}/buildings").json()[0]["name"] == "Corp principal"
    assert c.get(f"/api/buildings/{building_id}/levels").json()[0]["name"] == "Parter"
    assert c.get(f"/api/levels/{level_id}/sections").json()[0]["name"] == "Fundații"
    assert c.get(f"/api/sections/{section_id}/items").json()[0]["code"] == "01.001"

def test_boq_hierarchy_rejects_cross_level_parent(authenticated_client):
    c = authenticated_client
    project = c.post("/api/projects", json={"name": "Validare BOQ"}).json()
    building = c.post(f"/api/projects/{project['id']}/buildings", json={"name": "Corp"}).json()
    level_a = c.post(f"/api/buildings/{building['id']}/levels", json={"name": "Parter"}).json()
    level_b = c.post(f"/api/buildings/{building['id']}/levels", json={"name": "Etaj"}).json()
    parent = c.post(f"/api/levels/{level_a['id']}/sections", json={"code": "01", "name": "Structură"}).json()
    response = c.post(f"/api/levels/{level_b['id']}/sections", json={
        "code": "01.01", "name": "Invalid", "parent_section_id": parent["id"]
    })
    assert response.status_code == 422

def test_boq_hierarchy_update_delete_and_validation(authenticated_client):
    c = authenticated_client
    project = c.post("/api/projects", json={"name": "CRUD BOQ"}).json()
    building = c.post(f"/api/projects/{project['id']}/buildings", json={"name": "Corp A"}).json()
    level = c.post(f"/api/buildings/{building['id']}/levels", json={"name": "Parter"}).json()
    section = c.post(f"/api/levels/{level['id']}/sections", json={"code": "01", "name": "Fundații"}).json()
    item = c.post(f"/api/sections/{section['id']}/items", json={
        "code": "01.001", "description": "Beton", "unit": "m3", "quantity": "10",
        "waste_percent": "5", "notes": "Turnare continuă"
    }).json()

    updated_building = c.put(f"/api/buildings/{building['id']}", json={"name": "Corp principal"})
    assert updated_building.status_code == 200
    updated_level = c.put(f"/api/levels/{level['id']}", json={"name": "Parter înalt", "elevation_m": "0.45"})
    assert updated_level.status_code == 200
    updated_section = c.put(f"/api/sections/{section['id']}", json={"code": "01A", "name": "Infrastructură"})
    assert updated_section.status_code == 200
    updated_item = c.put(f"/api/estimate-items/{item['id']}", json={
        "code": "01A.001", "description": "Beton armat", "unit": "m3", "quantity": "12.5",
        "waste_percent": "7", "notes": "Conform proiectului"
    })
    assert updated_item.status_code == 200
    assert updated_item.json()["notes"] == "Conform proiectului"

    invalid_unit = c.put(f"/api/estimate-items/{item['id']}", json={
        "code": "x", "description": "x", "unit": "litru", "quantity": "1"
    })
    assert invalid_unit.status_code == 422

    assert c.delete(f"/api/estimate-items/{item['id']}").status_code == 204
    assert c.get(f"/api/sections/{section['id']}/items").json() == []
    assert c.delete(f"/api/sections/{section['id']}").status_code == 204
    assert c.delete(f"/api/levels/{level['id']}").status_code == 204
    assert c.delete(f"/api/buildings/{building['id']}").status_code == 204
    assert c.get(f"/api/projects/{project['id']}/buildings").json() == []
