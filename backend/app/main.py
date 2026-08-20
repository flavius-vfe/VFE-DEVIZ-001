from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, text
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import SystemSetting, User, UserSession, Project
from .schemas import (
    SetupStatusOut, SetupIn, LoginIn, UserOut,
    ProjectIn, ProjectOut, VatCalcIn, PackageCalcIn, RoomCalcIn, SteelCalcIn
)
from .security import (
    hash_password, verify_password, new_session_token, hash_session_token, session_expiry
)
from .deps import current_user, SESSION_COOKIE
from .calc import (
    gross_from_net, net_from_gross, vat_amount_from_net, with_waste,
    packages_required, room_geometry, steel_total_kg, money
)

app = FastAPI(title="VFE Deviz API", version="0.1.0")

private_origin_regex = (
    rf"^http://(?:{settings.server_ip.replace('.', r'\.')}"
    rf"|localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+"
    rf"|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):"
    rf"{settings.frontend_port}$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{settings.server_ip}:{settings.frontend_port}"],
    allow_origin_regex=private_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "vfe-deviz-backend", "version": "0.1.0"}

@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Baza de date nu este disponibilă.") from exc
    return {"status": "ready"}

@app.get("/api/setup/status", response_model=SetupStatusOut)
def setup_status(db: Session = Depends(get_db)):
    configured = db.scalar(select(User.id).limit(1)) is not None
    return SetupStatusOut(configured=configured)

@app.post("/api/setup", response_model=UserOut, status_code=201)
def setup(payload: SetupIn, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Configurarea inițială a fost deja finalizată.")
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    settings_to_save = {
        "setup_completed": "true",
        "server_ip": payload.server_ip,
        "default_locality": payload.locality,
        "default_county": payload.county,
        "default_vat_rate": str(payload.vat_rate),
        "default_currency": "RON",
        "default_locale": "ro-RO",
    }
    for key, value in settings_to_save.items():
        db.merge(SystemSetting(key=key, value=value))
    db.commit()
    db.refresh(user)
    return user

@app.post("/api/auth/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.active or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Utilizator sau parolă incorectă.")
    token = new_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=session_expiry(settings.session_days),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.session_days * 86400,
        path="/",
    )
    return user

@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_session_token(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response

@app.get("/api/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())))

@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Proiectul nu există.")
    return project

@app.post("/api/calc/vat")
def calc_vat(payload: VatCalcIn, _: User = Depends(current_user)):
    if payload.amount_includes_vat:
        gross = money(payload.amount)
        net = net_from_gross(gross, payload.vat_rate)
    else:
        net = money(payload.amount)
        gross = gross_from_net(net, payload.vat_rate)
    return {
        "net": net,
        "vat": money(gross - net),
        "gross": gross,
        "vat_rate": payload.vat_rate,
    }

@app.post("/api/calc/packages")
def calc_packages(payload: PackageCalcIn, _: User = Depends(current_user)):
    required_with_waste = with_waste(payload.required_quantity, payload.waste_percent)
    packages = packages_required(required_with_waste, payload.package_quantity)
    return {
        "required_quantity": payload.required_quantity,
        "required_with_waste": required_with_waste,
        "packages": packages,
        "purchased_quantity": Decimal(packages) * payload.package_quantity,
        "total_gross": money(Decimal(packages) * payload.package_price_gross),
    }

@app.post("/api/calc/room")
def calc_room(payload: RoomCalcIn, _: User = Depends(current_user)):
    g = room_geometry(payload.length_m, payload.width_m, payload.height_m, payload.openings_m2)
    return {
        "floor_area_m2": g.floor_area_m2,
        "ceiling_area_m2": g.ceiling_area_m2,
        "perimeter_m": g.perimeter_m,
        "wall_gross_m2": g.wall_gross_m2,
        "openings_m2": g.openings_m2,
        "wall_net_m2": g.wall_net_m2,
    }

@app.post("/api/calc/steel")
def calc_steel(payload: SteelCalcIn, _: User = Depends(current_user)):
    return {
        "total_kg": steel_total_kg(
            payload.diameter_mm,
            payload.bar_length_m,
            payload.quantity,
            payload.waste_percent,
        )
    }
