from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import (
    SystemSetting, User, UserSession, Project, Building, Level,
    EstimateSection, EstimateItem, WorkItem, Material, LaborResource, EquipmentResource,
    OtherResource, WorkRecipe, RecipeResource, ProjectResourcePrice, EstimateResourceLine,
)
from .schemas import (
    SetupStatusOut, SetupIn, LoginIn, UserOut,
    ProjectIn, ProjectOut, BuildingIn, BuildingOut, LevelIn, LevelOut,
    SectionIn, SectionOut, EstimateItemIn, EstimateItemOut,
    VatCalcIn, PackageCalcIn, RoomCalcIn, SteelCalcIn, MaterialIn, MaterialOut,
    PricedResourceIn, PricedResourceOut, WorkItemIn, WorkItemOut, RecipeIn, RecipeOut,
    RecipeResourceIn, RecipeResourceOut, ProjectPriceIn, ProjectPriceOut, ManualResourceLineIn,
)
from .security import (
    hash_password, verify_password, new_session_token, hash_session_token, session_expiry
)
from .deps import current_user, SESSION_COOKIE
from .calc import (
    gross_from_net, net_from_gross, vat_amount_from_net, with_waste,
    packages_required, room_geometry, steel_total_kg, money
)
from .estimation import calculate_cost, gross_from_net_exact, recipe_quantity, aggregate_totals

app = FastAPI(title="VFE Deviz API", version="0.1.4")

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
    return {"status": "ok", "service": "vfe-deviz-backend", "version": "0.1.4"}

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
        "default_currency": payload.currency,
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

def require_entity(db: Session, model, entity_id: int, detail: str):
    entity = db.get(model, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=detail)
    return entity

@app.get("/api/projects/{project_id}/buildings", response_model=list[BuildingOut])
def list_buildings(project_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există.")
    return list(db.scalars(select(Building).where(Building.project_id == project_id).order_by(Building.sort_order, Building.id)))

@app.post("/api/projects/{project_id}/buildings", response_model=BuildingOut, status_code=201)
def create_building(project_id: int, payload: BuildingIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există.")
    building = Building(project_id=project_id, **payload.model_dump())
    db.add(building)
    db.commit()
    db.refresh(building)
    return building

@app.put("/api/buildings/{building_id}", response_model=BuildingOut)
def update_building(building_id: int, payload: BuildingIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    building = require_entity(db, Building, building_id, "Corpul nu există.")
    for key, value in payload.model_dump().items():
        setattr(building, key, value)
    db.commit()
    db.refresh(building)
    return building

@app.delete("/api/buildings/{building_id}", status_code=204)
def delete_building(building_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    building = require_entity(db, Building, building_id, "Corpul nu există.")
    db.delete(building)
    db.commit()
    return Response(status_code=204)

@app.get("/api/buildings/{building_id}/levels", response_model=list[LevelOut])
def list_levels(building_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Building, building_id, "Corpul nu există.")
    return list(db.scalars(select(Level).where(Level.building_id == building_id).order_by(Level.sort_order, Level.id)))

@app.post("/api/buildings/{building_id}/levels", response_model=LevelOut, status_code=201)
def create_level(building_id: int, payload: LevelIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Building, building_id, "Corpul nu există.")
    level = Level(building_id=building_id, **payload.model_dump())
    db.add(level)
    db.commit()
    db.refresh(level)
    return level

@app.put("/api/levels/{level_id}", response_model=LevelOut)
def update_level(level_id: int, payload: LevelIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    level = require_entity(db, Level, level_id, "Nivelul nu există.")
    for key, value in payload.model_dump().items():
        setattr(level, key, value)
    db.commit()
    db.refresh(level)
    return level

@app.delete("/api/levels/{level_id}", status_code=204)
def delete_level(level_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    level = require_entity(db, Level, level_id, "Nivelul nu există.")
    db.delete(level)
    db.commit()
    return Response(status_code=204)

@app.get("/api/levels/{level_id}/sections", response_model=list[SectionOut])
def list_sections(level_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Level, level_id, "Nivelul nu există.")
    return list(db.scalars(select(EstimateSection).where(EstimateSection.level_id == level_id).order_by(EstimateSection.sort_order, EstimateSection.id)))

@app.post("/api/levels/{level_id}/sections", response_model=SectionOut, status_code=201)
def create_section(level_id: int, payload: SectionIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Level, level_id, "Nivelul nu există.")
    if payload.parent_section_id is not None:
        parent = require_entity(db, EstimateSection, payload.parent_section_id, "Capitolul părinte nu există.")
        if parent.level_id != level_id:
            raise HTTPException(status_code=422, detail="Capitolul părinte aparține altui nivel.")
    section = EstimateSection(level_id=level_id, **payload.model_dump())
    db.add(section)
    db.commit()
    db.refresh(section)
    return section

@app.put("/api/sections/{section_id}", response_model=SectionOut)
def update_section(section_id: int, payload: SectionIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    section = require_entity(db, EstimateSection, section_id, "Capitolul nu există.")
    if payload.parent_section_id == section_id:
        raise HTTPException(status_code=422, detail="Un capitol nu poate fi propriul părinte.")
    if payload.parent_section_id is not None:
        parent = require_entity(db, EstimateSection, payload.parent_section_id, "Capitolul părinte nu există.")
        if parent.level_id != section.level_id:
            raise HTTPException(status_code=422, detail="Capitolul părinte aparține altui nivel.")
    for key, value in payload.model_dump().items():
        setattr(section, key, value)
    db.commit()
    db.refresh(section)
    return section

@app.delete("/api/sections/{section_id}", status_code=204)
def delete_section(section_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    section = require_entity(db, EstimateSection, section_id, "Capitolul nu există.")
    db.delete(section)
    db.commit()
    return Response(status_code=204)

@app.get("/api/sections/{section_id}/items", response_model=list[EstimateItemOut])
def list_estimate_items(section_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, EstimateSection, section_id, "Capitolul nu există.")
    return list(db.scalars(select(EstimateItem).where(EstimateItem.section_id == section_id).order_by(EstimateItem.sort_order, EstimateItem.id)))

@app.post("/api/sections/{section_id}/items", response_model=EstimateItemOut, status_code=201)
def create_estimate_item(section_id: int, payload: EstimateItemIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, EstimateSection, section_id, "Capitolul nu există.")
    if payload.work_item_id is not None:
        require_entity(db, WorkItem, payload.work_item_id, "Lucrarea standard nu există.")
    item = EstimateItem(section_id=section_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.put("/api/estimate-items/{item_id}", response_model=EstimateItemOut)
def update_estimate_item(item_id: int, payload: EstimateItemIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    item = require_entity(db, EstimateItem, item_id, "Articolul de deviz nu există.")
    if payload.work_item_id is not None:
        require_entity(db, WorkItem, payload.work_item_id, "Lucrarea standard nu există.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item

@app.delete("/api/estimate-items/{item_id}", status_code=204)
def delete_estimate_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    item = require_entity(db, EstimateItem, item_id, "Articolul de deviz nu există.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)

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

RESOURCE_MODELS = {
    "MATERIAL": Material,
    "LABOR": LaborResource,
    "EQUIPMENT": EquipmentResource,
    "OTHER": OtherResource,
}

def commit_or_conflict(db: Session, detail: str):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc

def get_resource(db: Session, resource_type: str, resource_id: int):
    model = RESOURCE_MODELS[resource_type]
    return require_entity(db, model, resource_id, "Resursa nu există.")

def resource_name(resource) -> str:
    return resource.name

def project_for_item(db: Session, item_id: int) -> int:
    project_id = db.scalar(
        select(Building.project_id)
        .join(Level, Level.building_id == Building.id)
        .join(EstimateSection, EstimateSection.level_id == Level.id)
        .join(EstimateItem, EstimateItem.section_id == EstimateSection.id)
        .where(EstimateItem.id == item_id)
    )
    if project_id is None:
        raise HTTPException(status_code=404, detail="Articolul de deviz nu există.")
    return project_id

def effective_price(db: Session, project_id: int, resource_type: str, resource_id: int):
    override = db.scalar(select(ProjectResourcePrice).where(
        ProjectResourcePrice.project_id == project_id,
        ProjectResourcePrice.resource_type == resource_type,
        ProjectResourcePrice.resource_id == resource_id,
    ))
    if override:
        return override.unit_price_net, override.vat_rate
    resource = get_resource(db, resource_type, resource_id)
    if resource_type == "MATERIAL":
        return Decimal("0"), Decimal("21")
    return resource.rate_net, resource.vat_rate

@app.get("/api/catalog/materials", response_model=list[MaterialOut])
def list_materials(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return list(db.scalars(select(Material).order_by(Material.code)))

@app.post("/api/catalog/materials", response_model=MaterialOut, status_code=201)
def create_material(payload: MaterialIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row = Material(**payload.model_dump())
    db.add(row); commit_or_conflict(db, "Codul materialului există deja."); db.refresh(row)
    return row

@app.put("/api/catalog/materials/{resource_id}", response_model=MaterialOut)
def update_material(resource_id: int, payload: MaterialIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row = require_entity(db, Material, resource_id, "Materialul nu există.")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    commit_or_conflict(db, "Codul materialului există deja."); db.refresh(row)
    return row

def list_priced(model, db: Session):
    return list(db.scalars(select(model).order_by(model.code)))

def create_priced(model, payload: PricedResourceIn, db: Session):
    values = payload.model_dump()
    values["rate_gross"] = gross_from_net_exact(values["rate_net"], values["vat_rate"])
    row = model(**values); db.add(row); commit_or_conflict(db, "Codul resursei există deja."); db.refresh(row)
    return row

def update_priced(model, resource_id: int, payload: PricedResourceIn, db: Session):
    row = require_entity(db, model, resource_id, "Resursa nu există.")
    values = payload.model_dump(); values["rate_gross"] = gross_from_net_exact(values["rate_net"], values["vat_rate"])
    for key, value in values.items(): setattr(row, key, value)
    commit_or_conflict(db, "Codul resursei există deja."); db.refresh(row)
    return row

@app.get("/api/catalog/labor", response_model=list[PricedResourceOut])
def list_labor(db: Session = Depends(get_db), _: User = Depends(current_user)): return list_priced(LaborResource, db)
@app.post("/api/catalog/labor", response_model=PricedResourceOut, status_code=201)
def create_labor(payload: PricedResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)): return create_priced(LaborResource, payload, db)
@app.put("/api/catalog/labor/{resource_id}", response_model=PricedResourceOut)
def update_labor(resource_id: int, payload: PricedResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)): return update_priced(LaborResource, resource_id, payload, db)

@app.get("/api/catalog/equipment", response_model=list[PricedResourceOut])
def list_equipment(db: Session = Depends(get_db), _: User = Depends(current_user)): return list_priced(EquipmentResource, db)
@app.post("/api/catalog/equipment", response_model=PricedResourceOut, status_code=201)
def create_equipment(payload: PricedResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)): return create_priced(EquipmentResource, payload, db)
@app.put("/api/catalog/equipment/{resource_id}", response_model=PricedResourceOut)
def update_equipment(resource_id: int, payload: PricedResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)): return update_priced(EquipmentResource, resource_id, payload, db)

@app.get("/api/catalog/other", response_model=list[PricedResourceOut])
def list_other(db: Session = Depends(get_db), _: User = Depends(current_user)): return list_priced(OtherResource, db)
@app.post("/api/catalog/other", response_model=PricedResourceOut, status_code=201)
def create_other(payload: PricedResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)): return create_priced(OtherResource, payload, db)

@app.get("/api/catalog/work-items", response_model=list[WorkItemOut])
def list_work_items(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return list(db.scalars(select(WorkItem).order_by(WorkItem.code)))

@app.post("/api/catalog/work-items", response_model=WorkItemOut, status_code=201)
def create_work_item(payload: WorkItemIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row = WorkItem(**payload.model_dump()); db.add(row); commit_or_conflict(db, "Codul lucrării există deja."); db.refresh(row)
    return row

@app.put("/api/catalog/work-items/{work_item_id}", response_model=WorkItemOut)
def update_work_item(work_item_id: int, payload: WorkItemIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row = require_entity(db, WorkItem, work_item_id, "Lucrarea nu există.")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    commit_or_conflict(db, "Codul lucrării există deja."); db.refresh(row)
    return row

@app.get("/api/work-items/{work_item_id}/recipes", response_model=list[RecipeOut])
def list_recipes(work_item_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return list(db.scalars(select(WorkRecipe).where(WorkRecipe.work_item_id == work_item_id).order_by(WorkRecipe.version.desc())))

@app.post("/api/recipes", response_model=RecipeOut, status_code=201)
def create_recipe(payload: RecipeIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, WorkItem, payload.work_item_id, "Lucrarea nu există.")
    if payload.scope == "PROJECT_OVERRIDE" and payload.project_id is None:
        raise HTTPException(status_code=422, detail="Override-ul de proiect necesită project_id.")
    if payload.scope != "PROJECT_OVERRIDE" and payload.project_id is not None:
        raise HTTPException(status_code=422, detail="Doar override-ul de proiect poate avea project_id.")
    row = WorkRecipe(**payload.model_dump()); db.add(row); commit_or_conflict(db, "Versiunea rețetei există deja."); db.refresh(row)
    return row

@app.get("/api/recipes/{recipe_id}/resources", response_model=list[RecipeResourceOut])
def list_recipe_resources(recipe_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, WorkRecipe, recipe_id, "Rețeta nu există.")
    return list(db.scalars(select(RecipeResource).where(RecipeResource.recipe_id == recipe_id).order_by(RecipeResource.id)))

@app.post("/api/recipes/{recipe_id}/resources", response_model=RecipeResourceOut, status_code=201)
def create_recipe_resource(recipe_id: int, payload: RecipeResourceIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, WorkRecipe, recipe_id, "Rețeta nu există.")
    resource = get_resource(db, payload.resource_type, payload.resource_id)
    row = RecipeResource(recipe_id=recipe_id, description=resource_name(resource), formula=None, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row); return row

@app.put("/api/projects/{project_id}/resource-prices", response_model=ProjectPriceOut)
def set_project_price(project_id: int, payload: ProjectPriceIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există."); get_resource(db, payload.resource_type, payload.resource_id)
    row = db.scalar(select(ProjectResourcePrice).where(ProjectResourcePrice.project_id == project_id, ProjectResourcePrice.resource_type == payload.resource_type, ProjectResourcePrice.resource_id == payload.resource_id))
    values = payload.model_dump(); values["unit_price_gross"] = gross_from_net_exact(payload.unit_price_net, payload.vat_rate)
    if row is None: row = ProjectResourcePrice(project_id=project_id, **values); db.add(row)
    else:
        for key, value in values.items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row

def line_dict(line: EstimateResourceLine):
    return {column.name: getattr(line, column.name) for column in line.__table__.columns}

@app.get("/api/estimate-items/{item_id}/resources")
def list_item_resources(item_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, EstimateItem, item_id, "Articolul de deviz nu există.")
    return [line_dict(row) for row in db.scalars(select(EstimateResourceLine).where(EstimateResourceLine.estimate_item_id == item_id).order_by(EstimateResourceLine.id))]

@app.post("/api/estimate-items/{item_id}/resources", status_code=201)
def create_manual_resource(item_id: int, payload: ManualResourceLineIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, EstimateItem, item_id, "Articolul de deviz nu există.")
    if payload.resource_id is not None: get_resource(db, payload.resource_type, payload.resource_id)
    effective_quantity = recipe_quantity(payload.quantity, Decimal("1"), payload.waste_percent)
    cost = calculate_cost(effective_quantity, payload.unit_price_net, payload.vat_rate)
    row = EstimateResourceLine(estimate_item_id=item_id, source="MANUAL", recipe_resource_id=None, resource_type=payload.resource_type, resource_id=payload.resource_id, description=payload.description, unit=payload.unit, quantity=cost.quantity, waste_percent=payload.waste_percent, unit_price_net=cost.unit_price_net, vat_rate=cost.vat_rate, vat_amount=cost.vat_amount, unit_price_gross=cost.unit_price_gross, subtotal_net=cost.subtotal_net, subtotal_gross=cost.subtotal_gross, notes=payload.notes)
    db.add(row); db.commit(); db.refresh(row); return line_dict(row)

def resolve_recipe(db: Session, work_item_id: int, project_id: int):
    recipes = list(db.scalars(select(WorkRecipe).where(WorkRecipe.work_item_id == work_item_id).order_by(WorkRecipe.version.desc())))
    for scope in ("PROJECT_OVERRIDE", "COMPANY_OVERRIDE", "STANDARD"):
        candidates = [r for r in recipes if r.scope == scope and (scope != "PROJECT_OVERRIDE" or r.project_id == project_id)]
        if candidates: return candidates[0]
    return None

@app.post("/api/estimate-items/{item_id}/resources/generate")
def generate_recipe_resources(item_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    item = require_entity(db, EstimateItem, item_id, "Articolul de deviz nu există.")
    if item.work_item_id is None: raise HTTPException(status_code=422, detail="Articolul nu are o lucrare asociată.")
    project_id = project_for_item(db, item_id); recipe = resolve_recipe(db, item.work_item_id, project_id)
    if recipe is None: raise HTTPException(status_code=404, detail="Nu există rețetă aplicabilă.")
    db.execute(delete(EstimateResourceLine).where(EstimateResourceLine.estimate_item_id == item_id, EstimateResourceLine.source == "RECIPE"))
    for recipe_line in db.scalars(select(RecipeResource).where(RecipeResource.recipe_id == recipe.id)):
        net, vat = effective_price(db, project_id, recipe_line.resource_type, recipe_line.resource_id)
        quantity = recipe_quantity(item.quantity, recipe_line.quantity_per_unit, recipe_line.waste_percent)
        cost = calculate_cost(quantity, net, vat)
        db.add(EstimateResourceLine(estimate_item_id=item.id, recipe_resource_id=recipe_line.id, source="RECIPE", resource_type=recipe_line.resource_type, resource_id=recipe_line.resource_id, description=recipe_line.description, unit=recipe_line.unit, quantity=cost.quantity, waste_percent=recipe_line.waste_percent, unit_price_net=cost.unit_price_net, vat_rate=cost.vat_rate, vat_amount=cost.vat_amount, unit_price_gross=cost.unit_price_gross, subtotal_net=cost.subtotal_net, subtotal_gross=cost.subtotal_gross, notes=recipe_line.notes))
    db.commit()
    return list_item_resources(item_id, db, _)

@app.get("/api/projects/{project_id}/estimate-totals")
def project_estimate_totals(project_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există.")
    lines = list(db.scalars(select(EstimateResourceLine).join(EstimateItem).join(EstimateSection).join(Level).join(Building).where(Building.project_id == project_id)))
    return aggregate_totals([line_dict(line) for line in lines])
