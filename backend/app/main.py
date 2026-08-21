from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import (
    SystemSetting, User, UserSession, Project, Building, Level,
    EstimateSection, EstimateItem, WorkItem, Material, LaborResource, EquipmentResource,
    OtherResource, WorkRecipe, RecipeResource, ProjectResourcePrice, EstimateResourceLine,
    GeometryCalculation, GeometryEstimateLink, MeshCatalogueItem, WorkCategory, Supplier, SupplierLocation,
    SupplierProduct, ProductMatch, PriceObservation, SupplierRefreshJob, DeliveryQuote, EstimateVersion, EstimateSnapshotLine,
)
from .schemas import (
    SetupStatusOut, SetupIn, LoginIn, UserOut,
    ProjectIn, ProjectOut, BuildingIn, BuildingOut, LevelIn, LevelOut,
    SectionIn, SectionOut, EstimateItemIn, EstimateItemOut,
    VatCalcIn, PackageCalcIn, RoomCalcIn, SteelCalcIn, MaterialIn, MaterialOut,
    PricedResourceIn, PricedResourceOut, WorkItemIn, WorkItemOut, RecipeIn, RecipeOut,
    RecipeResourceIn, RecipeResourceOut, ProjectPriceIn, ProjectPriceOut, ManualResourceLineIn,
    GeometryCalculationIn, GeometryLinkIn, GeometryCreateItemIn, MeshCatalogueIn, CatalogueItemIn, CatalogueImportIn,
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
from .geometry import calculate as calculate_geometry, UNITS as GEOMETRY_UNITS, with_waste as geometry_with_waste
from .catalogue import seed_catalogue, export_catalogue
from .suppliers import adapter_for, import_product, match_score, package_purchase
from .suppliers.seed import seed_suppliers
from .suppliers.security import validate_supplier_url

app = FastAPI(title="VFE Deviz API", version="0.1.7")

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
    return {"status": "ok", "service": "vfe-deviz-backend", "version": "0.1.7"}

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
    seed_catalogue(db)
    seed_suppliers(db)
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

@app.put("/api/projects/{project_id}/material-price-strategy",response_model=ProjectOut)
def update_material_price_strategy(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    project=require_entity(db,Project,project_id,"Proiectul nu există.");strategy=payload.get("strategy")
    if strategy not in {"MANUAL","CHEAPEST_PRODUCT_PRICE","PREFERRED_SUPPLIER"}:raise HTTPException(422,"Strategie de preț invalidă.")
    project.material_price_strategy=strategy;project.preferred_supplier_id=payload.get("preferred_supplier_id") if strategy=="PREFERRED_SUPPLIER" else project.preferred_supplier_id;db.commit();db.refresh(project);return project

def require_entity(db: Session, model, entity_id: int, detail: str):
    entity = db.get(model, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=detail)
    return entity

def supplier_dict(db: Session, supplier: Supplier):
    locations=list(db.scalars(select(SupplierLocation).where(SupplierLocation.supplier_id==supplier.id)))
    return {"id":supplier.id,"code":supplier.code,"name":supplier.name,"website":supplier.website,"active":supplier.active,
      "status":"FUNCTIONAL" if supplier.last_error is None else "DEGRADED","requests":supplier.requests,"successes":supplier.successes,
      "failures":supplier.failures,"parse_failures":supplier.parse_failures,"last_success":supplier.last_success,"last_error":supplier.last_error,
      "locations":[{"id":x.id,"code":x.code,"name":x.name,"address":x.address,"locality":x.locality,"county":x.county,"active":x.active} for x in locations]}

@app.get("/api/suppliers")
def list_suppliers(db:Session=Depends(get_db),_:User=Depends(current_user)):
    return [supplier_dict(db,x) for x in db.scalars(select(Supplier).order_by(Supplier.name))]

@app.get("/api/suppliers/{code}")
def get_supplier(code:str,db:Session=Depends(get_db),_:User=Depends(current_user)):
    supplier=db.scalar(select(Supplier).where(Supplier.code==code.upper()))
    if not supplier: raise HTTPException(404,"Furnizorul nu există.")
    result=supplier_dict(db,supplier); products=list(db.scalars(select(SupplierProduct).where(SupplierProduct.supplier_id==supplier.id)))
    result["products"]=[product_dict(db,x) for x in products]; return result

def product_dict(db, product):
    observation=db.scalar(select(PriceObservation).where(PriceObservation.supplier_product_id==product.id,PriceObservation.success.is_(True)).order_by(PriceObservation.checked_at.desc()).limit(1))
    return {"id":product.id,"supplier_id":product.supplier_id,"supplier_sku":product.supplier_sku,"name":product.name,"brand":product.brand,"category":product.category,"product_url":product.product_url,"image_url":product.image_url,"package_quantity":product.package_quantity,"package_unit":product.package_unit,"normalized_quantity":product.normalized_quantity,"normalized_unit":product.normalized_unit,"attributes":product.attributes,"active":product.active,"last_seen_at":product.last_seen_at,"price":({"gross":observation.price_gross,"net":observation.price_net,"vat_rate":observation.vat_rate,"stock_status":observation.stock_status,"stock_text":observation.stock_text,"checked_at":observation.checked_at} if observation else None)}

@app.post("/api/suppliers/import-url",status_code=201)
def import_supplier_url(payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    supplier=db.scalar(select(Supplier).where(Supplier.code==str(payload.get("supplier","")).upper()))
    if not supplier: raise HTTPException(404,"Furnizorul nu există.")
    url=str(payload.get("url", ""));
    try: validate_supplier_url(url,supplier.code); adapter=adapter_for(supplier.code); parsed=adapter.parse_product(adapter.fetch_product(url),url)
    except ValueError as exc:
        supplier.requests+=1;supplier.parse_failures+=1;supplier.last_error=str(exc);db.commit();raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        supplier.requests+=1;supplier.failures+=1;supplier.last_error=str(exc);db.commit();raise HTTPException(502,"Pagina publică a furnizorului nu a putut fi accesată.") from exc
    location=db.scalar(select(SupplierLocation).where(SupplierLocation.supplier_id==supplier.id,SupplierLocation.preferred.is_(True)))
    product,_=import_product(db,supplier,parsed,location.id if location else None); return product_dict(db,product)

@app.post("/api/suppliers/import-fixture",status_code=201)
def import_supplier_fixture(payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    allowed={"dedeman_adeziv.html":"DEDEMAN","dedeman_bca.html":"DEDEMAN","mathaus_adeziv.html":"MATHAUS","mathaus_bca.html":"MATHAUS"}; name=str(payload.get("fixture",""))
    code=allowed.get(name)
    if not code: raise HTTPException(422,"Fixture necunoscut.")
    supplier=db.scalar(select(Supplier).where(Supplier.code==code)); location=db.scalar(select(SupplierLocation).where(SupplierLocation.supplier_id==supplier.id,SupplierLocation.preferred.is_(True)))
    path=Path(__file__).resolve().parent/"suppliers"/"fixtures"/name
    parsed=adapter_for(code).parse_product(path.read_text(encoding="utf-8"),f"https://{'www.dedeman.ro' if code=='DEDEMAN' else 'mathaus.ro'}/fixture/{name}")
    product,_=import_product(db,supplier,parsed,location.id if location else None,"FIXTURE"); return product_dict(db,product)

@app.get("/api/catalog/materials/{material_id}/products")
def material_products(material_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    material=require_entity(db,Material,material_id,"Materialul nu există."); products=list(db.scalars(select(SupplierProduct).where(SupplierProduct.active.is_(True))))
    matches={x.supplier_product_id:x for x in db.scalars(select(ProductMatch).where(ProductMatch.material_id==material_id))}
    result=[]
    for p in products:
        match=matches.get(p.id); row=product_dict(db,p); row["supplier"]=db.get(Supplier,p.supplier_id).name; row["confidence"]=match.confidence if match else match_score(material,p); row["approved"]=bool(match and match.approved); row["match_status"]=match.match_status if match else "AUTO"; result.append(row)
    return sorted(result,key=lambda x:x["confidence"],reverse=True)

@app.post("/api/catalog/materials/{material_id}/products/{product_id}/match")
def set_product_match(material_id:int,product_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    material=require_entity(db,Material,material_id,"Materialul nu există."); product=require_entity(db,SupplierProduct,product_id,"Produsul nu există.")
    match=db.scalar(select(ProductMatch).where(ProductMatch.material_id==material_id,ProductMatch.supplier_product_id==product_id)) or ProductMatch(material_id=material_id,supplier_product_id=product_id,confidence=match_score(material,product))
    approve=bool(payload.get("approved")); match.approved=approve; match.match_status="MANUAL" if approve else "REJECTED"; match.approved_at=datetime.now(timezone.utc) if approve else None; match.notes=payload.get("notes"); db.add(match); db.commit(); return {"id":match.id,"approved":match.approved,"match_status":match.match_status,"confidence":match.confidence}

@app.post("/api/suppliers/refresh")
def schedule_refresh(payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    product_id=payload.get("supplier_product_id"); supplier_id=payload.get("supplier_id")
    if product_id and not supplier_id: supplier_id=require_entity(db,SupplierProduct,int(product_id),"Produsul nu există.").supplier_id
    supplier=require_entity(db,Supplier,int(supplier_id),"Furnizorul nu există.")
    product_ids=[int(product_id)] if product_id else list(db.scalars(select(SupplierProduct.id).where(SupplierProduct.supplier_id==supplier.id,SupplierProduct.active.is_(True))))
    if not product_ids: raise HTTPException(422,"Furnizorul nu are produse active de actualizat.")
    jobs=[SupplierRefreshJob(supplier_id=supplier.id,supplier_product_id=pid,job_type=payload.get("job_type","PRODUCT"),status="PENDING",scheduled_at=datetime.now(timezone.utc)) for pid in product_ids]
    db.add_all(jobs);db.commit();return {"id":jobs[0].id,"status":"PENDING","jobs_created":len(jobs)}

@app.post("/api/calc/supplier-package")
def calc_supplier_package(payload:dict,_:User=Depends(current_user)):
    try:return package_purchase(payload["required_quantity"],payload["package_quantity"],payload["package_price"])
    except (KeyError,ValueError) as exc: raise HTTPException(422,str(exc)) from exc

@app.get("/api/catalog/materials/{material_id}/compare")
def compare_material_products(material_id:int,required_quantity:Decimal,db:Session=Depends(get_db),_:User=Depends(current_user)):
    require_entity(db,Material,material_id,"Materialul nu există."); matches=list(db.scalars(select(ProductMatch).where(ProductMatch.material_id==material_id,ProductMatch.approved.is_(True))))
    rows=[]
    for match in matches:
        product=db.get(SupplierProduct,match.supplier_product_id); observation=db.scalar(select(PriceObservation).where(PriceObservation.supplier_product_id==product.id,PriceObservation.success.is_(True)).order_by(PriceObservation.checked_at.desc(),PriceObservation.id.desc()).limit(1))
        if not observation or not product.package_quantity: continue
        purchase=package_purchase(required_quantity,product.package_quantity,observation.price_gross); supplier=db.get(Supplier,product.supplier_id)
        rows.append({"supplier":supplier.name,"product":product.name,"supplier_sku":product.supplier_sku,"required_quantity":required_quantity,"package_quantity":product.package_quantity,"package_unit":product.package_unit,"price_checked_at":observation.checked_at,"delivery_cost":"UNKNOWN",**purchase})
    return sorted(rows,key=lambda x:x["purchase_cost"])

@app.post("/api/projects/{project_id}/delivery-quotes",status_code=201)
def create_delivery_quote(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    project=require_entity(db,Project,project_id,"Proiectul nu există.");supplier=require_entity(db,Supplier,int(payload["supplier_id"]),"Furnizorul nu există.")
    quote=DeliveryQuote(project_id=project.id,supplier_id=supplier.id,supplier_location_id=payload.get("supplier_location_id"),destination_locality=payload.get("destination_locality") or project.locality or "Ceahlău",destination_county=payload.get("destination_county") or project.county or "Neamț",cost_gross=payload.get("cost_gross"),source="MANUAL",checked_at=datetime.now(timezone.utc),notes=payload.get("notes"));db.add(quote);db.commit();db.refresh(quote);return {"id":quote.id,"cost_gross":quote.cost_gross,"source":quote.source}

@app.post("/api/projects/{project_id}/estimate/snapshot",status_code=201)
def snapshot_estimate(project_id:int,payload:dict,db:Session=Depends(get_db),_:User=Depends(current_user)):
    require_entity(db,Project,project_id,"Proiectul nu există.");next_version=(db.scalar(select(func.max(EstimateVersion.version)).where(EstimateVersion.project_id==project_id)) or 0)+1
    lines=payload.get("supplier_lines",[]);total=sum((Decimal(str(x["total_gross"])) for x in lines),Decimal("0"));vat_rate=Decimal(str(payload.get("vat_rate","21")));net=net_from_gross(total,vat_rate)
    version=EstimateVersion(project_id=project_id,version=next_version,status="ISSUED",vat_rate=vat_rate,total_net=net,vat_total=money(total-net),total_gross=money(total),issued_at=datetime.now(timezone.utc));db.add(version);db.flush()
    for x in lines:
        db.add(EstimateSnapshotLine(estimate_version_id=version.id,source_item_id=x.get("source_item_id"),resource_type="MATERIAL",description=x["description"],unit=x["unit"],quantity=x["quantity"],unit_price_net=x["unit_price_net"],vat_rate=x.get("vat_rate",vat_rate),unit_price_gross=x["unit_price_gross"],total_gross=x["total_gross"],supplier_product_id=x.get("supplier_product_id"),supplier_name=x.get("supplier_name"),supplier_sku=x.get("supplier_sku"),product_name=x.get("product_name"),package_quantity=x.get("package_quantity"),package_unit=x.get("package_unit"),purchase_quantity=x.get("purchase_quantity"),packages_to_buy=x.get("packages_to_buy"),product_url=x.get("product_url"),price_checked_at=x.get("price_checked_at")))
    db.commit();return {"id":version.id,"version":version.version,"status":version.status,"total_gross":version.total_gross,"line_count":len(lines)}

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
    project_id = project_for_item(db, item_id); recipe = db.get(WorkRecipe,item.pinned_recipe_id) if item.pinned_recipe_id else resolve_recipe(db, item.work_item_id, project_id)
    if recipe is None: raise HTTPException(status_code=404, detail="Nu există rețetă aplicabilă.")
    if item.pinned_recipe_id is None: item.pinned_recipe_id=recipe.id
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

def json_decimals(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, dict): return {key: json_decimals(item) for key, item in value.items()}
    if isinstance(value, list): return [json_decimals(item) for item in value]
    return value

def geometry_dict(row: GeometryCalculation):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}

def calculate_geometry_payload(payload: GeometryCalculationIn):
    try: results = calculate_geometry(payload.geometry_type, payload.input_data)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.selected_result not in results or payload.selected_result not in GEOMETRY_UNITS:
        raise HTTPException(status_code=422, detail="Rezultatul selectat nu este disponibil pentru acest calculator.")
    return results

def synchronize_geometry_link(db: Session, calculation: GeometryCalculation, link: GeometryEstimateLink):
    item = require_entity(db, EstimateItem, link.estimate_item_id, "Articolul de deviz nu există.")
    results = {key: Decimal(str(value)) for key, value in calculation.results.items()}
    if link.result_key not in results: raise HTTPException(status_code=422, detail="Rezultatul geometric selectat nu există.")
    unit = GEOMETRY_UNITS[link.result_key]
    if item.unit != unit: raise HTTPException(status_code=422, detail=f"Unitatea articolului trebuie să fie {unit}.")
    item.quantity = geometry_with_waste(results[link.result_key], link.waste_percent)
    item.waste_percent = link.waste_percent
    db.flush()
    if item.work_item_id is not None:
        generate_recipe_resources(item.id, db, None)

@app.get("/api/projects/{project_id}/geometry")
def list_geometry(project_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există.")
    rows = db.scalars(select(GeometryCalculation).where(GeometryCalculation.project_id == project_id).order_by(GeometryCalculation.updated_at.desc()))
    return [geometry_dict(row) for row in rows]

@app.post("/api/projects/{project_id}/geometry/calculate")
def preview_geometry(project_id: int, payload: GeometryCalculationIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există.")
    results = calculate_geometry_payload(payload)
    base = results[payload.selected_result]
    return {"results": results, "calculated_unit": GEOMETRY_UNITS[payload.selected_result], "geometric_quantity": base, "waste_quantity": geometry_with_waste(base, payload.waste_percent)-base, "estimate_quantity": geometry_with_waste(base, payload.waste_percent)}

@app.post("/api/projects/{project_id}/geometry", status_code=201)
def create_geometry(project_id: int, payload: GeometryCalculationIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    require_entity(db, Project, project_id, "Proiectul nu există."); results=calculate_geometry_payload(payload); base=results[payload.selected_result]
    if payload.parent_calculation_id is not None:
        parent=require_entity(db, GeometryCalculation,payload.parent_calculation_id,"Calculul structural părinte nu există.")
        if parent.project_id != project_id: raise HTTPException(status_code=422,detail="Elementul structural aparține altui proiect.")
    row=GeometryCalculation(project_id=project_id, results=json_decimals(results), calculated_quantity=geometry_with_waste(base,payload.waste_percent), calculated_unit=GEOMETRY_UNITS[payload.selected_result], **payload.model_dump())
    row.input_data=json_decimals(payload.input_data); db.add(row); db.flush()
    if payload.estimate_item_id is not None:
        link=GeometryEstimateLink(geometry_calculation_id=row.id,estimate_item_id=payload.estimate_item_id,result_key=payload.selected_result,waste_percent=payload.waste_percent); db.add(link); synchronize_geometry_link(db,row,link)
    db.commit(); db.refresh(row); return geometry_dict(row)

@app.put("/api/geometry/{calculation_id}")
def update_geometry(calculation_id: int, payload: GeometryCalculationIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row=require_entity(db,GeometryCalculation,calculation_id,"Calculul geometric nu există."); results=calculate_geometry_payload(payload); base=results[payload.selected_result]
    values=payload.model_dump(); values["input_data"]=json_decimals(payload.input_data); values["results"]=json_decimals(results); values["calculated_quantity"]=geometry_with_waste(base,payload.waste_percent); values["calculated_unit"]=GEOMETRY_UNITS[payload.selected_result]
    for key,value in values.items(): setattr(row,key,value)
    db.flush()
    for link in db.scalars(select(GeometryEstimateLink).where(GeometryEstimateLink.geometry_calculation_id==row.id)): synchronize_geometry_link(db,row,link)
    db.commit(); db.refresh(row); return geometry_dict(row)

@app.delete("/api/geometry/{calculation_id}", status_code=204)
def delete_geometry(calculation_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row=require_entity(db,GeometryCalculation,calculation_id,"Calculul geometric nu există."); db.delete(row); db.commit(); return Response(status_code=204)

@app.post("/api/geometry/{calculation_id}/links", status_code=201)
def link_geometry(calculation_id: int, payload: GeometryLinkIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row=require_entity(db,GeometryCalculation,calculation_id,"Calculul geometric nu există.");
    if project_for_item(db,payload.estimate_item_id)!=row.project_id: raise HTTPException(status_code=422,detail="Articolul aparține altui proiect.")
    link=GeometryEstimateLink(geometry_calculation_id=row.id,**payload.model_dump()); db.add(link); synchronize_geometry_link(db,row,link); commit_or_conflict(db,"Rezultatul este deja legat la acest articol."); db.refresh(link); return link

@app.post("/api/geometry/{calculation_id}/create-item", response_model=EstimateItemOut, status_code=201)
def geometry_create_item(calculation_id: int, payload: GeometryCreateItemIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row=require_entity(db,GeometryCalculation,calculation_id,"Calculul geometric nu există."); section=require_entity(db,EstimateSection,payload.section_id,"Capitolul nu există.")
    section_project=db.scalar(select(Building.project_id).join(Level,Level.building_id==Building.id).join(EstimateSection,EstimateSection.level_id==Level.id).where(EstimateSection.id==section.id))
    if section_project != row.project_id: raise HTTPException(status_code=422,detail="Capitolul aparține altui proiect.")
    if payload.work_item_id is not None: require_entity(db,WorkItem,payload.work_item_id,"Lucrarea standard nu există.")
    results={key:Decimal(str(value)) for key,value in row.results.items()}
    if payload.result_key not in results: raise HTTPException(status_code=422,detail="Rezultatul geometric selectat nu există.")
    item=EstimateItem(section_id=section.id,code=payload.code,description=payload.description,unit=GEOMETRY_UNITS[payload.result_key],quantity=geometry_with_waste(results[payload.result_key],payload.waste_percent),waste_percent=payload.waste_percent,work_item_id=payload.work_item_id,calculation_type="GEOMETRY",calculation_inputs={"geometry_calculation_id":row.id,"result_key":payload.result_key})
    db.add(item); db.flush(); link=GeometryEstimateLink(geometry_calculation_id=row.id,estimate_item_id=item.id,result_key=payload.result_key,waste_percent=payload.waste_percent); db.add(link)
    if item.work_item_id is not None: generate_recipe_resources(item.id,db,None)
    db.commit(); db.refresh(item); return item

@app.get("/api/catalog/mesh")
def list_mesh(db: Session = Depends(get_db), _: User = Depends(current_user)): return list(db.scalars(select(MeshCatalogueItem).order_by(MeshCatalogueItem.code)))

@app.post("/api/catalog/mesh", status_code=201)
def create_mesh(payload: MeshCatalogueIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    values=payload.model_dump(); values["sheet_area_m2"]=payload.sheet_length_m*payload.sheet_width_m; row=MeshCatalogueItem(**values); db.add(row); commit_or_conflict(db,"Codul plasei există deja."); db.refresh(row); return row

@app.get("/api/catalog/categories")
def list_categories(db:Session=Depends(get_db),_:User=Depends(current_user)): return list(db.scalars(select(WorkCategory).order_by(WorkCategory.sort_order)))

@app.post("/api/catalog/admin/reload")
def reload_standard_catalogue(db:Session=Depends(get_db),_:User=Depends(current_user)): return seed_catalogue(db)

@app.post("/api/catalog/admin/reset-standard")
def reset_standard_catalogue(db:Session=Depends(get_db),_:User=Depends(current_user)):
    for model in (Material,LaborResource):
        for row in db.scalars(select(model).where(model.code.like("STD-%"))): row.active=False
    for row in db.scalars(select(WorkItem).where(WorkItem.description.like("Coeficienții rețetei sunt estimări inițiale%"))): row.active=False
    db.commit(); return seed_catalogue(db)

@app.get("/api/catalog/admin/export")
def catalogue_export(db:Session=Depends(get_db),_:User=Depends(current_user)): return export_catalogue(db)

@app.post("/api/catalog/admin/import")
def catalogue_import(payload:CatalogueImportIn,db:Session=Depends(get_db),_:User=Depends(current_user)):
    if payload.schema_version!="1": raise HTTPException(status_code=422,detail="Versiunea schemei catalogului nu este acceptată.")
    for data in payload.categories:
        row=db.scalar(select(WorkCategory).where(WorkCategory.code==data["code"])) or WorkCategory(code=data["code"]); row.name=data["name"]; row.sort_order=data.get("sort_order",0); db.add(row)
    resource_map={}
    for data in payload.resources.get("materials",[]):
        row=db.scalar(select(Material).where(Material.code==data["code"])) or Material(code=data["code"]); row.name=data["name"]; row.category=data["category"]; row.base_unit=data["unit"]; row.attributes={"source":"IMPORT"}; row.active=data.get("active",True); db.add(row)
        db.flush(); resource_map[("MATERIAL",data.get("id"))]=row.id
    for data in payload.resources.get("labor",[]):
        row=db.scalar(select(LaborResource).where(LaborResource.code==data["code"])) or LaborResource(code=data["code"]); row.name=data["name"]; row.unit=data["unit"]; row.rate_net=Decimal(data["rate_net"]); row.vat_rate=Decimal(data.get("vat_rate","21")); row.rate_gross=gross_from_net_exact(row.rate_net,row.vat_rate); row.active=data.get("active",True); db.add(row)
        db.flush(); resource_map[("LABOR",data.get("id"))]=row.id
    work_map={}
    for data in payload.works:
        row=db.scalar(select(WorkItem).where(WorkItem.code==data["code"])) or WorkItem(code=data["code"]); row.name=data["name"]; row.category=data["category"]; row.unit=data["unit"]; row.description=data.get("description"); row.active=data.get("active",True); db.add(row)
        db.flush(); work_map[data.get("id")]=row.id
    for data in payload.recipes:
        work_id=work_map.get(data["work_item_id"]); recipe=db.scalar(select(WorkRecipe).where(WorkRecipe.work_item_id==work_id,WorkRecipe.version==data["version"]))
        if recipe is None: recipe=WorkRecipe(work_item_id=work_id,scope=data["scope"],project_id=data.get("project_id"),version=data["version"]);db.add(recipe);db.flush()
        if db.scalar(select(RecipeResource.id).where(RecipeResource.recipe_id==recipe.id).limit(1)) is None:
            for line in data.get("resources",[]): db.add(RecipeResource(recipe_id=recipe.id,resource_type=line["resource_type"],resource_id=resource_map.get((line["resource_type"],line.get("resource_id")),line.get("resource_id")),description=line["description"],unit=line["unit"],quantity_per_unit=Decimal(line["quantity_per_unit"]),waste_percent=Decimal(line["waste_percent"])))
    db.commit(); return {"status":"importat","categories":len(payload.categories),"works":len(payload.works),"recipes":len(payload.recipes)}

@app.post("/api/sections/{section_id}/items/from-catalog",response_model=EstimateItemOut,status_code=201)
def create_item_from_catalog(section_id:int,payload:CatalogueItemIn,db:Session=Depends(get_db),_:User=Depends(current_user)):
    require_entity(db,EstimateSection,section_id,"Capitolul nu există."); work=require_entity(db,WorkItem,payload.work_item_id,"Lucrarea nu există."); project_id=db.scalar(select(Building.project_id).join(Level).join(EstimateSection).where(EstimateSection.id==section_id)); recipe=resolve_recipe(db,work.id,project_id)
    item=EstimateItem(section_id=section_id,work_item_id=work.id,pinned_recipe_id=recipe.id if recipe else None,code=payload.code,description=work.name,unit=work.unit,quantity=payload.quantity,waste_percent=payload.waste_percent,calculation_type="CATALOG",calculation_inputs={"recipe_version":recipe.version if recipe else None}); db.add(item); db.flush()
    if recipe: generate_recipe_resources(item.id,db,None)
    db.commit(); db.refresh(item); return item

@app.delete("/api/recipe-resources/{resource_id}",status_code=204)
def delete_recipe_resource(resource_id:int,db:Session=Depends(get_db),_:User=Depends(current_user)):
    row=require_entity(db,RecipeResource,resource_id,"Resursa rețetei nu există."); db.delete(row); db.commit(); return Response(status_code=204)
