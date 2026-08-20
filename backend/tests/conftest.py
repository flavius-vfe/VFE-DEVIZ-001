import os
os.environ["DATABASE_URL"] = "sqlite:///./test_deviz.sqlite3"
os.environ["SERVER_IP"] = "192.168.0.50"
os.environ["FRONTEND_PORT"] = "3080"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app

@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

@pytest.fixture()
def client(db):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture()
def authenticated_client(client):
    r = client.post("/api/setup", json={
        "username": "administrator",
        "password": "Parola-Foarte-Sigura-123!",
        "server_ip": "192.168.0.50",
        "locality": "Ceahlău",
        "county": "Neamț",
        "vat_rate": "21"
    })
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={
        "username": "administrator",
        "password": "Parola-Foarte-Sigura-123!"
    })
    assert r.status_code == 200
    return client
