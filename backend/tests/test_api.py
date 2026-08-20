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
